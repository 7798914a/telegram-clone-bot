import asyncio
from fastapi import Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from models import get_pool
from collector_engine import start_login_thread, get_pending_code, set_pending_code, del_pending_code, pending_code_requests
from web.auth import login_required

def register(app, render):
    @app.get("/accounts", response_class=HTMLResponse)
    async def accounts_page(request: Request):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            accounts = await conn.fetch("SELECT * FROM tg_accounts ORDER BY id DESC")
        pending_account = None
        for aid in list(pending_code_requests.keys()):
            req = get_pending_code(aid)
            if req.get("status") in ("waiting_code","waiting_2fa","sending_code","connecting","error","timeout","cancelled","connected"):
                pending_account = {"id": aid, "phone": req.get("phone",""), "status": req["status"], "error": req.get("error","")}
                break
        error = request.query_params.get("error")
        return render("accounts.html", active_page="accounts", accounts=accounts, pending_account=pending_account, error=error)

    @app.post("/accounts/add")
    async def add_account(request: Request, phone: str = Form(...), api_id: int = Form(...), api_hash: str = Form(...)):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            account_id = await conn.fetchval(
                "INSERT INTO tg_accounts (phone, api_id, api_hash) VALUES ($1,$2,$3) RETURNING id", 
                phone, api_id, api_hash
            )
        
        del_pending_code(account_id)
        start_login_thread(account_id)
        
        # 等待状态变为 waiting_code 或 error
        for _ in range(10):
            req = get_pending_code(account_id)
            status = req.get("status", "")
            if status in ("waiting_code", "waiting_2fa", "error", "timeout", "connected"):
                break
            await asyncio.sleep(1)
        
        return RedirectResponse("/accounts", status_code=302)

    @app.get("/accounts/{account_id}/login")
    async def login_account(account_id: int, request: Request):
        await login_required(request)
        del_pending_code(account_id)
        start_login_thread(account_id)
        # 等待 3 秒再重定向，让登录线程有机会更新状态
        await asyncio.sleep(3)
        return RedirectResponse("/accounts", status_code=302)

    @app.post("/accounts/verify")
    async def verify_code(request: Request, account_id: int = Form(...), code: str = Form(...)):
        await login_required(request)
        req = get_pending_code(account_id)
        if req:
            req["status"] = "code_submitted"
            req["code"] = code
            set_pending_code(account_id, req)
        return RedirectResponse("/accounts", status_code=302)

    @app.get("/accounts/cancel/{account_id}")
    async def cancel_login(account_id: int, request: Request):
        await login_required(request)
        set_pending_code(account_id, {"status": "cancelled"})
        return RedirectResponse("/accounts", status_code=302)

    @app.post("/accounts/{account_id}/delete")
    async def delete_account(account_id: int, request: Request):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            running = await conn.fetchval(
                "SELECT COUNT(*) FROM clone_tasks WHERE account_id=$1 AND status IN ('running','checking','waiting_join')", 
                account_id
            )
            if running and running > 0:
                return RedirectResponse("/accounts?error=该账号有运行中的任务，无法删除", status_code=302)
            
            task_ids = await conn.fetch("SELECT id FROM clone_tasks WHERE account_id=$1", account_id)
            for t in task_ids:
                await conn.execute("DELETE FROM cloned_posts WHERE task_id=$1", t["id"])
                await conn.execute("DELETE FROM clone_errors WHERE task_id=$1", t["id"])
            await conn.execute("DELETE FROM clone_tasks WHERE account_id=$1", account_id)
            await conn.execute("DELETE FROM tg_accounts WHERE id=$1", account_id)
        del_pending_code(account_id)
        return RedirectResponse("/accounts", status_code=302)

    @app.post("/accounts/update_proxy")
    async def update_proxy(
        request: Request,
        account_id: int = Form(...),
        proxy_type: str = Form("socks5"),
        proxy_host: str = Form(""),
        proxy_port: int = Form(0),
        proxy_username: str = Form(""),
        proxy_password: str = Form("")
    ):
        await login_required(request)
        proxy_host = proxy_host.strip() or None
        proxy_username = proxy_username.strip() or None
        proxy_password = proxy_password.strip() or None
        proxy_port = proxy_port if proxy_port else None

        p = await get_pool()
        async with p.acquire() as conn:
            await conn.execute("""
                UPDATE tg_accounts SET 
                    proxy_type=$1, proxy_host=$2, proxy_port=$3,
                    proxy_username=$4, proxy_password=$5
                WHERE id=$6
            """, proxy_type, proxy_host, proxy_port, proxy_username, proxy_password, account_id)
        return RedirectResponse("/accounts", status_code=302)

    @app.post("/accounts/clear_proxy")
    async def clear_proxy(request: Request, account_id: int = Form(...)):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            await conn.execute("""
                UPDATE tg_accounts SET 
                    proxy_type=NULL, proxy_host=NULL, proxy_port=NULL,
                    proxy_username=NULL, proxy_password=NULL
                WHERE id=$1
            """, account_id)
        return RedirectResponse("/accounts", status_code=302)

    @app.post("/accounts/release")
    async def release_account(request: Request, account_id: int = Form(...)):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            await conn.execute("UPDATE tg_accounts SET is_assigned=FALSE, assigned_task_id=NULL WHERE id=$1", account_id)
        return RedirectResponse("/accounts", status_code=302)