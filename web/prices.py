from fastapi import Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from models import get_pool
from web.auth import login_required
from models import log_admin_action

def register(app, render):
    @app.get("/prices", response_class=HTMLResponse)
    async def prices_page(request: Request):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            full = await conn.fetchval("SELECT price FROM prices WHERE type='full'")
            dual = await conn.fetchval("SELECT price FROM prices WHERE type='dual'")
            from_link = await conn.fetchval("SELECT price FROM prices WHERE type='from_link'")
            monitor = await conn.fetchval("SELECT price FROM prices WHERE type='monitor'")
            delete_all = await conn.fetchval("SELECT price FROM prices WHERE type='delete_all'")
        
        return render("prices.html", active_page="prices", 
                     full=full, dual=dual, from_link=from_link, monitor=monitor,
                     delete_all=delete_all)

    @app.post("/prices/update")
    async def update_prices(
        request: Request, 
        full: float = Form(0), 
        dual: float = Form(0),
        from_link: float = Form(0), 
        monitor: float = Form(0),
        delete_all: float = Form(0)
    ):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            await conn.execute("UPDATE prices SET price=$1 WHERE type='full'", full)
            await log_admin_action("价格修改", f"普通模式 ¥{full}", "admin")
            
            await conn.execute("UPDATE prices SET price=$1 WHERE type='dual'", dual)
            await log_admin_action("价格修改", f"双账号模式 ¥{dual}", "admin")
            
            await conn.execute("UPDATE prices SET price=$1 WHERE type='from_link'", from_link)
            await log_admin_action("价格修改", f"从链接 ¥{from_link}", "admin")
            
            await conn.execute("UPDATE prices SET price=$1 WHERE type='monitor'", monitor)
            await log_admin_action("价格修改", f"实时监控 ¥{monitor}", "admin")
            
            await conn.execute("UPDATE prices SET price=$1 WHERE type='delete_all'", delete_all)
            await log_admin_action("价格修改", f"删除全部帖子 ¥{delete_all}", "admin")
            
        return RedirectResponse("/prices", status_code=302)