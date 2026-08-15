from fastapi import Request
from fastapi.responses import HTMLResponse
from models import get_pool
from web.auth import login_required

def register(app, render):
    @app.get("/admin_logs", response_class=HTMLResponse)
    async def admin_logs_page(request: Request):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            logs = await conn.fetch("SELECT * FROM admin_logs ORDER BY id DESC LIMIT 100")
        return render("admin_logs.html", active_page="admin_logs", logs=logs)
