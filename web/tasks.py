from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from models import get_pool
from web.auth import login_required

def register(app, render):
    @app.get("/tasks", response_class=HTMLResponse)
    async def tasks_page(request: Request, page: int = 1):
        await login_required(request)
        page_size = 20
        offset = (page - 1) * page_size
        
        p = await get_pool()
        async with p.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM clone_tasks")
            tasks = await conn.fetch(
                "SELECT * FROM clone_tasks ORDER BY id DESC LIMIT $1 OFFSET $2",
                page_size, offset
            )
        
        total_pages = max((total + page_size - 1) // page_size, 1)
        return render(
            "tasks.html",
            active_page="tasks",
            tasks=tasks,
            page=page,
            total_pages=total_pages,
            total=total
        )

    @app.get("/api/progress/{task_id}")
    async def api_progress(task_id: int):
        from redis_queue import get_progress
        p = await get_progress(task_id)
        return JSONResponse(p if p else {"status": "unknown"})
