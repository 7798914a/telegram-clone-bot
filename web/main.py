import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
app = FastAPI()
jinja_env = Environment(loader=FileSystemLoader(os.path.join(BASE_DIR, "templates")))

def render(name, **kwargs):
    # ✅ 直接渲染模板，base.html 已经通过 {% extends %} 包含了布局
    template = jinja_env.get_template(name)
    content = template.render(**kwargs)
    return HTMLResponse(content)

# 注册所有模块
from web import auth, accounts, tasks, clone, users, payments, prices, okpay_callback, filters, vip, support, logs
auth.register(app)
accounts.register(app, render)
tasks.register(app, render)
clone.register(app, render)
users.register(app, render)
payments.register(app, render)
prices.register(app, render)
okpay_callback.register(app)
filters.register(app, render)
vip.register(app, render)
support.register(app, render)
logs.register(app, render)

@app.get("/", response_class=HTMLResponse)
async def index():
    return RedirectResponse("/dashboard")

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    from web.auth import login_required
    from models import get_pool
    from redis_queue import get_redis, QUEUE_KEY
    await login_required(request)
    p = await get_pool()
    async with p.acquire() as conn:
        accounts_list = await conn.fetch("SELECT * FROM tg_accounts ORDER BY id DESC")
        tasks_list = await conn.fetch("SELECT * FROM clone_tasks ORDER BY id DESC LIMIT 10")
    try:
        r = await get_redis()
        queue_len = await r.llen(QUEUE_KEY)
    except: queue_len = 0
    return render("dashboard.html", active_page="dashboard", accounts=accounts_list, tasks=tasks_list, queue_len=queue_len)
