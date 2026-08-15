from fastapi import Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from models import get_pool
from web.auth import login_required
from models import log_admin_action

def register(app, render):
    @app.get("/users", response_class=HTMLResponse)
    async def users_page(request: Request):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            users = await conn.fetch("SELECT * FROM users ORDER BY id DESC")
            payments = await conn.fetch("SELECT * FROM payments ORDER BY id DESC LIMIT 20")
        return render("users.html", active_page="users", users=users, payments=payments)

    @app.post("/users/recharge")
    async def recharge_user(request: Request, telegram_id: int = Form(...), amount: float = Form(...), note: str = Form("")):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            # 确认用户存在
            user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", telegram_id)
            if not user:
                await conn.execute("INSERT INTO users (telegram_id) VALUES ($1)", telegram_id)
            # 创建充值记录
            await conn.execute("INSERT INTO payments (telegram_id, amount, status, note) VALUES ($1,$2,'approved',$3)", telegram_id, amount, note)
            # 更新余额
            await conn.execute("UPDATE users SET balance = balance + $1 WHERE telegram_id=$2", amount, telegram_id)
            await log_admin_action("手动充值", f"给 {telegram_id} 充值 ¥{amount}", "admin")
        return RedirectResponse("/users", status_code=302)

    @app.get("/payments", response_class=HTMLResponse)
    async def payments_page(request: Request):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            payments = await conn.fetch("SELECT * FROM payments ORDER BY id DESC LIMIT 50")
        return render("payments.html", active_page="payments", payments=payments)
