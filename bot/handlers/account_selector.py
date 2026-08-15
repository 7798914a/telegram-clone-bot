from telethon import events, Button
from models import get_pool
import logging

logger = logging.getLogger(__name__)

async def get_all_available_accounts():
    p = await get_pool()
    async with p.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM tg_accounts WHERE status='connected' AND (is_assigned IS NULL OR is_assigned=FALSE) ORDER BY id ASC"
        )

def get_account_button_display(acc):
    """按钮显示：优先手机尾号，无手机号显示用户名，最后显示ID"""
    phone = acc.get('phone')
    if phone:
        return f"尾号 {str(phone)[-4:]}"
    username = acc.get('username')
    if username:
        return username
    return f"ID:{acc['id']}"

def get_account_detail_display(acc):
    """详情显示：优先用户名，其次完整手机号，最后ID"""
    if acc.get('username'):
        return acc['username']
    if acc.get('phone'):
        return acc['phone']
    return f"ID:{acc['id']}"

async def show_account_selection(event, mode_type, mode_name, need_count, price, callback_prefix="accsel"):
    if isinstance(mode_type, bytes):
        mode_type = mode_type.decode('utf-8')
    if isinstance(mode_name, bytes):
        mode_name = mode_name.decode('utf-8')

    accounts = await get_all_available_accounts()
    if not accounts:
        msg = "❌ 没有空闲账号，请稍后再试"
        try:
            await event.edit(msg)
        except:
            await event.reply(msg)
        return

    p = await get_pool()
    async with p.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", event.sender_id)

    balance = float(user['balance']) if user and user['balance'] else 0
    msg = f"✅ **{mode_name}**\n\n"
    msg += f"📊 建议需要 {need_count} 个账号"
    if mode_type == "dual":
        msg += "（选主账号，系统自动配备用）"
    elif mode_type == "multi":
        msg += "（选主账号，系统自动分配其余备用账号）"
    msg += f"\n💰 费用: ¥{price}\n"
    msg += f"💳 余额: ¥{balance}\n\n"
    msg += "请点击选择账号（选择后立即锁定）：\n\n"
    msg += "⚠️ 请确保所选账号已设置用户名（@username），否则无法拉入频道。"

    buttons = []
    for acc in accounts:
        button_text = get_account_button_display(acc)
        buttons.append([
            Button.inline(
                f"👤 {button_text}",
                f"{callback_prefix}_{mode_type}_{acc['id']}"
            )
        ])

    try:
        await event.edit(msg, buttons=buttons)
    except:
        await event.reply(msg, buttons=buttons)

def register(bot):
    @bot.on(events.CallbackQuery(pattern=r"accsel_(\w+)_(\d+)"))
    async def cb_account_selected(event):
        try:
            await event.answer()
        except:
            pass

        mode_type = event.pattern_match.group(1)
        if isinstance(mode_type, bytes):
            mode_type = mode_type.decode('utf-8')
        account_id = int(event.pattern_match.group(2))

        try:
            p = await get_pool()
            async with p.acquire() as conn:
                main_account = await conn.fetchrow(
                    "SELECT * FROM tg_accounts WHERE id=$1 AND (is_assigned IS NULL OR is_assigned=FALSE)",
                    account_id
                )
                if not main_account:
                    await event.answer("❌ 账号已被占用，请重新选择", alert=True)
                    return

                user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id=$1", event.sender_id)
                prices = await conn.fetch("SELECT * FROM prices")
                price_map = {r['type']: r['price'] for r in prices}

                if mode_type == "normal":
                    price = price_map.get('full', 5)
                    need_extra = 0
                elif mode_type == "dual":
                    price = price_map.get('dual', 8)
                    need_extra = 1
                elif mode_type == "multi":
                    price = 0
                    need_extra = 2
                elif mode_type == "monitor":
                    price = 0
                    need_extra = 0
                elif mode_type == "delete_all":
                    price = price_map.get('delete_all', 10)
                    need_extra = 0
                else:
                    price = price_map.get('full', 5)
                    need_extra = 0

                balance = float(user['balance']) if user and user['balance'] else 0
                if price > 0 and balance < price:
                    await event.answer(f"❌ 余额不足，需要 ¥{price}", alert=True)
                    return

                backup_accounts = []
                if need_extra > 0:
                    backup_accounts = await conn.fetch(
                        "SELECT * FROM tg_accounts WHERE status='connected' AND id != $1 AND (is_assigned IS NULL OR is_assigned=FALSE) ORDER BY id ASC LIMIT $2",
                        account_id, need_extra
                    )
                    if len(backup_accounts) < need_extra:
                        await event.answer(f"❌ 备用账号不足，需要 {need_extra} 个，只有 {len(backup_accounts)} 个", alert=True)
                        return

                if price > 0:
                    await conn.execute(
                        "UPDATE users SET balance = balance - $1 WHERE telegram_id=$2",
                        price, event.sender_id
                    )
                    await conn.execute(
                        "INSERT INTO payments (telegram_id, amount, status, note) VALUES ($1,$2,'approved',$3)",
                        event.sender_id, -price, f"{mode_type} 扣费"
                    )

                all_ids = [account_id] + [ba['id'] for ba in backup_accounts]
                for aid in all_ids:
                    await conn.execute(
                        "UPDATE tg_accounts SET is_assigned=TRUE WHERE id=$1",
                        aid
                    )

                await conn.execute(
                    "INSERT INTO user_selected_account (telegram_id, account_id) VALUES ($1,$2) ON CONFLICT (telegram_id) DO UPDATE SET account_id=$2",
                    event.sender_id, account_id
                )

                if mode_type == "dual" and backup_accounts:
                    await conn.execute(
                        "INSERT INTO user_selected_backup (telegram_id, backup_account_id) VALUES ($1,$2) ON CONFLICT (telegram_id) DO UPDATE SET backup_account_id=$2",
                        event.sender_id, backup_accounts[0]['id']
                    )
                elif mode_type == "multi" and backup_accounts:
                    backup_ids = [ba['id'] for ba in backup_accounts]
                    await conn.execute(
                        "INSERT INTO user_selected_backup_multi (telegram_id, backup_account_ids) VALUES ($1,$2) ON CONFLICT (telegram_id) DO UPDATE SET backup_account_ids=$2",
                        event.sender_id, backup_ids
                    )

            try:
                await event.delete()
            except:
                pass

            detail = get_account_detail_display(main_account)
            if main_account.get('username'):
                pull_instruction = f"请先将账号 @{detail} 拉入目标频道，并授予相应权限（至少发送消息）。"
            else:
                pull_instruction = "⚠️ 该账号未设置用户名，请先在 Telegram 客户端为该账号设置用户名，然后再拉入频道。"

            if mode_type == "delete_all":
                prompt = f"✅ 已选择并锁定账号：{detail}\n\n{pull_instruction}\n\n请发送要清空的目标频道：\n`@目标频道` 或 `https://t.me/目标频道`"
            elif mode_type == "dual":
                backup_detail = get_account_detail_display(backup_accounts[0]) if backup_accounts else ""
                prompt = f"✅ 已锁定双账号模式\n主账号: {detail}\n备用账号: {backup_detail}\n\n{pull_instruction}\n\n请发送：\n`@源频道 @目标频道`"
            elif mode_type == "multi":
                backup_details = ", ".join([get_account_detail_display(ba) for ba in backup_accounts]) if backup_accounts else ""
                prompt = f"✅ 已锁定多账号模式\n主账号: {detail}\n备用账号: {backup_details}\n\n{pull_instruction}\n\n请发送：\n`@源频道 @目标频道`"
            elif mode_type == "monitor":
                prompt = f"✅ 已锁定实时监控账号：{detail}\n\n{pull_instruction}\n\n请发送：\n`@源频道 @目标频道`"
            else:
                prompt = f"✅ 已锁定账号：{detail}\n\n{pull_instruction}\n\n请发送：\n`@源频道 @目标频道`"

            await event.respond(prompt, buttons=[[Button.inline("❌ 取消并释放", f"release_{mode_type}_{account_id}")]])

        except Exception as e:
            logger.error(f"账号选择处理错误: {e}")
            try:
                await event.answer("❌ 操作失败，请重试", alert=True)
            except:
                pass

    @bot.on(events.CallbackQuery(pattern=r"release_(normal|dual|multi|monitor|delete_all)_(\d+)"))
    async def cb_release_account(event):
        try:
            await event.answer()
        except:
            pass
        mode_type = event.pattern_match.group(1)
        if isinstance(mode_type, bytes):
            mode_type = mode_type.decode('utf-8')
        account_id = int(event.pattern_match.group(2))

        try:
            p = await get_pool()
            async with p.acquire() as conn:
                await conn.execute("UPDATE tg_accounts SET is_assigned=FALSE, assigned_task_id=NULL WHERE id=$1", account_id)
                if mode_type == "dual":
                    backup = await conn.fetchrow("SELECT backup_account_id FROM user_selected_backup WHERE telegram_id=$1", event.sender_id)
                    if backup:
                        await conn.execute("UPDATE tg_accounts SET is_assigned=FALSE, assigned_task_id=NULL WHERE id=$1", backup["backup_account_id"])
                        await conn.execute("DELETE FROM user_selected_backup WHERE telegram_id=$1", event.sender_id)
                elif mode_type == "multi":
                    backup = await conn.fetchrow("SELECT backup_account_ids FROM user_selected_backup_multi WHERE telegram_id=$1", event.sender_id)
                    if backup:
                        for bid in backup["backup_account_ids"]:
                            await conn.execute("UPDATE tg_accounts SET is_assigned=FALSE, assigned_task_id=NULL WHERE id=$1", bid)
                        await conn.execute("DELETE FROM user_selected_backup_multi WHERE telegram_id=$1", event.sender_id)
                await conn.execute("DELETE FROM user_selected_account WHERE account_id=$1", account_id)
                await conn.execute("DELETE FROM user_states WHERE telegram_id=$1", event.sender_id)

            try:
                await event.delete()
            except:
                pass
            await event.respond("✅ 已释放账号")
        except Exception as e:
            logger.error(f"释放账号错误: {e}")
            try:
                await event.answer("❌ 释放失败", alert=True)
            except:
                pass