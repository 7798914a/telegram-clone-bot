from fastapi import Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from models import get_pool
from web.auth import login_required
from models import log_admin_action

def register(app, render):
    @app.get("/filters", response_class=HTMLResponse)
    async def filters_page(request: Request):
        await login_required(request)
        p = await get_pool()
        async with p.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM settings WHERE key IN ('filter_ads','filter_buttons','filter_links','filter_mentions','ad_keywords','max_mentions')"
            )
        settings = {r['key']: r['value'] for r in rows}
        return render(
            "filters.html",
            active_page="filters",
            filter_ads=(settings.get('filter_ads') == '1'),
            filter_buttons=(settings.get('filter_buttons') == '1'),
            filter_links=(settings.get('filter_links') == '1'),
            filter_mentions=(settings.get('filter_mentions') == '1'),
            ad_keywords=settings.get('ad_keywords', ''),
            max_mentions=settings.get('max_mentions', '3'),
            success=False
        )

    @app.post("/filters/update")
    async def update_filters(
        request: Request,
        filter_ads: str = Form("0"),
        filter_buttons: str = Form("0"),
        filter_links: str = Form("0"),
        filter_mentions: str = Form("0"),
        ad_keywords: str = Form(""),
        max_mentions: int = Form(3)
    ):
        await login_required(request)
        filter_ads = "1" if filter_ads == "1" else "0"
        filter_buttons = "1" if filter_buttons == "1" else "0"
        filter_links = "1" if filter_links == "1" else "0"
        filter_mentions = "1" if filter_mentions == "1" else "0"

        p = await get_pool()
        async with p.acquire() as conn:
            await conn.execute("INSERT INTO settings (key, value) VALUES ('filter_ads', $1) ON CONFLICT (key) DO UPDATE SET value=$1", filter_ads)
            await conn.execute("INSERT INTO settings (key, value) VALUES ('filter_buttons', $1) ON CONFLICT (key) DO UPDATE SET value=$1", filter_buttons)
            await conn.execute("INSERT INTO settings (key, value) VALUES ('filter_links', $1) ON CONFLICT (key) DO UPDATE SET value=$1", filter_links)
            await conn.execute("INSERT INTO settings (key, value) VALUES ('filter_mentions', $1) ON CONFLICT (key) DO UPDATE SET value=$1", filter_mentions)
            await conn.execute("INSERT INTO settings (key, value) VALUES ('ad_keywords', $1) ON CONFLICT (key) DO UPDATE SET value=$1", ad_keywords)
            await conn.execute("INSERT INTO settings (key, value) VALUES ('max_mentions', $1) ON CONFLICT (key) DO UPDATE SET value=$1", str(max_mentions))
            await log_admin_action("过滤设置修改", "广告过滤设置已更新", "admin")

        return RedirectResponse("/filters?success=1", status_code=302)