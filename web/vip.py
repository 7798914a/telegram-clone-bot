from fastapi import Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from models import get_pool
from web.auth import login_required
from models import log_admin_action

def register(app, render):
    @app.get("/vip", response_class=HTMLResponse)
    async def vip_page(request: Request):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            users = await conn.fetch("SELECT * FROM users ORDER BY id DESC LIMIT 100")
        return render("vip.html", active_page="vip", users=users)

    @app.post("/vip/set")
    async def set_vip(request: Request, telegram_id: int = Form(...), is_vip: str = Form("0")):
        await login_required(request)
        vip_val = True if is_vip == "1" else False
        p = await get_pool()
        async with p.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", telegram_id)
            if not user:
                await conn.execute("INSERT INTO users (telegram_id) VALUES ($1)", telegram_id)
            await conn.execute("UPDATE users SET is_vip=$1 WHERE telegram_id=$2", vip_val, telegram_id)
            vip_text = "开通" if vip_val else "取消"
            await log_admin_action("VIP设置", f"用户 {telegram_id} VIP={vip_text}", "admin")
        return RedirectResponse("/vip", status_code=302)
