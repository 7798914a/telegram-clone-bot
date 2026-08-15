from fastapi import Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from models import get_pool
from web.auth import login_required

def register(app, render):
    @app.get("/support", response_class=HTMLResponse)
    async def support_page(request: Request):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            row = await conn.fetchrow("SELECT value FROM settings WHERE key='support_link'")
        link = row["value"] if row else ""
        return render("support.html", active_page="support", link=link)

    @app.post("/support/update")
    async def update_support(request: Request, support_link: str = Form(...)):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            await conn.execute("INSERT INTO settings (key, value) VALUES ('support_link', $1) ON CONFLICT (key) DO UPDATE SET value=$1", support_link)
        return RedirectResponse("/support", status_code=302)
