from telethon import events, Button
from models import get_pool

def register(bot):
    @bot.on(events.CallbackQuery(data="my_info"))
    async def cb_my_info(event):
        p = await get_pool()
        async with p.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", event.sender_id)
            if not user:
                await conn.execute("INSERT INTO users (telegram_id, username) VALUES ($1,$2)", event.sender_id, getattr(event.sender, 'username', ''))
                user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", event.sender_id)
        
        vip = "✅ 是" if user['is_vip'] else "❌ 否"
        balance = user['balance'] if user['balance'] else 0
        text = f"👤 **我的信息**\n\n🆔 TG ID：`{event.sender_id}`\n💎 VIP：{vip}\n💰 余额：¥{balance}"
        # 移除返回按钮，底部键盘导航
        await event.edit(text)
    
    @bot.on(events.NewMessage(pattern='👤 我的信息'))
    async def cmd_my_info(event):
        if not event.is_private: return
        p = await get_pool()
        async with p.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", event.sender_id)
            if not user:
                await conn.execute("INSERT INTO users (telegram_id, username) VALUES ($1,$2)", event.sender_id, getattr(event.sender, 'username', ''))
                user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", event.sender_id)
        vip = "✅ 是" if user['is_vip'] else "❌ 否"
        balance = user['balance'] if user['balance'] else 0
        text = f"👤 **我的信息**\n\n🆔 TG ID：`{event.sender_id}`\n💎 VIP：{vip}\n💰 余额：¥{balance}"
        await event.reply(text)