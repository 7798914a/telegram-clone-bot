from telethon import events, Button
from models import get_pool

def register(bot):
    @bot.on(events.CallbackQuery(data="support"))
    async def cb_support(event):
        p = await get_pool()
        async with p.acquire() as conn:
            row = await conn.fetchrow("SELECT value FROM settings WHERE key='support_link'")
        link = row["value"] if row else "https://t.me/your_support"
        if not link.startswith("http"):
            link = f"https://t.me/{link}"
        await event.edit(
            "🎧 **联系客服**\n\n点击下方按钮联系：",
            buttons=[[Button.url("💬 联系客服", link)]]
        )
    
    @bot.on(events.NewMessage(pattern='🎧 联系客服'))
    async def cmd_support(event):
        if not event.is_private: return
        p = await get_pool()
        async with p.acquire() as conn:
            row = await conn.fetchrow("SELECT value FROM settings WHERE key='support_link'")
        link = row["value"] if row else "https://t.me/your_support"
        if not link.startswith("http"):
            link = f"https://t.me/{link}"
        await event.reply(
            "🎧 **联系客服**\n\n点击下方按钮联系：",
            buttons=[[Button.url("💬 联系客服", link)]]
        )