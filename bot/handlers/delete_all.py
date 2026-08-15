from telethon import events, Button
from models import get_pool
import asyncio
import logging

logger = logging.getLogger(__name__)

def register(bot):
    
    @bot.on(events.NewMessage(pattern='🗑️ 删除全部帖子'))
    async def cmd_delete_all(event):
        if not event.is_private:
            return
        
        msg = "🗑️ **⚠️ 删除频道全部帖子**\n\n"
        msg += "⚠️ **警告：此操作不可恢复！**\n\n"
        msg += "请发送要删除的频道链接或用户名：\n\n"
        msg += "📌 格式1（链接）：\n"
        msg += "`https://t.me/channel_name`\n\n"
        msg += "📌 格式2（@用户名）：\n"
        msg += "`@channel_name`\n\n"
        msg += "⚠️ 要求：\n"
        msg += "• Bot 必须是频道管理员\n"
        msg += "• 有删除消息权限\n\n"
        msg += "❌ 回复 /cancel 取消"
        
        await event.reply(msg)

    @bot.on(events.NewMessage(pattern='/cancel'))
    async def cmd_cancel(event):
        if not event.is_private: return
        await event.reply("✅ 已取消删除操作")

    @bot.on(events.NewMessage())
    async def handle_delete_all_input(event):
        if not event.is_private:
            return
        
        text = event.text.strip()
        if text.startswith('/'):
            return
        
        # 检测是否是频道链接或@用户名
        if not (text.startswith('https://t.me/') or text.startswith('@')):
            return
        
        channel_input = text
        
        # 显示确认对话框
        confirm_msg = f"🗑️ **⚠️ 确认删除全部帖子**\n\n"
        confirm_msg += f"📢 频道: {channel_input}\n\n"
        confirm_msg += "⚠️ **此操作将删除该频道的所有帖子！**\n"
        confirm_msg += "⛔ **不可恢复！**\n\n"
        confirm_msg += "请确认："
        
        buttons = [
            [Button.inline("✅ 确认删除全部", f"confirm_delete_all_{channel_input}")],
            [Button.inline("❌ 取消", "cancel_delete_all")]
        ]
        
        try:
            await event.delete()
        except:
            pass
        await event.reply(confirm_msg, buttons=buttons)

    @bot.on(events.CallbackQuery(data="cancel_delete_all"))
    async def cb_cancel_delete_all(event):
        try:
            await event.delete()
        except:
            pass
        await event.respond("✅ 已取消删除操作")

    @bot.on(events.CallbackQuery(pattern=r"confirm_delete_all_(.+)"))
    async def cb_confirm_delete_all(event):
        channel_input = event.pattern_match.group(1)
        
        await event.answer("⏳ 正在获取频道信息...")
        
        try:
            # 获取频道实体
            entity = await bot.get_entity(channel_input)
            channel_title = entity.title if hasattr(entity, 'title') else channel_input
            
            progress_msg = await event.edit(
                f"🗑️ **开始删除频道帖子**\n\n"
                f"📢 频道: {channel_title}\n"
                f"⏳ 正在获取消息列表..."
            )
            
            # 获取所有消息ID
            messages = []
            async for msg in bot.iter_messages(entity, limit=None):
                messages.append(msg.id)
            
            total = len(messages)
            
            if total == 0:
                await progress_msg.edit(
                    f"📢 频道: {channel_title}\n\n"
                    f"✅ 频道中没有帖子"
                )
                return
            
            # 分批删除
            batch_size = 100
            deleted_count = 0
            failed_count = 0
            
            for i in range(0, len(messages), batch_size):
                batch = messages[i:i+batch_size]
                try:
                    await bot.delete_messages(entity, batch)
                    deleted_count += len(batch)
                    
                    progress = int((i + len(batch)) / total * 100)
                    bar = f"[{'█' * (progress // 10)}{'░' * (10 - progress // 10)}]"
                    
                    await progress_msg.edit(
                        f"🗑️ **删除频道帖子**\n\n"
                        f"📢 频道: {channel_title}\n"
                        f"📊 进度: {bar} {progress}%\n"
                        f"✅ 已删除: {deleted_count}/{total} 条\n"
                        f"⏳ 剩余: {total - deleted_count} 条"
                    )
                    
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    failed_count += len(batch)
                    logger.error(f"批量删除失败: {e}")
            
            # 记录日志
            p = await get_pool()
            async with p.acquire() as conn:
                await conn.execute(
                    "INSERT INTO deleted_posts (channel_id, msg_id, deleted_by, reason) VALUES ($1, $2, $3, $4)",
                    str(entity.id), 0, event.sender_id, f"删除全部({total}条)"
                )
            
            result_msg = f"🗑️ **删除完成**\n\n"
            result_msg += f"📢 频道: {channel_title}\n"
            result_msg += f"✅ 成功删除: {deleted_count} 条\n"
            if failed_count > 0:
                result_msg += f"❌ 失败: {failed_count} 条\n"
            result_msg += "\n🎉 所有帖子已删除！"
            
            await progress_msg.edit(result_msg)
            
        except Exception as e:
            error_msg = f"❌ 删除失败\n\n"
            error_msg += f"📢 频道: {channel_input}\n"
            error_msg += f"错误: {str(e)}\n\n"
            error_msg += "请确保：\n"
            error_msg += "1. Bot 是频道管理员\n"
            error_msg += "2. 频道存在且可访问\n"
            error_msg += "3. 有删除消息权限"
            await event.edit(error_msg)
