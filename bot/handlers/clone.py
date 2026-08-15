from telethon import events, Button
from models import get_pool
from redis_queue import push_task
from collector_engine import get_session_path
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest
from bot.handlers import account_selector
import re
import asyncio

async def check_channels(account, src, dst):
    try:
        client = TelegramClient(get_session_path(account["id"]), account["api_id"], account["api_hash"])
        await client.connect()
        me = await client.get_me()
        src_ok = False
        try:
            await client.get_entity(src)
            src_ok = True
        except:
            pass
        dst_in = False
        dst_admin = False
        try:
            dst_entity = await client.get_entity(dst)
            try:
                participant = await client.get_permissions(dst_entity, me)
                dst_in = True
                if participant:
                    dst_admin = getattr(participant, 'send_messages', False) or getattr(participant, 'post_messages', False)
            except:
                dst_in = False
        except:
            dst_in = False
        await client.disconnect()
        return src_ok, dst_in, dst_admin
    except:
        return False, False, False

def register(bot):
    @bot.on(events.NewMessage(pattern='📋 创建任务'))
    async def cmd_create_clone_text(event):
        if not event.is_private:
            return
        await show_mode_selection(event, reply=True)

    @bot.on(events.CallbackQuery(data="create_clone"))
    async def cb_create_clone(event):
        await show_mode_selection(event, edit=True)

    async def show_mode_selection(event, reply=False, edit=False):
        p = await get_pool()
        async with p.acquire() as conn:
            free = await conn.fetch("SELECT * FROM tg_accounts WHERE status='connected' AND (is_assigned IS NULL OR is_assigned=FALSE)")
            prices = await conn.fetch("SELECT * FROM prices")
            user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", event.sender_id)

        price_map = {x['type']: x['price'] for x in prices}
        balance = float(user['balance']) if user and user['balance'] else 0
        is_vip = user['is_vip'] if user else False

        if not free:
            msg = "❌ 没有空闲账号，请稍后再试"
            if reply:
                await event.reply(msg)
            else:
                try:
                    await event.edit(msg)
                except:
                    await event.reply(msg)
            return

        total_free = len(free)
        normal_price = price_map.get('full', 5)
        dual_price = price_map.get('dual', 8)
        delete_price = price_map.get('delete_all', 10)

        msg = "📋 **选择克隆模式**\n\n"
        msg += f"✅ 空闲账号: {total_free} 个 | 💰 余额: ¥{balance:.2f}\n\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        msg += f"👤 普通模式：1个账号 | ¥{normal_price}\n"
        msg += f"👥 双账号模式：2个账号轮替 | ¥{dual_price}\n"
        if is_vip:
            msg += "👨‍👩‍👦 多账号模式：3个账号轮替 | VIP免费\n"
            msg += "📡 实时监控：持续监控新帖子 | VIP免费\n"
        else:
            msg += "🔒 多账号模式：VIP专属\n"
            msg += "🔒 实时监控：VIP专属\n"
        msg += f"🗑️ 删除全部帖子：清空目标频道 | ¥{delete_price}\n"
        msg += "\n请选择模式："

        buttons = []
        buttons.append([Button.inline("👤 普通模式 ⭐推荐", "select_mode_normal")])
        buttons.append([Button.inline("👥 双账号模式", "select_mode_dual")])

        if is_vip:
            buttons.append([Button.inline("👨‍👩‍👦 多账号模式 👑VIP", "select_mode_multi")])
            buttons.append([Button.inline("📡 实时监控 👑VIP", "select_mode_monitor")])
        else:
            buttons.append([Button.inline("🔒 多账号模式 (VIP专属)", "show_vip_required")])
            buttons.append([Button.inline("🔒 实时监控 (VIP专属)", "show_vip_required")])

        buttons.append([Button.inline("🗑️ 删除频道全部帖子", "mode_delete_all")])
        buttons.append([Button.inline("📖 模式详情", "show_mode_details")])

        if edit:
            try:
                await event.edit(msg, buttons=buttons)
            except:
                await event.reply(msg, buttons=buttons)
        elif reply:
            await event.reply(msg, buttons=buttons)
        else:
            await event.respond(msg, buttons=buttons)

    @bot.on(events.CallbackQuery(data="show_mode_details"))
    async def cb_mode_details(event):
        p = await get_pool()
        async with p.acquire() as conn:
            prices = await conn.fetch("SELECT * FROM prices")
            user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", event.sender_id)

        price_map = {x['type']: x['price'] for x in prices}
        is_vip = user['is_vip'] if user else False
        normal_price = price_map.get('full', 5)
        dual_price = price_map.get('dual', 8)

        details = f"""📖 **模式详情说明**

━━━━━━━━━━━━━━━━━━━━

👤 **普通模式**
━━━━━━━━━━━━━━━━━━━━
• 使用 **1个** 账号进行克隆
• 按帖子数量计费
• 遇到限速会自动暂停等待
• 适合：小批量克隆

💰 费用: ¥{normal_price}/次

━━━━━━━━━━━━━━━━━━━━

👥 **双账号模式**
━━━━━━━━━━━━━━━━━━━━
• 使用 **2个** 账号轮替克隆
• 主账号限速时自动切换备用账号
• 克隆不中断，效率更高
• 适合：中等批量克隆

💰 费用: ¥{dual_price}/次

━━━━━━━━━━━━━━━━━━━━

👨‍👩‍👦 **多账号模式**
━━━━━━━━━━━━━━━━━━━━
• 使用 **3个以上** 账号轮替克隆
• 限速自动切换，稳定高速
• 适合：大批量/高频克隆

💰 费用: {'VIP免费' if is_vip else '🔒 VIP专属'}

━━━━━━━━━━━━━━━━━━━━

📡 **实时监控**
━━━━━━━━━━━━━━━━━━━━
• 持续监控源频道新帖子
• 自动克隆新内容
• 实时同步更新

💰 费用: {'VIP免费' if is_vip else '🔒 VIP专属'}

━━━━━━━━━━━━━━━━━━━━

🗑️ **删除频道全部帖子**
━━━━━━━━━━━━━━━━━━━━
• 删除指定频道的所有帖子
• 需要账号是频道管理员
• 有删除消息权限
• 操作不可恢复

💰 费用: ¥{price_map.get('delete_all', 10)}/次

━━━━━━━━━━━━━━━━━━━━

💡 提示：VIP可免费使用所有模式"""

        buttons = [
            [Button.inline("🔙 返回选择", "create_clone")],
        ]
        if not is_vip:
            buttons.append([Button.inline("👑 升级VIP", "show_vip_plans")])
        try:
            await event.edit(details, buttons=buttons)
        except:
            await event.reply(details, buttons=buttons)

    @bot.on(events.CallbackQuery(data="show_vip_required"))
    async def cb_vip_required(event):
        await event.answer("🔒 该模式仅VIP用户可用，请先升级VIP")
        try:
            await event.edit(
                "🔒 **VIP专属模式**\n\n"
                "该模式仅VIP用户可用\n\n"
                "升级VIP后可使用：\n"
                "✅ 多账号模式\n"
                "✅ 实时监控模式\n"
                "✅ 不限次数克隆\n\n"
                "点击下方按钮了解VIP",
                buttons=[
                    [Button.inline("👑 查看VIP套餐", "show_vip_plans")],
                    [Button.inline("🔙 返回", "create_clone")]
                ]
            )
        except:
            await event.reply(
                "🔒 **VIP专属模式**\n\n"
                "该模式仅VIP用户可用\n\n"
                "升级VIP后可使用：\n"
                "✅ 多账号模式\n"
                "✅ 实时监控模式\n"
                "✅ 不限次数克隆\n\n"
                "点击下方按钮了解VIP",
                buttons=[
                    [Button.inline("👑 查看VIP套餐", "show_vip_plans")],
                    [Button.inline("🔙 返回", "create_clone")]
                ]
            )

    @bot.on(events.CallbackQuery(pattern=r"select_mode_(\w+)"))
    async def cb_select_mode(event):
        mode = event.pattern_match.group(1).decode('utf-8') if isinstance(event.pattern_match.group(1), bytes) else event.pattern_match.group(1)

        try:
            await event.delete()
        except:
            pass

        p = await get_pool()
        async with p.acquire() as conn:
            prices = await conn.fetch("SELECT * FROM prices")
            user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", event.sender_id)

        price_map = {x['type']: x['price'] for x in prices}
        is_vip = user['is_vip'] if user else False
        balance = float(user['balance']) if user and user['balance'] else 0

        mode_config = {
            "normal": {"need": 1, "price": price_map.get('full', 5), "name": "普通模式"},
            "dual": {"need": 2, "price": price_map.get('dual', 8), "name": "双账号模式"},
            "multi": {"need": 3, "price": 0, "name": "多账号模式"},
            "monitor": {"need": 1, "price": 0, "name": "实时监控"}
        }

        config = mode_config.get(mode, {"need": 1, "price": 5, "name": "普通模式"})

        if not is_vip and mode in ["multi", "monitor"]:
            await event.reply("❌ 该模式仅VIP可用")
            return

        if config["price"] > 0 and balance < config["price"]:
            await event.reply(
                f"❌ 余额不足\n\n"
                f"需要: ¥{config['price']}\n"
                f"余额: ¥{balance}\n\n"
                f"请先充值",
                buttons=[[Button.inline("💰 充值", "recharge")]]
            )
            return

        if mode == "monitor":
            async with p.acquire() as conn:
                await conn.execute(
                    "INSERT INTO user_states (telegram_id, mode) VALUES ($1,$2) ON CONFLICT (telegram_id) DO UPDATE SET mode=$2",
                    event.sender_id, "monitor"
                )
            await account_selector.show_account_selection(event, mode, config["name"], config["need"], config["price"])
        else:
            await show_clone_type(event, mode, config["name"], config["need"], config["price"])

    async def show_clone_type(event, mode_type, mode_name, need_count, price):
        msg = f"✅ 已选择: {mode_name}\n\n"
        msg += f"📊 需要 {need_count} 个账号\n"
        msg += f"💰 费用: ¥{price}\n\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        msg += "📋 **请选择克隆方式：**\n\n"

        buttons = [
            [Button.inline("📥 克隆全部", f"clone_type_all_{mode_type}_{need_count}_{price}")],
            [Button.inline("🔗 从链接开始", f"clone_type_link_{mode_type}_{need_count}_{price}")]
        ]

        await event.reply(msg, buttons=buttons)

    @bot.on(events.CallbackQuery(pattern=r"clone_type_all_(\w+)_(\d+)_([\d.]+)"))
    async def cb_clone_type_all(event):
        mode_type = event.pattern_match.group(1)
        if isinstance(mode_type, bytes):
            mode_type = mode_type.decode('utf-8')
        need_count = int(event.pattern_match.group(2))
        price = float(event.pattern_match.group(3))

        p = await get_pool()
        async with p.acquire() as conn:
            await conn.execute(
                "INSERT INTO user_states (telegram_id, mode) VALUES ($1,$2) ON CONFLICT (telegram_id) DO UPDATE SET mode=$2",
                event.sender_id, f"{mode_type}_full"
            )
        try:
            await event.delete()
        except:
            pass

        await account_selector.show_account_selection(event, mode_type, f"{mode_type}_full", need_count, price)

    @bot.on(events.CallbackQuery(pattern=r"clone_type_link_(\w+)_(\d+)_([\d.]+)"))
    async def cb_clone_type_link(event):
        mode_type = event.pattern_match.group(1)
        if isinstance(mode_type, bytes):
            mode_type = mode_type.decode('utf-8')
        need_count = int(event.pattern_match.group(2))
        price = float(event.pattern_match.group(3))

        p = await get_pool()
        async with p.acquire() as conn:
            await conn.execute(
                "INSERT INTO user_states (telegram_id, mode) VALUES ($1,$2) ON CONFLICT (telegram_id) DO UPDATE SET mode=$2",
                event.sender_id, f"{mode_type}_link"
            )
        try:
            await event.delete()
        except:
            pass

        await account_selector.show_account_selection(event, mode_type, f"{mode_type}_link", need_count, price)

    @bot.on(events.NewMessage(pattern=r'^@\S+\s+@\S+'))
    async def handle_input(event):
        if not event.is_private:
            return
        text = event.text.strip()
        if text.startswith('/'):
            return
        parts = text.split()
        if len(parts) < 2:
            return

        p = await get_pool()
        async with p.acquire() as conn:
            state = await conn.fetchrow("SELECT mode FROM user_states WHERE telegram_id=$1", event.sender_id)
            selected = await conn.fetchrow("SELECT account_id FROM user_selected_account WHERE telegram_id=$1", event.sender_id)

        if not state or not selected:
            await show_mode_selection(event, reply=True)
            return

        mode_type = state["mode"]
        account_id = selected["account_id"]
        src, dst = parts[0], parts[1]

        is_link_mode = "_link" in mode_type
        base_mode = mode_type.replace("_link", "").replace("_full", "")

        start_msg_id = None
        if is_link_mode:
            if len(parts) < 3:
                await event.reply(
                    "❌ 需要帖子链接\n\n"
                    "格式：`@源频道 @目标频道 帖子链接`\n"
                    "示例：`@source @target https://t.me/source/123`"
                )
                return
            link = parts[2]
            m = re.search(r'/(\d+)(?:[?/].*)?$', link)
            if m:
                start_msg_id = int(m.group(1))
            else:
                await event.reply("❌ 无法解析帖子链接，请提供包含消息ID的链接。")
                return

        async with p.acquire() as conn:
            account = await conn.fetchrow("SELECT * FROM tg_accounts WHERE id=$1", account_id)

        if not account:
            await event.reply("❌ 账号不存在")
            return

        src_ok, dst_in, dst_admin = await check_channels(account, src, dst)

        async with p.acquire() as conn:
            tid = await conn.fetchval(
                """
                INSERT INTO clone_tasks 
                (user_telegram_id, account_id, source_channel, target_channel, status, task_type, start_msg_id)
                VALUES ($1,$2,$3,$4,'checking',$5,$6)
                RETURNING id
                """,
                event.sender_id, account_id, src, dst, base_mode, start_msg_id
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

        msg = f"📋 **任务 #{tid}**\n\n"
        msg += f"👤 账号: {username_display}\n"
        msg += f"📥 源频道: {'✅ 可读取' if src_ok else '❌ 无法读取'}\n"
        msg += f"📤 目标频道: {'✅ 在频道' if dst_in else '❌ 不在'} | {'✅ 有权限' if dst_admin else '❌ 无权限'}\n\n"

        buttons = []
        if src_ok and dst_admin:
            msg += "✅ 检查通过！"
            buttons.append([Button.inline("🚀 开始克隆", f"start_clone_{tid}")])
        else:
            if not dst_in:
                msg += "❌ 账号不在目标频道\n"
            elif not dst_admin:
                msg += "⚠️ 账号在频道但无管理权限\n请设为管理员后重新检查\n"
            buttons.append([Button.inline("🚀 加入频道", f"auto_join_{tid}")])
            buttons.append([Button.inline("🔍 重新检查", f"recheck_{tid}")])
        buttons.append([Button.inline("❌ 取消退款", f"cancel_refund_{tid}")])

        try:
            await event.delete()
        except:
            pass

        await event.reply(msg, buttons=buttons)

        async with p.acquire() as conn:
            await conn.execute("DELETE FROM user_states WHERE telegram_id=$1", event.sender_id)

    @bot.on(events.CallbackQuery(pattern=r"recheck_(\d+)"))
    async def cb_recheck(event):
        tid = int(event.pattern_match.group(1))
        await event.answer("🔍 检查中...")
        p = await get_pool()
        async with p.acquire() as conn:
            task = await conn.fetchrow("SELECT * FROM clone_tasks WHERE id=$1", tid)
            account = await conn.fetchrow("SELECT * FROM tg_accounts WHERE id=$1", task["account_id"])

        src_ok, dst_in, dst_admin = await check_channels(account, task["source_channel"], task["target_channel"])

        msg = f"📋 **任务 #{tid}**\n\n"
        msg += f"📥 源频道: {'✅ 可读取' if src_ok else '❌ 无法读取'}\n"
        msg += f"📤 目标频道: {'✅ 在频道' if dst_in else '❌ 不在'} | {'✅ 有权限' if dst_admin else '❌ 无权限'}\n\n"

        buttons = []
        if src_ok and dst_admin:
            msg += "✅ 通过！"
            buttons.append([Button.inline("🚀 开始克隆", f"start_clone_{tid}")])
        else:
            buttons.append([Button.inline("🚀 加入频道", f"auto_join_{tid}")])
            buttons.append([Button.inline("🔍 重新检查", f"recheck_{tid}")])
        buttons.append([Button.inline("❌ 取消退款", f"cancel_refund_{tid}")])

        try:
            await event.edit(msg, buttons=buttons)
        except:
            await event.reply(msg, buttons=buttons)

    @bot.on(events.CallbackQuery(pattern=r"auto_join_(\d+)"))
    async def cb_auto_join(event):
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
                await event.edit("✅ 已加入，请重新检查", buttons=[[Button.inline("🔍 重新检查", f"recheck_{tid}")]])
            except:
                await event.reply("✅ 已加入，请重新检查", buttons=[[Button.inline("🔍 重新检查", f"recheck_{tid}")]])
        except:
            try:
                await client.disconnect()
            except:
                pass
            try:
                await event.edit("❌ 无法加入\n请手动拉入并设为管理员", buttons=[[Button.inline("🔍 重新检查", f"recheck_{tid}")]])
            except:
                await event.reply("❌ 无法加入\n请手动拉入并设为管理员", buttons=[[Button.inline("🔍 重新检查", f"recheck_{tid}")]])

    @bot.on(events.CallbackQuery(pattern=r"start_clone_(\d+)"))
    async def cb_start(event):
        tid = int(event.pattern_match.group(1))
        p = await get_pool()
        async with p.acquire() as conn:
            await conn.execute("UPDATE clone_tasks SET status='queued' WHERE id=$1", tid)
        await push_task(tid)
        try:
            await event.edit("🚀 克隆已开始！")
        except:
            await event.reply("🚀 克隆已开始！")

    @bot.on(events.CallbackQuery(pattern=r"cancel_refund_(\d+)"))
    async def cb_cancel(event):
        tid = int(event.pattern_match.group(1))
        p = await get_pool()
        async with p.acquire() as conn:
            account = await conn.fetchrow("SELECT * FROM tg_accounts WHERE assigned_task_id=$1", tid)
            if account:
                await conn.execute("UPDATE tg_accounts SET is_assigned=FALSE, assigned_task_id=NULL WHERE id=$1", account["id"])
            await conn.execute("UPDATE clone_tasks SET status='cancelled' WHERE id=$1", tid)
        try:
            await event.edit("已取消，账号已释放")
        except:
            await event.reply("已取消，账号已释放")