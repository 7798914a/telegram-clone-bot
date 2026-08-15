from fastapi import Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from models import get_pool
from redis_queue import push_task
from web.auth import login_required

def register(app, render):
    @app.get("/clone", response_class=HTMLResponse)
    async def clone_page(request: Request):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            accounts = await conn.fetch("SELECT * FROM tg_accounts WHERE status='connected'")
        return render("clone.html", active_page="clone", accounts=accounts)

    @app.post("/clone/start")
    async def start_clone(request: Request, account_id: int = Form(...), source: str = Form(...), target: str = Form(...), max_posts: int = Form(0)):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            task_id = await conn.fetchval("INSERT INTO clone_tasks (account_id, source_channel, target_channel, max_posts) VALUES ($1,$2,$3,$4) RETURNING id", account_id, source, target, max_posts)
        await push_task(task_id)
        return RedirectResponse("/dashboard", status_code=302)