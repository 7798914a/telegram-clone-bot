import os
import hashlib
import secrets
import time
from datetime import datetime, timedelta
from fastapi import Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from jinja2 import Environment, FileSystemLoader
from models import get_pool

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 登录失败记录（内存，重启清空）
login_attempts = {}

def render_login(error=None, warning=None):
    with open(os.path.join(BASE_DIR, 'templates', 'login.html'), 'r') as f:
        tpl = f.read()
    return HTMLResponse(Environment().from_string(tpl).render(error=error, warning=warning))

async def get_session(request: Request):
    token = request.cookies.get("admin_token")
    if not token: return None
    p = await get_pool()
    async with p.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM admin_sessions WHERE token=$1 AND expires_at > $2", token, datetime.fromtimestamp(time.time()))

async def login_required(request: Request):
    if not await get_session(request):
        raise HTTPException(status_code=302, headers={"Location": "/login"})

def check_password_strength(pwd):
    if len(pwd) < 6:
        return False, "密码至少6位"
    return True, ""

def register(app):
    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        return render_login()

    @app.post("/login")
    async def login(request: Request, password: str = Form(...)):
        ip = request.client.host
        
        # 防爆破：同一IP 5次失败锁5分钟
        now = time.time()
        if ip in login_attempts:
            attempts = login_attempts[ip]
            if attempts["count"] >= 5 and now - attempts["last_time"] < 300:
                return render_login(error="尝试次数过多，请5分钟后再试")
        
        if hashlib.sha256(password.encode()).hexdigest() == hashlib.sha256("admin123".encode()).hexdigest():
            # 成功，清空记录
            login_attempts.pop(ip, None)
            token = secrets.token_hex(32)
            p = await get_pool()
            async with p.acquire() as conn:
                await conn.execute("DELETE FROM admin_sessions WHERE expires_at < $1", datetime.fromtimestamp(time.time()))
                await conn.execute("INSERT INTO admin_sessions (token, expires_at) VALUES ($1,$2)", token, datetime.fromtimestamp(time.time()) + timedelta(days=7))
            resp = RedirectResponse("/dashboard", status_code=302)
            resp.set_cookie("admin_token", token, httponly=True, max_age=86400*7, path="/", samesite="lax")
            return resp
        
        # 失败记录
        if ip not in login_attempts:
            login_attempts[ip] = {"count": 0, "last_time": now}
        login_attempts[ip]["count"] += 1
        login_attempts[ip]["last_time"] = now
        remaining = 5 - login_attempts[ip]["count"]
        return render_login(error=f"密码错误，还剩{remaining}次尝试")

    @app.get("/logout")
    async def logout(request: Request):
        token = request.cookies.get("admin_token")
        if token:
            p = await get_pool()
            async with p.acquire() as conn:
                await conn.execute("DELETE FROM admin_sessions WHERE token=$1", token)
        resp = RedirectResponse("/login", status_code=302)
        resp.delete_cookie("admin_token", path="/")
        return resp

    @app.get("/change_password", response_class=HTMLResponse)
    async def change_password_page(request: Request):
        await login_required(request)
        return render_password()

    @app.post("/change_password")
    async def change_password(request: Request, current_password: str = Form(...), new_password: str = Form(...), confirm_password: str = Form(...)):
        await login_required(request)
        
        # 验证当前密码
        if hashlib.sha256(current_password.encode()).hexdigest() != hashlib.sha256("admin123".encode()).hexdigest():
            return render_password(error="当前密码错误")
        
        # 验证新密码
        ok, msg = check_password_strength(new_password)
        if not ok:
            return render_password(error=msg)
        
        if new_password != confirm_password:
            return render_password(error="两次密码不一致")
        
        # 更新密码（写文件）
        try:
            with open(os.path.join(BASE_DIR, 'admin_password.txt'), 'w') as f:
                f.write(new_password)
            return render_password(success="密码已修改，请重新登录")
        except:
            return render_password(error="保存失败")

def render_password(error=None, success=None):
    html = '''
<h4>修改密码</h4>
<div class="card"><div class="card-body">
{% if error %}<div class="alert alert-danger">{{ error }}</div>{% endif %}
{% if success %}<div class="alert alert-success">{{ success }}</div>{% endif %}
<form method="post" action="/change_password">
<div class="mb-3"><label class="form-label">当前密码</label><input type="password" class="form-control" name="current_password" required></div>
<div class="mb-3"><label class="form-label">新密码（至少6位）</label><input type="password" class="form-control" name="new_password" required minlength="6"></div>
<div class="mb-3"><label class="form-label">确认新密码</label><input type="password" class="form-control" name="confirm_password" required></div>
<button class="btn btn-primary">修改</button>
</form>
</div></div>
'''
    from jinja2 import Environment, BaseLoader
    env = Environment(loader=BaseLoader())
    template = env.from_string(html)
    # 简化：直接用文件读 base.html 包裹
    import os as _os
    base_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    with open(_os.path.join(base_dir, 'templates', 'base.html'), 'r') as f:
        base = f.read()
    page_content = template.render(error=error, success=success)
    # 简单替换
    base = base.replace('{{ page_content|safe }}', page_content)
    from jinja2 import Environment as Env2, BaseLoader as BL2
    return HTMLResponse(Env2(loader=BL2()).from_string(base).render(active_page=''))
