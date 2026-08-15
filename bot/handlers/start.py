from telethon import events, Button
from models import get_pool

def register(bot):
    @bot.on(events.NewMessage(pattern='/start'))
    async def cmd_start(event):
        if not event.is_private:
            return
        await event.reply(
            "🤖 **频道克隆 Bot**\n\n使用下方按钮操作：",
            buttons=[
                [Button.text("📋 创建任务", resize=True), Button.text("📊 任务进度", resize=True)],
                [Button.text("👤 我的信息", resize=True), Button.text("💰 余额充值", resize=True)],
                [Button.text("🎧 联系客服", resize=True)]
            ]
        )

    # ✅ 处理 "🔙 返回主菜单"（文本按钮）
    @bot.on(events.NewMessage(pattern='🔙 返回主菜单'))
    async def cmd_back_menu(event):
        if not event.is_private:
            return
        # 清理用户状态，防止残留影响后续操作
        p = await get_pool()
        async with p.acquire() as conn:
            await conn.execute("DELETE FROM user_states WHERE telegram_id=$1", event.sender_id)
            await conn.execute("DELETE FROM user_selected_account WHERE telegram_id=$1", event.sender_id)
            await conn.execute("DELETE FROM user_selected_backup WHERE telegram_id=$1", event.sender_id)
            await conn.execute("DELETE FROM user_selected_backup_multi WHERE telegram_id=$1", event.sender_id)
        # 调用主菜单
        await cmd_start(event)