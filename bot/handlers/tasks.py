from telethon import events, Button
from models import get_pool

def register(bot):
    @bot.on(events.CallbackQuery(data="my_tasks"))
    async def cb_my_tasks(event):
        await show_tasks(bot, event, edit=True)
    
    @bot.on(events.NewMessage(pattern='📋 我的任务'))
    async def cmd_my_tasks(event):
        if not event.is_private: return
        await show_tasks(bot, event, edit=False)
    
    @bot.on(events.NewMessage(pattern='📊 任务进度'))
    async def cmd_task_progress(event):
        if not event.is_private: return
        await show_tasks(bot, event, edit=False)
    
    @bot.on(events.CallbackQuery(pattern=r"stop_task_(\d+)"))
    async def cb_stop_task(event):
        tid = int(event.pattern_match.group(1))
        p = await get_pool()
        async with p.acquire() as conn:
            account = await conn.fetchrow("SELECT * FROM tg_accounts WHERE assigned_task_id=$1", tid)
            if account:
                await conn.execute("UPDATE tg_accounts SET is_assigned=FALSE, assigned_task_id=NULL WHERE id=$1", account["id"])
            await conn.execute("UPDATE clone_tasks SET status='stopped' WHERE id=$1", tid)
        await event.edit(f"✅ 任务 #{tid} 已停止，账号已释放", buttons=[[Button.inline("🔄 刷新", "my_tasks")]])
    
    @bot.on(events.CallbackQuery(pattern=r"delete_task_(\d+)"))
    async def cb_delete_task(event):
        tid = int(event.pattern_match.group(1))
        p = await get_pool()
        async with p.acquire() as conn:
            account = await conn.fetchrow("SELECT * FROM tg_accounts WHERE assigned_task_id=$1", tid)
            if account:
                await conn.execute("UPDATE tg_accounts SET is_assigned=FALSE, assigned_task_id=NULL WHERE id=$1", account["id"])
            # 先删关联数据
            await conn.execute("DELETE FROM cloned_posts WHERE task_id=$1", tid)
            await conn.execute("DELETE FROM clone_errors WHERE task_id=$1", tid)
            await conn.execute("DELETE FROM clone_tasks WHERE id=$1", tid)
        await event.edit(f"✅ 任务 #{tid} 已删除", buttons=[[Button.inline("🔄 刷新", "my_tasks")]])

async def show_tasks(bot, event, edit=False):
    p = await get_pool()
    async with p.acquire() as conn:
        tasks = await conn.fetch("SELECT * FROM clone_tasks WHERE user_telegram_id=$1 OR user_telegram_id IS NULL ORDER BY id DESC LIMIT 5", event.sender_id)
    
    if not tasks:
        msg = "📭 暂无任务"
        if edit:
            try: await event.edit(msg)
            except: await event.reply(msg)
        else: await event.reply(msg)
        return
    
    status_map = {
        'done': '✅', 'running': '🔄', 'checking': '🔍',
        'waiting_join': '⏳', 'waiting_account': '⏳',
        'need_join': '⚠️', 'cancelled': '❌', 'error': '❌',
        'queued': '⏳', 'monitoring': '📡', 'stopped': '🛑'
    }
    
    text = "📊 **任务列表**\n\n"
    buttons = []
    
    for t in tasks:
        icon = status_map.get(t['status'], '❓')
        cloned = t['cloned'] or 0
        text += f"{icon} #{t['id']} | {t['status']} | 已克隆 {cloned} 条\n\n"
        
        # 每个任务都显示停止和删除
        if t['status'] == 'need_join':
            buttons.append([Button.inline(f"🔍 重新检查 #{t['id']}", f"check_{t['id']}")])
        elif t['status'] not in ('done', 'cancelled', 'error', 'stopped'):
            buttons.append([Button.inline(f"🛑 停止 #{t['id']}", f"stop_task_{t['id']}")])
        buttons.append([Button.inline(f"🗑️ 删除 #{t['id']}", f"delete_task_{t['id']}")])
    
    buttons.append([Button.inline("🔄 刷新", "my_tasks")])
    
    if edit:
        try: await event.edit(text, buttons=buttons)
        except: await event.reply(text, buttons=buttons)
    else: await event.reply(text, buttons=buttons)
