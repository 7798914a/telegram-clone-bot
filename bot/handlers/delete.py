from telethon import events, Button
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest
from models import get_pool
from collector_engine import get_session_path
from bot.handlers import account_selector
import logging

logger = logging.getLogger(__name__)

async def check_delete_permission(account, dst):
    """检查账号是否有删除目标频道消息的权限"""
    try:
        client = TelegramClient(get_session_path(account["id"]), account["api_id"], account["api_hash"])
        await client.connect()
        me = await client.get_me()
        dst_in = False
        dst_delete = False
        try:
            dst_entity = await client.get_entity(dst)
            try:
                participant = await client.get_permissions(dst_entity, me)
                dst_in = True
                if participant:
                    dst_delete = getattr(participant, 'delete_messages', False)
            except:
                dst_in = False
        except:
            dst_in = False
        await client.disconnect()
        return dst_in, dst_delete
    except Exception as e:
        logger.error(f"检查删除权限失败: {e}")
        return False, False

def register(bot):
    @bot.on(events.CallbackQuery(data="mode_delete_all"))
    async def cb_mode_delete_all(event):
        await event.answer()
        p = await get_pool()
        async with p.acquire() as conn:
            prices = await conn.fetch("SELECT * FROM prices")
            user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", event.sender_id)
            # 保存删除模式状态
            await conn.execute(
                "INSERT INTO user_states (telegram_id, mode) VALUES ($1,$2) ON CONFLICT (telegram_id) DO UPDATE SET mode=$2",
                event.sender_id, "delete_all"
            )
        price_map = {x['type']: x['price'] for x in prices}
        delete_price = price_map.get('delete_all', 10)
        balance = float(user['balance']) if user and user['balance'] else 0
        if balance < delete_price:
            await event.answer(f"❌ 余额不足，需要 ¥{delete_price}", alert=True)
            return
        await account_selector.show_account_selection(
            event,
            mode_type="delete_all",
            mode_name="删除全部帖子",
            need_count=1,
            price=delete_price
        )

    @bot.on(events.NewMessage(pattern=r'^(@\S+|https://t\.me/\S+)'))
    async def handle_delete_input(event):
        if not event.is_private:
            return
        text = event.text.strip()
        if text.startswith('/'):
            return

        p = await get_pool()
        async with p.acquire() as conn:
            state = await conn.fetchrow("SELECT mode FROM user_states WHERE telegram_id=$1", event.sender_id)
            selected = await conn.fetchrow("SELECT account_id FROM user_selected_account WHERE telegram_id=$1", event.sender_id)

        if not state or not selected or state["mode"] != "delete_all":
            return

        dst = text.split()[0]
        account_id = selected["account_id"]

        async with p.acquire() as conn:
            account = await conn.fetchrow("SELECT * FROM tg_accounts WHERE id=$1", account_id)

        if not account:
            await event.reply("❌ 账号不存在")
            return

        dst_in, dst_delete = await check_delete_permission(account, dst)

        async with p.acquire() as conn:
            tid = await conn.fetchval(
                "INSERT INTO clone_tasks (user_telegram_id, account_id, source_channel, target_channel, status, task_type) VALUES ($1,$2,'',$3,'checking','delete_all') RETURNING id",
                event.sender_id, account_id, dst
            )

        username_display = ""
        try:
            client = TelegramClient(get_session_path(account_id), account["api_id"], account["api_hash"])
            await client.connect()
            me = await client.get_me()
            if me and me.username:
                username_display = f"@{me.username}"
            elif me and me.first_name:
                username_display = me.first_name
            await client.disconnect()
        except:
            pass

        msg = f"📋 **删除任务 #{tid}**\n\n"
        msg += f"👤 账号: {username_display}\n"
        msg += f"🎯 目标频道: {'✅ 可访问' if dst_in else '❌ 不在频道'} | {'✅ 有删除权限' if dst_delete else '❌ 无删除权限'}\n\n"

        buttons = []
        if dst_in and dst_delete:
            msg += "✅ 检查通过！可以开始删除。"
            buttons.append([Button.inline("🚀 开始删除", f"start_delete_{tid}")])
        else:
            if not dst_in:
                msg += "❌ 账号不在目标频道\n"
            elif not dst_delete:
                msg += "⚠️ 账号无删除权限，请设为管理员并授予删除消息权限\n"
            buttons.append([Button.inline("🚀 加入频道", f"del_join_{tid}")])
            buttons.append([Button.inline("🔍 重新检查", f"del_recheck_{tid}")])
        buttons.append([Button.inline("❌ 取消退款", f"del_cancel_{tid}")])

        try:
            await event.delete()
        except:
            pass
        await event.reply(msg, buttons=buttons)

        async with p.acquire() as conn:
            await conn.execute("DELETE FROM user_states WHERE telegram_id=$1", event.sender_id)

    @bot.on(events.CallbackQuery(pattern=r"del_recheck_(\d+)"))
    async def cb_del_recheck(event):
        tid = int(event.pattern_match.group(1))
        await event.answer("🔍 检查中...")
        p = await get_pool()
        async with p.acquire() as conn:
            task = await conn.fetchrow("SELECT * FROM clone_tasks WHERE id=$1", tid)
            account = await conn.fetchrow("SELECT * FROM tg_accounts WHERE id=$1", task["account_id"])
        dst_in, dst_delete = await check_delete_permission(account, task["target_channel"])
        msg = f"📋 **删除任务 #{tid}**\n\n"
        msg += f"🎯 目标频道: {'✅ 可访问' if dst_in else '❌ 不在频道'} | {'✅ 有删除权限' if dst_delete else '❌ 无删除权限'}\n\n"
        buttons = []
        if dst_in and dst_delete:
            msg += "✅ 通过！"
            buttons.append([Button.inline("🚀 开始删除", f"start_delete_{tid}")])
        else:
            buttons.append([Button.inline("🚀 加入频道", f"del_join_{tid}")])
            buttons.append([Button.inline("🔍 重新检查", f"del_recheck_{tid}")])
        buttons.append([Button.inline("❌ 取消退款", f"del_cancel_{tid}")])
        try:
            await event.edit(msg, buttons=buttons)
        except:
            await event.reply(msg, buttons=buttons)

    @bot.on(events.CallbackQuery(pattern=r"del_join_(\d+)"))
    async def cb_del_join(event):
        tid = int(event.pattern_match.group(1))
        await event.answer("⏳ 处理中...")
        p = await get_pool()
        async with p.acquire() as conn:
            task = await conn.fetchrow("SELECT * FROM clone_tasks WHERE id=$1", tid)
            account = await conn.fetchrow("SELECT * FROM tg_accounts WHERE id=$1", task["account_id"])
        try:
            client = TelegramClient(get_session_path(account["id"]), account["api_id"], account["api_hash"])
            await client.connect()
            target = await client.get_entity(task["target_channel"])
            await client(JoinChannelRequest(target))
            await client.disconnect()
            try:
                await event.edit("✅ 已加入，请重新检查", buttons=[[Button.inline("🔍 重新检查", f"del_recheck_{tid}")]])
            except:
                await event.reply("✅ 已加入，请重新检查", buttons=[[Button.inline("🔍 重新检查", f"del_recheck_{tid}")]])
        except:
            try:
                await client.disconnect()
            except:
                pass
            try:
                await event.edit("❌ 无法加入，请手动拉入并设为管理员", buttons=[[Button.inline("🔍 重新检查", f"del_recheck_{tid}")]])
            except:
                await event.reply("❌ 无法加入，请手动拉入并设为管理员", buttons=[[Button.inline("🔍 重新检查", f"del_recheck_{tid}")]])

    @bot.on(events.CallbackQuery(pattern=r"start_delete_(\d+)"))
    async def cb_start_delete(event):
        tid = int(event.pattern_match.group(1))
        p = await get_pool()
        async with p.acquire() as conn:
            await conn.execute("UPDATE clone_tasks SET status='queued' WHERE id=$1", tid)
        from redis_queue import push_task
        await push_task(tid)
        try:
            await event.edit("🚀 删除任务已开始！")
        except:
            await event.reply("🚀 删除任务已开始！")

    @bot.on(events.CallbackQuery(pattern=r"del_cancel_(\d+)"))
    async def cb_del_cancel(event):
        tid = int(event.pattern_match.group(1))
        p = await get_pool()
        async with p.acquire() as conn:
            account = await conn.fetchrow("SELECT * FROM tg_accounts WHERE assigned_task_id=$1", tid)
            if account:
                await conn.execute("UPDATE tg_accounts SET is_assigned=FALSE, assigned_task_id=NULL WHERE id=$1", account["id"])
            await conn.execute("UPDATE clone_tasks SET status='cancelled' WHERE id=$1", tid)
            task = await conn.fetchrow("SELECT * FROM clone_tasks WHERE id=$1", tid)
            prices = await conn.fetch("SELECT * FROM prices")
            price_map = {r['type']: r['price'] for r in prices}
            refund = price_map.get('delete_all', 10)
            await conn.execute(
                "UPDATE users SET balance = balance + $1 WHERE telegram_id=$2",
                refund, task["user_telegram_id"]
            )
            await conn.execute(
                "INSERT INTO payments (telegram_id, amount, status, note) VALUES ($1,$2,'refund','删除任务取消退款')",
                task["user_telegram_id"], refund
            )
        try:
            await event.edit("已取消，账号已释放，费用已退还")
        except:
            await event.reply("已取消，账号已释放，费用已退还")