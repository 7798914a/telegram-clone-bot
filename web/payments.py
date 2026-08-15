from fastapi import Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from models import get_pool
from web.auth import login_required

def register(app, render):
    @app.get("/payments", response_class=HTMLResponse)
    async def payments_page(request: Request):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            pending = await conn.fetch("SELECT * FROM payments WHERE status='pending' ORDER BY id DESC")
            all_records = await conn.fetch("SELECT * FROM payments ORDER BY id DESC LIMIT 50")
        return render("payments.html", active_page="payments", pending=pending, records=all_records)

    @app.post("/payments/approve/{payment_id}")
    async def approve_payment(payment_id: int, request: Request):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            payment = await conn.fetchrow("SELECT * FROM payments WHERE id=$1", payment_id)
            if payment and payment["status"] == "pending":
                await conn.execute("UPDATE payments SET status='approved', approved_at=NOW() WHERE id=$1", payment_id)
                await conn.execute("UPDATE users SET balance = balance + $1 WHERE telegram_id=$2", payment["amount"], payment["telegram_id"])
        return RedirectResponse("/payments", status_code=302)

    @app.post("/payments/reject/{payment_id}")
    async def reject_payment(payment_id: int, request: Request):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            await conn.execute("UPDATE payments SET status='rejected' WHERE id=$1", payment_id)
        return RedirectResponse("/payments", status_code=302)
