import asyncio
import os
import re
import random
import traceback
import logging
from collections import defaultdict
from telethon import TelegramClient
from telethon.errors import FloodWaitError, WorkerBusyTooLongRetryError
from config import SESSION_DIR

logging.basicConfig(level=logging.INFO, format='%(asctime)s [Engine] %(message)s')
logger = logging.getLogger(__name__)

bot_instance = None

async def notify_user(user_id, text):
    if bot_instance:
        try:
            await bot_instance.send_message(user_id, text)
            logger.info(f"已通知用户 {user_id}: {text[:50]}")
        except Exception as e:
            logger.error(f"通知用户 {user_id} 失败: {e}")
    else:
        logger.warning("bot_instance 未设置，无法发送通知")

def get_proxy(account):
    """根据账号记录返回 Telethon proxy 参数，无代理则返回 None"""
    if account.get('proxy_host') and account.get('proxy_port'):
        proxy_type = account.get('proxy_type') or 'socks5'
        if proxy_type == 'http':
            return ("http", account['proxy_host'], int(account['proxy_port']))
        else:
            # 默认 socks5
            if account.get('proxy_username') and account.get('proxy_password'):
                return ("socks5", account['proxy_host'], int(account['proxy_port']), True, account['proxy_username'], account['proxy_password'])
            else:
                return ("socks5", account['proxy_host'], int(account['proxy_port']))
    return None

async def safe_start_client(client, phone):
    """尝试启动客户端，如果代理连接失败则回退到无代理重试一次"""
    try:
        await client.start(phone=phone)
        return client
    except Exception as e:
        logger.warning(f"代理连接失败，尝试无代理直连: {e}")
        # 如果失败，且使用了代理，则尝试去除代理重新连接
        if client.proxy:
            try:
                await client.disconnect()
            except:
                pass
            # 创建新的无代理客户端
            session = client.session
            api_id = client.api_id
            api_hash = client.api_hash
            client_no_proxy = TelegramClient(session, api_id, api_hash)
            await client_no_proxy.start(phone=phone)
            return client_no_proxy
        else:
            raise

async def should_filter(msg, pool):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM settings WHERE key IN ('filter_ads','filter_buttons','filter_links','filter_mentions','ad_keywords','max_mentions')")
    settings = {r['key']: r['value'] for r in rows}

    text = getattr(msg, 'text', '') or getattr(msg, 'message', '') or ''
    buttons = getattr(msg, 'reply_markup', None)

    if settings.get('filter_buttons') == '1' and buttons:
        return True, "有按钮"

    has_link = bool(re.search(r'https?://', text))
    has_real_content = bool(re.sub(r'https?://\S+|@\w+|\s', '', text).strip())
    if settings.get('filter_links') == '1' and has_link and not has_real_content:
        return True, "纯链接"

    if settings.get('filter_ads') == '1':
        keywords = [k.strip() for k in settings.get('ad_keywords', '').split(',') if k.strip()]
        for kw in keywords:
            if kw in text:
                return True, f"广告词:{kw}"

    if settings.get('filter_mentions') == '1':
        max_m = int(settings.get('max_mentions', '3'))
        mention_count = len(re.findall(r'@\w+', text))
        if mention_count > max_m:
            return True, f"@{mention_count}个"

    return False, None

def get_session_path(account_id):
    return os.path.join(SESSION_DIR, f"account_{account_id}")

def clean_text(text):
    if not text:
        return ""
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r't\.me/\S+', '', text)
    text = re.sub(r'@\w+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:4000]

async def update_account_username(pool, account_id, client):
    try:
        me = await client.get_me()
        if me.username:
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE tg_accounts SET username=$1 WHERE id=$2",
                    me.username, account_id
                )
            logger.info(f"已更新账号 {account_id} 的用户名为 @{me.username}")
    except Exception as e:
        logger.warning(f"更新账号 {account_id} 用户名失败: {e}")

async def allocate_account(pool):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE tg_accounts SET is_assigned=FALSE, assigned_task_id=NULL 
            WHERE assigned_task_id IN (SELECT id FROM clone_tasks WHERE status NOT IN ('running','checking','waiting_join'))
        """)
        account = await conn.fetchrow(
            "SELECT * FROM tg_accounts WHERE status='connected' AND (is_assigned IS NULL OR is_assigned=FALSE) ORDER BY id ASC LIMIT 1"
        )
        if account:
            await conn.execute("UPDATE tg_accounts SET is_assigned=TRUE WHERE id=$1", account["id"])
            logger.info(f"[分配] 账号 {account['phone']} (ID:{account['id']})")
            return account
    return None

async def release_account(pool, account_id):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE tg_accounts SET is_assigned=FALSE, assigned_task_id=NULL WHERE id=$1", account_id)
    logger.info(f"[释放] 账号 ID:{account_id}")

async def check_account_in_channel(user_client, channel_input):
    try:
        entity = await user_client.get_entity(channel_input)
        return True, entity.title
    except:
        return False, None

async def insert_cloned_post(pool, task_id, source_msg_id, target_msg_id):
    last_exc = None
    for attempt in range(3):
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO cloned_posts (task_id, source_msg_id, target_msg_id, cloned_at) VALUES ($1,$2,$3,NOW()) ON CONFLICT DO NOTHING",
                    task_id, source_msg_id, target_msg_id
                )
            return True
        except Exception as e:
            last_exc = e
            logger.warning(f"插入克隆记录失败 (尝试 {attempt+1}/3): {e}")
            await asyncio.sleep(2)
    raise last_exc

async def send_group(client, target, group_msgs, prefix="", suffix=""):
    media = []
    caption = ""
    for m in sorted(group_msgs.values(), key=lambda x: x.id):
        if getattr(m, 'photo', None): media.append(m.photo)
        elif getattr(m, 'video', None): media.append(m.video)
        elif getattr(m, 'document', None): media.append(m.document)
        txt = getattr(m, 'text', '') or getattr(m, 'message', '') or ''
        if txt and not caption: caption = txt
    logger.info(f"[媒体组] 收集到 {len(media)} 个媒体, caption长度={len(caption)}")
    if not media:
        return None

    final_caption = (prefix + clean_text(caption) + suffix)[:1024] if caption else ""
    
    for attempt in range(3):
        try:
            result = await client.send_file(target, media, group=True, caption=final_caption or '')
            if isinstance(result, list):
                return result[0] if result else None
            return result
        except WorkerBusyTooLongRetryError as e:
            logger.warning(f"[媒体组] 服务器繁忙，尝试 {attempt+1}/3，等待重试...")
            await asyncio.sleep(random.uniform(10, 20))
        except FloodWaitError as e:
            logger.warning(f"[媒体组] 限速 {e.seconds}s，等待...")
            await asyncio.sleep(e.seconds + 10)
            return None
        except Exception as e:
            logger.error(f"[媒体组] 发送失败: {e}")
            return None
    logger.error("[媒体组] 重试多次仍失败")
    return None

async def handle_delete_all_task(task_id):
    from models import get_pool
    pool = await get_pool()
    logger.info(f"🗑️ 删除任务 #{task_id} 开始")

    async with pool.acquire() as conn:
        task = await conn.fetchrow("SELECT * FROM clone_tasks WHERE id=$1", task_id)
        if not task:
            logger.error("任务不存在")
            return

        account = await conn.fetchrow(
            "SELECT * FROM tg_accounts WHERE id=$1",
            task["account_id"]
        )
        if not account:
            await conn.execute("UPDATE clone_tasks SET status='error', error_msg='账号不存在' WHERE id=$1", task_id)
            await notify_user(task["user_telegram_id"], f"❌ 删除任务 #{task_id} 出错：账号不存在")
            return

        client = TelegramClient(
            get_session_path(account["id"]),
            account["api_id"],
            account["api_hash"],
            proxy=get_proxy(account)
        )
        try:
            client = await safe_start_client(client, account["phone"])
            await update_account_username(pool, account["id"], client)
            logger.info(f"✅ 用户账号 {account['phone']} 已连接")

            entity = await client.get_entity(task["target_channel"])
            await conn.execute("UPDATE clone_tasks SET status='running' WHERE id=$1", task_id)

            messages = []
            async for msg in client.iter_messages(entity, limit=None):
                messages.append(msg.id)

            total = len(messages)
            logger.info(f"共发现 {total} 条消息")

            if total == 0:
                await conn.execute("UPDATE clone_tasks SET status='done', cloned=0, finished_at=NOW() WHERE id=$1", task_id)
                await release_account(pool, account["id"])
                await client.disconnect()
                await notify_user(task["user_telegram_id"], f"✅ 删除任务 #{task_id} 已完成，频道中无消息")
                return

            deleted = 0
            failed = 0
            for i in range(0, total, 100):
                batch = messages[i:i+100]
                try:
                    await client.delete_messages(entity, batch)
                    deleted += len(batch)
                    async with pool.acquire() as conn2:
                        await conn2.execute("UPDATE clone_tasks SET cloned=$1 WHERE id=$2", deleted, task_id)
                    logger.info(f"已删除 {deleted}/{total}")
                except Exception as e:
                    failed += len(batch)
                    logger.error(f"批量删除失败（任务 {task_id}）: {e}")
                await asyncio.sleep(1)

            if failed == 0:
                async with pool.acquire() as conn3:
                    await conn3.execute("UPDATE clone_tasks SET status='done', cloned=$1, finished_at=NOW() WHERE id=$2", deleted, task_id)
                await notify_user(task["user_telegram_id"], f"✅ 删除任务 #{task_id} 已完成，删除 {deleted} 条消息")
            else:
                async with pool.acquire() as conn4:
                    await conn4.execute("UPDATE clone_tasks SET status='done', cloned=$1, error_msg=$2, finished_at=NOW() WHERE id=$3", deleted, f"{failed} 条删除失败", task_id)
                await notify_user(task["user_telegram_id"], f"⚠️ 删除任务 #{task_id} 部分失败，成功 {deleted} 条，失败 {failed} 条")

            await release_account(pool, account["id"])
            await client.disconnect()

        except Exception as e:
            logger.error(f"删除任务 #{task_id} 失败: {e}")
            logger.error(traceback.format_exc())
            try:
                await client.disconnect()
            except:
                pass
            async with pool.acquire() as conn5:
                await conn5.execute("UPDATE clone_tasks SET status='error', error_msg=$1 WHERE id=$2", str(e)[:500], task_id)
            await notify_user(task["user_telegram_id"], f"❌ 删除任务 #{task_id} 出错：{str(e)[:200]}")
            await release_account(pool, account["id"])

async def run_dual_account_clone(task_id, account_ids):
    from models import get_pool
    pool = await get_pool()
    logger.info(f"🔄 双账号任务 #{task_id} 开始")

    async with pool.acquire() as conn:
        task = await conn.fetchrow("SELECT * FROM clone_tasks WHERE id=$1", task_id)
        if not task:
            logger.error("任务不存在")
            return

    accounts = []
    for aid in account_ids:
        async with pool.acquire() as conn:
            acc = await conn.fetchrow("SELECT * FROM tg_accounts WHERE id=$1", aid)
            if acc:
                accounts.append(acc)
                await conn.execute("UPDATE tg_accounts SET is_assigned=TRUE, assigned_task_id=$1 WHERE id=$2", task_id, aid)

    if len(accounts) < 1:
        logger.error("没有可用账号")
        await notify_user(task["user_telegram_id"], f"❌ 双账号任务 #{task_id} 出错：没有可用账号")
        return

    main_account = accounts[0]
    backup_account = accounts[1] if len(accounts) > 1 else None

    try:
        main_client = TelegramClient(
            get_session_path(main_account["id"]),
            main_account["api_id"],
            main_account["api_hash"],
            proxy=get_proxy(main_account)
        )
        main_client = await safe_start_client(main_client, main_account["phone"])
        await update_account_username(pool, main_account["id"], main_client)
        logger.info(f"✅ 主账号已连接")
    except Exception as e:
        logger.error(f"❌ 主账号连接失败: {e}")
        await notify_user(task["user_telegram_id"], f"❌ 双账号任务 #{task_id} 出错：主账号连接失败")
        return

    backup_client = None
    if backup_account:
        try:
            backup_client = TelegramClient(
                get_session_path(backup_account["id"]),
                backup_account["api_id"],
                backup_account["api_hash"],
                proxy=get_proxy(backup_account)
            )
            backup_client = await safe_start_client(backup_client, backup_account["phone"])
            await update_account_username(pool, backup_account["id"], backup_client)
            logger.info(f"✅ 备用账号已连接")
        except Exception as e:
            logger.warning(f"备用账号连接失败: {e}")
            backup_client = None

    current_client = main_client
    current_account = main_account
    use_backup = False

    source = await main_client.get_entity(task["source_channel"])
    target = await main_client.get_entity(task["target_channel"])

    prefix = task.get("prefix_text") or ""
    suffix = task.get("suffix_text") or ""
    max_posts = task["max_posts"] if task["max_posts"] else 0
    cloned = 0
    skipped = 0
    processed_groups = set()

    group_index = defaultdict(list)
    scanned = await main_client.get_messages(source, limit=10000)
    for m in scanned:
        gid = getattr(m, 'grouped_id', None)
        if gid:
            group_index[gid].append(m)
    logger.info(f"找到 {len(group_index)} 个媒体组")

    start_msg_id = task.get("start_msg_id")
    async with pool.acquire() as conn:
        last_processed = await conn.fetchval("SELECT last_processed_msg_id FROM clone_tasks WHERE id=$1", task_id) or start_msg_id

    iter_kwargs = {"limit": None}
    if last_processed:
        iter_kwargs["min_id"] = last_processed - 1
        iter_kwargs["reverse"] = True
    elif start_msg_id:
        iter_kwargs["min_id"] = start_msg_id - 1
        iter_kwargs["reverse"] = True

    try:
        async for msg in main_client.iter_messages(source, **iter_kwargs):
            if max_posts > 0 and cloned >= max_posts:
                break

            async with pool.acquire() as conn:
                already_cloned = await conn.fetchval("SELECT id FROM cloned_posts WHERE task_id=$1 AND source_msg_id=$2", task_id, msg.id)
            if already_cloned:
                continue

            is_filtered, reason = await should_filter(msg, pool)
            if is_filtered:
                skipped += 1
                continue

            gid = getattr(msg, 'grouped_id', None)
            caption = clean_text(getattr(msg, 'text', '') or '')[:2000]

            try:
                target_msg_id = None
                if gid:
                    if gid in processed_groups:
                        continue
                    processed_groups.add(gid)
                    group_msgs = group_index.get(gid, [msg])
                    same_group = {m.id: m for m in group_msgs if m is not None}
                    if same_group:
                        r = await send_group(current_client, target, same_group, prefix, suffix)
                        if r:
                            target_msg_id = r.id
                            async with pool.acquire() as conn:
                                for mid in same_group.keys():
                                    await insert_cloned_post(pool, task_id, mid, target_msg_id)
                                await conn.execute("UPDATE clone_tasks SET last_processed_msg_id=$1 WHERE id=$2", msg.id, task_id)
                            cloned += 1
                    else:
                        skipped += 1
                        continue
                elif getattr(msg, 'photo', None):
                    r = await current_client.send_file(target, msg.photo, caption=caption)
                    target_msg_id = r.id if r else None
                elif getattr(msg, 'video', None):
                    r = await current_client.send_file(target, msg.video, caption=caption)
                    target_msg_id = r.id if r else None
                elif caption:
                    r = await current_client.send_message(target, caption)
                    target_msg_id = r.id if r else None
                else:
                    skipped += 1
                    continue

                if target_msg_id:
                    if not gid:
                        await insert_cloned_post(pool, task_id, msg.id, target_msg_id)
                    cloned += 1
                    logger.info(f"✅ {current_account['phone']} 克隆 msg_id={msg.id} ({cloned}/{max_posts or '∞'})")
                    async with pool.acquire() as conn:
                        await conn.execute("UPDATE clone_tasks SET last_processed_msg_id=$1 WHERE id=$2", msg.id, task_id)
                else:
                    skipped += 1

                await asyncio.sleep(random.uniform(15, 25))

            except FloodWaitError as e:
                logger.warning(f"⏳ 账号 {current_account['phone']} 限速 {e.seconds}s，暂停等待...")
                await asyncio.sleep(e.seconds + 20)
                async with pool.acquire() as conn:
                    await conn.execute("UPDATE clone_tasks SET cloned=$1, skipped=$2, last_processed_msg_id=$3 WHERE id=$4", cloned, skipped, msg.id, task_id)
            except Exception as e:
                logger.error(f"克隆失败 msg_id={msg.id}: {e}")
                skipped += 1
                async with pool.acquire() as conn:
                    await conn.execute("UPDATE clone_tasks SET status='error', error_msg=$1 WHERE id=$2", str(e)[:500], task_id)
                await notify_user(task["user_telegram_id"], f"❌ 双账号任务 #{task_id} 出错：{str(e)[:200]}")
                return

        logger.info(f"双账号任务完成：{cloned}成功，{skipped}跳过")
        async with pool.acquire() as conn:
            await conn.execute("UPDATE clone_tasks SET status='done', cloned=$1, skipped=$2, finished_at=NOW() WHERE id=$3", cloned, skipped, task_id)
        await notify_user(task["user_telegram_id"], f"✅ 您的双账号克隆任务 #{task_id} 已完成！克隆 {cloned} 条，跳过 {skipped} 条。")
    except Exception as e:
        logger.error(f"任务异常: {e}")
    finally:
        await release_account(pool, main_account["id"])
        if backup_account:
            await release_account(pool, backup_account["id"])
        logger.info("✅ 所有账号已释放")

async def run_multi_account_clone(task_id, account_ids):
    from models import get_pool
    pool = await get_pool()
    logger.info(f"🔄 多账号任务 #{task_id} 开始，使用 {len(account_ids)} 个账号")

    async with pool.acquire() as conn:
        task = await conn.fetchrow("SELECT * FROM clone_tasks WHERE id=$1", task_id)
        if not task:
            logger.error("任务不存在")
            return

    accounts = []
    for aid in account_ids:
        async with pool.acquire() as conn:
            acc = await conn.fetchrow("SELECT * FROM tg_accounts WHERE id=$1", aid)
            if acc:
                accounts.append(acc)
                await conn.execute("UPDATE tg_accounts SET is_assigned=TRUE, assigned_task_id=$1 WHERE id=$2", task_id, aid)

    if len(accounts) < 2:
        logger.warning("多账号模式需要至少2个账号")
        await notify_user(task["user_telegram_id"], f"❌ 多账号任务 #{task_id} 出错：备用账号不足")
        return

    clients = []
    for acc in accounts:
        try:
            client = TelegramClient(
                get_session_path(acc["id"]),
                acc["api_id"],
                acc["api_hash"],
                proxy=get_proxy(acc)
            )
            client = await safe_start_client(client, acc["phone"])
            await update_account_username(pool, acc["id"], client)
            clients.append({"client": client, "account": acc, "available": True})
            logger.info(f"✅ 账号 {acc['phone']} 已连接")
        except Exception as e:
            logger.error(f"❌ 账号 {acc['phone']} 连接失败: {e}")

    if not clients:
        logger.error("没有可用账号")
        await notify_user(task["user_telegram_id"], f"❌ 多账号任务 #{task_id} 出错：没有可用账号")
        return

    source = await clients[0]["client"].get_entity(task["source_channel"])
    target = await clients[0]["client"].get_entity(task["target_channel"])

    prefix = task.get("prefix_text") or ""
    suffix = task.get("suffix_text") or ""
    max_posts = task["max_posts"] if task["max_posts"] else 0
    cloned = 0
    skipped = 0
    current_account_index = 0
    processed_groups = set()

    group_index = defaultdict(list)
    scanned = await clients[0]["client"].get_messages(source, limit=10000)
    for m in scanned:
        gid = getattr(m, 'grouped_id', None)
        if gid:
            group_index[gid].append(m)
    logger.info(f"找到 {len(group_index)} 个媒体组")

    start_msg_id = task.get("start_msg_id")
    async with pool.acquire() as conn:
        last_processed = await conn.fetchval("SELECT last_processed_msg_id FROM clone_tasks WHERE id=$1", task_id) or start_msg_id

    iter_kwargs = {"limit": None}
    if last_processed:
        iter_kwargs["min_id"] = last_processed - 1
        iter_kwargs["reverse"] = True
    elif start_msg_id:
        iter_kwargs["min_id"] = start_msg_id - 1
        iter_kwargs["reverse"] = True

    try:
        async for msg in clients[0]["client"].iter_messages(source, **iter_kwargs):
            if max_posts > 0 and cloned >= max_posts:
                break

            available_clients = [c for c in clients if c["available"]]
            if not available_clients:
                logger.warning("所有账号都限速了，等待60秒...")
                await asyncio.sleep(60)
                continue

            current_client = available_clients[current_account_index % len(available_clients)]
            current_account_index += 1

            async with pool.acquire() as conn:
                already_cloned = await conn.fetchval("SELECT id FROM cloned_posts WHERE task_id=$1 AND source_msg_id=$2", task_id, msg.id)
            if already_cloned:
                continue

            is_filtered, reason = await should_filter(msg, pool)
            if is_filtered:
                skipped += 1
                continue

            gid = getattr(msg, 'grouped_id', None)
            caption = clean_text(getattr(msg, 'text', '') or '')[:2000]

            try:
                target_msg_id = None
                if gid:
                    if gid in processed_groups:
                        continue
                    processed_groups.add(gid)
                    group_msgs = group_index.get(gid, [msg])
                    same_group = {m.id: m for m in group_msgs if m is not None}
                    if same_group:
                        r = await send_group(current_client["client"], target, same_group, prefix, suffix)
                        if r:
                            target_msg_id = r.id
                            async with pool.acquire() as conn:
                                for mid in same_group.keys():
                                    await insert_cloned_post(pool, task_id, mid, target_msg_id)
                                await conn.execute("UPDATE clone_tasks SET last_processed_msg_id=$1 WHERE id=$2", msg.id, task_id)
                            cloned += 1
                    else:
                        skipped += 1
                        continue
                elif getattr(msg, 'photo', None):
                    r = await current_client["client"].send_file(target, msg.photo, caption=caption)
                    target_msg_id = r.id if r else None
                elif getattr(msg, 'video', None):
                    r = await current_client["client"].send_file(target, msg.video, caption=caption)
                    target_msg_id = r.id if r else None
                elif caption:
                    r = await current_client["client"].send_message(target, caption)
                    target_msg_id = r.id if r else None
                else:
                    skipped += 1
                    continue

                if target_msg_id:
                    if not gid:
                        await insert_cloned_post(pool, task_id, msg.id, target_msg_id)
                    cloned += 1
                    logger.info(f"✅ {current_client['account']['phone']} 克隆 msg_id={msg.id} ({cloned}/{max_posts or '∞'})")
                    async with pool.acquire() as conn:
                        await conn.execute("UPDATE clone_tasks SET last_processed_msg_id=$1 WHERE id=$2", msg.id, task_id)
                else:
                    skipped += 1

                await asyncio.sleep(random.uniform(15, 25))

            except FloodWaitError as e:
                logger.warning(f"⏳ {current_client['account']['phone']} 限速 {e.seconds}s，标记为不可用")
                current_client["available"] = False
                async with pool.acquire() as conn:
                    await conn.execute("UPDATE clone_tasks SET cloned=$1, skipped=$2, last_processed_msg_id=$3 WHERE id=$4", cloned, skipped, msg.id, task_id)
            except Exception as e:
                logger.error(f"克隆失败 msg_id={msg.id}: {e}")
                skipped += 1
                async with pool.acquire() as conn:
                    await conn.execute("UPDATE clone_tasks SET status='error', error_msg=$1 WHERE id=$2", str(e)[:500], task_id)
                await notify_user(task["user_telegram_id"], f"❌ 多账号任务 #{task_id} 出错：{str(e)[:200]}")
                return

            if cloned % 10 == 0:
                for c in clients:
                    if not c["available"]:
                        try:
                            await c["client"].get_me()
                            c["available"] = True
                            logger.info(f"✅ 账号 {c['account']['phone']} 已恢复")
                        except:
                            pass

        logger.info(f"多账号任务完成：{cloned}成功，{skipped}跳过")
        async with pool.acquire() as conn:
            await conn.execute("UPDATE clone_tasks SET status='done', cloned=$1, skipped=$2, finished_at=NOW() WHERE id=$3", cloned, skipped, task_id)
        await notify_user(task["user_telegram_id"], f"✅ 您的多账号克隆任务 #{task_id} 已完成！克隆 {cloned} 条，跳过 {skipped} 条。")
    except Exception as e:
        logger.error(f"任务异常: {e}")
    finally:
        for acc in accounts:
            await release_account(pool, acc["id"])
        logger.info("✅ 所有账号已释放")

async def run_monitor_task(task_id):
    from models import get_pool
    pool = await get_pool()

    async with pool.acquire() as conn:
        task = await conn.fetchrow("SELECT * FROM clone_tasks WHERE id=$1", task_id)
        if not task: return

    account = await allocate_account(pool)
    if not account:
        logger.warning("[监控] 无空闲账号")
        async with pool.acquire() as conn:
            await conn.execute("UPDATE clone_tasks SET status='waiting_account' WHERE id=$1", task_id)
        await notify_user(task["user_telegram_id"], f"❌ 监控任务 #{task_id} 等待账号分配中，请稍后")
        return

    async with pool.acquire() as conn:
        await conn.execute("UPDATE clone_tasks SET account_id=$1, status='monitoring' WHERE id=$2", account["id"], task_id)
        await conn.execute("UPDATE tg_accounts SET assigned_task_id=$1 WHERE id=$2", task_id, account["id"])

    user_client = TelegramClient(
        get_session_path(account["id"]),
        account["api_id"],
        account["api_hash"],
        proxy=get_proxy(account)
    )
    user_client = await safe_start_client(user_client, account["phone"])
    await update_account_username(pool, account["id"], user_client)
    source = await user_client.get_entity(task["source_channel"])
    target = await user_client.get_entity(task["target_channel"])

    async with pool.acquire() as conn:
        last_msg_id = await conn.fetchval("SELECT last_processed_msg_id FROM clone_tasks WHERE id=$1", task_id) or 0

    if last_msg_id == 0:
        latest_first = await user_client.get_messages(source, limit=1)
        last_msg_id = latest_first[0].id if latest_first and len(latest_first) > 0 else 0
        logger.info(f"[监控] 任务#{task_id} 首次启动，起始ID: {last_msg_id}")
    else:
        logger.info(f"[监控] 任务#{task_id} 从断点恢复，起始ID: {last_msg_id}")

    group_index = defaultdict(list)
    logger.info("[监控] 建立媒体组索引...")
    async for m in user_client.iter_messages(source, limit=5000):
        gid = getattr(m, 'grouped_id', None)
        if gid:
            group_index[gid].append(m)
    logger.info(f"[监控] 索引完成，共 {len(group_index)} 个媒体组")
    logger.info(f"[监控] 开始监控 {source.title} → {target.title}")

    try:
        while True:
            async with pool.acquire() as conn:
                current = await conn.fetchval("SELECT status FROM clone_tasks WHERE id=$1", task_id)
                if current != "monitoring":
                    break

            new_messages = await user_client.get_messages(source, limit=50, min_id=last_msg_id)
            if new_messages:
                new_messages_sorted = sorted(new_messages, key=lambda x: x.id)
                for msg in new_messages_sorted:
                    async with pool.acquire() as conn:
                        already_cloned = await conn.fetchval("SELECT id FROM cloned_posts WHERE task_id=$1 AND source_msg_id=$2", task_id, msg.id)
                    if already_cloned:
                        logger.info(f"[监控] ⏭️ 跳过已克隆 msg_id={msg.id}")
                        last_msg_id = max(last_msg_id, msg.id)
                        continue

                    is_filtered, reason = await should_filter(msg, pool)
                    if is_filtered:
                        logger.info(f"[监控] 过滤 msg_id={msg.id}: {reason}")
                        last_msg_id = max(last_msg_id, msg.id)
                        continue

                    gid = getattr(msg, 'grouped_id', None)
                    caption = clean_text(getattr(msg, 'text', '') or '')[:2000]
                    try:
                        target_msg_id = None
                        if gid:
                            group_msgs = group_index.get(gid, [msg])
                            same = {m.id: m for m in group_msgs if m is not None}
                            if same:
                                result = await send_group(user_client, target, same)
                                if result:
                                    target_msg_id = result.id
                                    async with pool.acquire() as conn:
                                        for mid in same.keys():
                                            await insert_cloned_post(pool, task_id, mid, target_msg_id)
                            else:
                                last_msg_id = max(last_msg_id, msg.id)
                                continue
                        elif getattr(msg, 'photo', None):
                            result = await user_client.send_file(target, msg.photo, caption=caption)
                            target_msg_id = result.id if result else None
                        elif getattr(msg, 'video', None):
                            result = await user_client.send_file(target, msg.video, caption=caption)
                            target_msg_id = result.id if result else None
                        elif caption:
                            result = await user_client.send_message(target, caption)
                            target_msg_id = result.id if result else None
                        else:
                            last_msg_id = max(last_msg_id, msg.id)
                            continue

                        if target_msg_id:
                            if not gid:
                                await insert_cloned_post(pool, task_id, msg.id, target_msg_id)
                            async with pool.acquire() as conn:
                                await conn.execute("UPDATE clone_tasks SET cloned=cloned+1, last_processed_msg_id=$1 WHERE id=$2", msg.id, task_id)
                            logger.info(f"[监控] ✅ 已克隆 msg_id={msg.id}")
                        else:
                            logger.warning(f"[监控] ⚠️ 克隆结果为空 msg_id={msg.id}")

                        await asyncio.sleep(random.uniform(15, 25))

                    except FloodWaitError as e:
                        logger.warning(f"[监控] 限速 {e.seconds}s，暂停后从断点继续")
                        async with pool.acquire() as conn:
                            await conn.execute("UPDATE clone_tasks SET last_processed_msg_id=$1 WHERE id=$2", last_msg_id, task_id)
                        await asyncio.sleep(e.seconds + 30)
                        continue
                    except Exception as e:
                        logger.error(f"[监控] 克隆失败 msg_id={msg.id}: {e}")
                        continue

                    last_msg_id = max(last_msg_id, msg.id)
                    async with pool.acquire() as conn:
                        await conn.execute("UPDATE clone_tasks SET last_processed_msg_id=$1 WHERE id=$2", last_msg_id, task_id)

            await asyncio.sleep(180)

    except Exception as e:
        logger.error(f"[监控] 异常: {e}")
        logger.error(traceback.format_exc())
    finally:
        await user_client.disconnect()
        await release_account(pool, account["id"])
        async with pool.acquire() as conn:
            await conn.execute("UPDATE clone_tasks SET status='stopped', finished_at=NOW() WHERE id=$1", task_id)
            await conn.execute("UPDATE tg_accounts SET is_assigned=FALSE, assigned_task_id=NULL WHERE id=$1", account["id"])
        await notify_user(task["user_telegram_id"], f"🛑 监控任务 #{task_id} 已停止。")
        logger.info(f"[监控] 任务#{task_id} 已停止")

async def run_clone_task(task_id):
    from models import get_pool
    pool = await get_pool()
    logger.info(f"=== 任务 #{task_id} 开始 ===")

    async with pool.acquire() as conn:
        task = await conn.fetchrow("SELECT * FROM clone_tasks WHERE id=$1", task_id)
        if not task:
            logger.error("任务不存在")
            return
        if task.get("task_type") == "monitor":
            await run_monitor_task(task_id)
            return
        if task.get("task_type") == "delete_all":
            await handle_delete_all_task(task_id)
            return
        if task["status"] == "waiting_join":
            logger.info(f"任务 #{task_id} 等待用户拉入频道，跳过")
            return
        if task["status"] == "checking":
            logger.info(f"任务 #{task_id} 用户已确认，开始检测")

    # 获取任务类型和已选账号信息
    async with pool.acquire() as conn:
        task_type = await conn.fetchval("SELECT task_type FROM clone_tasks WHERE id=$1", task_id) or "full"
        main_account_id = await conn.fetchval("SELECT account_id FROM clone_tasks WHERE id=$1", task_id)
        account_ids = []
        if main_account_id:
            account_ids.append(main_account_id)

        if task_type == "dual":
            backup = await conn.fetchrow("SELECT backup_account_id FROM user_selected_backup WHERE telegram_id=$1", task["user_telegram_id"])
            if backup:
                account_ids.append(backup["backup_account_id"])
        elif task_type == "multi":
            backup_multi = await conn.fetchrow("SELECT backup_account_ids FROM user_selected_backup_multi WHERE telegram_id=$1", task["user_telegram_id"])
            if backup_multi:
                account_ids.extend(backup_multi["backup_account_ids"])

    if task_type == "multi" and len(account_ids) >= 2:
        await run_multi_account_clone(task_id, account_ids)
        return

    if task_type == "dual" and len(account_ids) >= 2:
        await run_dual_account_clone(task_id, account_ids)
        return

    # 单账号模式：优先使用任务中已锁定的账号
    if main_account_id:
        async with pool.acquire() as conn:
            account = await conn.fetchrow("SELECT * FROM tg_accounts WHERE id=$1", main_account_id)
            if not account:
                logger.warning(f"任务指定的账号 {main_account_id} 不存在")
                await conn.execute("UPDATE clone_tasks SET status='error' WHERE id=$1", task_id)
                await notify_user(task["user_telegram_id"], f"❌ 任务 #{task_id} 出错：指定账号不存在")
                return
            await conn.execute("UPDATE tg_accounts SET is_assigned=TRUE, assigned_task_id=$1 WHERE id=$2", task_id, account["id"])
    else:
        account = await allocate_account(pool)

    if not account:
        logger.warning("无空闲账号")
        async with pool.acquire() as conn:
            await conn.execute("UPDATE clone_tasks SET status='waiting_account' WHERE id=$1", task_id)
        await notify_user(task["user_telegram_id"], f"❌ 任务 #{task_id} 等待账号分配中，请稍后")
        return

    async with pool.acquire() as conn:
        await conn.execute("UPDATE clone_tasks SET account_id=$1, status='checking' WHERE id=$2", account["id"], task_id)
        await conn.execute("UPDATE tg_accounts SET assigned_task_id=$1 WHERE id=$2", task_id, account["id"])

    user_client = None
    try:
        session_file = get_session_path(account["id"])
        user_client = TelegramClient(
            session_file,
            account["api_id"],
            account["api_hash"],
            proxy=get_proxy(account)
        )
        user_client = await safe_start_client(user_client, account["phone"])
        await update_account_username(pool, account["id"], user_client)
        logger.info("用户账号已连接")

        ok, title = await check_account_in_channel(user_client, task["target_channel"])
        if not ok:
            logger.warning(f"账号不在目标频道 {task['target_channel']}")
            async with pool.acquire() as conn:
                await conn.execute("UPDATE clone_tasks SET status='need_join', error_msg='账号不在目标频道' WHERE id=$1", task_id)
            await notify_user(task["user_telegram_id"], f"❌ 任务 #{task_id} 出错：账号不在目标频道，请先拉入账号并设为管理员")
            await release_account(pool, account["id"])
            return

        logger.info(f"账号在目标频道: {title}")
        async with pool.acquire() as conn:
            await conn.execute("UPDATE clone_tasks SET status='running' WHERE id=$1", task_id)

        prefix = task.get("prefix_text") or ""
        suffix = task.get("suffix_text") or ""
        source = await user_client.get_entity(task["source_channel"])
        target = await user_client.get_entity(task["target_channel"])

        cloned = skipped = 0
        post_count = 0
        max_posts = task["max_posts"] if task["max_posts"] else 0
        processed_groups = set()
        pending_group = {}
        last_group_id = None

        group_index = defaultdict(list)
        scanned = await user_client.get_messages(source, limit=10000)
        for m in scanned:
            gid = getattr(m, 'grouped_id', None)
            if gid:
                group_index[gid].append(m)
        logger.info(f"找到 {len(group_index)} 个媒体组")

        start_msg_id = task.get("start_msg_id")
        async with pool.acquire() as conn:
            last_processed = await conn.fetchval("SELECT last_processed_msg_id FROM clone_tasks WHERE id=$1", task_id) or start_msg_id

        iter_kwargs = {"limit": None}
        if last_processed:
            iter_kwargs["min_id"] = last_processed - 1
            iter_kwargs["reverse"] = True
        elif start_msg_id:
            iter_kwargs["min_id"] = start_msg_id - 1
            iter_kwargs["reverse"] = True

        async for msg in user_client.iter_messages(source, **iter_kwargs):
            if max_posts > 0 and post_count >= max_posts:
                break

            gid = getattr(msg, 'grouped_id', None)
            is_filtered, reason = await should_filter(msg, pool)
            if is_filtered:
                logger.info(f"过滤: msg_id={msg.id} 原因:{reason}")
                skipped += 1
                continue

            if gid:
                if gid in processed_groups:
                    continue
                processed_groups.add(gid)
                try:
                    group_msgs = group_index.get(gid, [msg])
                    same_group = {m.id: m for m in group_msgs if m is not None}
                    if same_group:
                        r = await send_group(user_client, target, same_group, prefix, suffix)
                        if r:
                            target_msg_id = r.id
                            async with pool.acquire() as conn:
                                for mid in same_group.keys():
                                    await insert_cloned_post(pool, task_id, mid, target_msg_id)
                                await conn.execute("UPDATE clone_tasks SET last_processed_msg_id=$1 WHERE id=$2", msg.id, task_id)
                            cloned += 1
                            post_count += 1
                            await asyncio.sleep(random.uniform(25, 40))
                            logger.info(f"✅ 媒体组 #{cloned}/{max_posts} ({len(same_group)}个文件)")
                        else:
                            skipped += 1
                    else:
                        skipped += 1
                except Exception as e:
                    logger.error(f"媒体组失败: {e}")
                    skipped += 1
                    async with pool.acquire() as conn:
                        await conn.execute("UPDATE clone_tasks SET status='error', error_msg=$1 WHERE id=$2", str(e)[:500], task_id)
                    await notify_user(task["user_telegram_id"], f"❌ 任务 #{task_id} 出错：{str(e)[:200]}")
                    return
                if max_posts > 0 and post_count >= max_posts:
                    break
                continue

            if pending_group:
                try:
                    r = await send_group(user_client, target, pending_group, prefix, suffix)
                    if r:
                        target_msg_id = r.id
                        async with pool.acquire() as conn:
                            for mid in pending_group.keys():
                                await insert_cloned_post(pool, task_id, mid, target_msg_id)
                            await conn.execute("UPDATE clone_tasks SET last_processed_msg_id=$1 WHERE id=$2", msg.id, task_id)
                        cloned += 1
                        post_count += 1
                        await asyncio.sleep(random.uniform(25, 40))
                        logger.info(f"✅ 媒体组 #{cloned}/{max_posts} ({len(pending_group)}个文件)")
                    else:
                        skipped += 1
                except Exception as e:
                    logger.error(f"媒体组失败: {e}")
                    skipped += 1
                    async with pool.acquire() as conn:
                        await conn.execute("UPDATE clone_tasks SET status='error', error_msg=$1 WHERE id=$2", str(e)[:500], task_id)
                    await notify_user(task["user_telegram_id"], f"❌ 任务 #{task_id} 出错：{str(e)[:200]}")
                    return
                pending_group = {}
                last_group_id = None

            raw_caption = getattr(msg, 'text', '') or ''
            cleaned = clean_text(raw_caption)
            caption = (prefix + cleaned + suffix)[:2000] if cleaned else ""

            has_web_preview = getattr(msg, 'web_preview', None) is not None
            has_real_text = clean_text(raw_caption).strip() != ""

            try:
                if has_web_preview and not has_real_text:
                    skipped += 1
                    continue
                elif getattr(msg, 'photo', None) and not has_web_preview:
                    r = await user_client.send_file(target, msg.photo, caption=caption)
                elif getattr(msg, 'video', None):
                    r = await user_client.send_file(target, msg.video, caption=caption)
                elif getattr(msg, 'document', None):
                    r = await user_client.send_file(target, msg.document, caption=caption)
                elif caption.strip():
                    r = await user_client.send_message(target, caption)
                else:
                    skipped += 1
                    continue

                if r:
                    target_msg_id = r.id if hasattr(r, 'id') else None
                    if target_msg_id:
                        await insert_cloned_post(pool, task_id, msg.id, target_msg_id)
                    cloned += 1
                    post_count += 1
                    logger.info(f"✅ 单条 #{cloned}/{max_posts} msg_id={msg.id}")
                    async with pool.acquire() as conn:
                        await conn.execute("UPDATE clone_tasks SET last_processed_msg_id=$1 WHERE id=$2", msg.id, task_id)
                    if max_posts > 0 and post_count >= max_posts:
                        break
                else:
                    skipped += 1
            except FloodWaitError as e:
                logger.warning(f"限速{e.seconds}s，暂停后继续")
                async with pool.acquire() as conn:
                    await conn.execute("UPDATE clone_tasks SET cloned=$1, skipped=$2, last_processed_msg_id=$3 WHERE id=$4", cloned, skipped, msg.id, task_id)
                await asyncio.sleep(e.seconds + 30)
                continue
            except Exception as e:
                logger.error(f"失败 msg_id={msg.id}: {e}")
                skipped += 1
                async with pool.acquire() as conn:
                    await conn.execute("UPDATE clone_tasks SET status='error', error_msg=$1 WHERE id=$2", str(e)[:500], task_id)
                await notify_user(task["user_telegram_id"], f"❌ 任务 #{task_id} 出错：{str(e)[:200]}")
                return

            await asyncio.sleep(random.uniform(15, 25))

        if pending_group and (max_posts == 0 or post_count < max_posts):
            try:
                r = await send_group(user_client, target, pending_group, prefix, suffix)
                if r:
                    target_msg_id = r.id
                    async with pool.acquire() as conn:
                        for mid in pending_group.keys():
                            await insert_cloned_post(pool, task_id, mid, target_msg_id)
                        await conn.execute("UPDATE clone_tasks SET last_processed_msg_id=$1 WHERE id=$2", msg.id, task_id)
                    cloned += 1
                    post_count += 1
                    logger.info(f"✅ 最后媒体组 #{cloned}/{max_posts} ({len(pending_group)}个文件)")
            except Exception as e:
                skipped += 1

        logger.info(f"=== 完成 {cloned}成功 {skipped}跳过 ===")
        async with pool.acquire() as conn:
            await conn.execute("UPDATE clone_tasks SET status='done', cloned=$1, skipped=$2, finished_at=NOW() WHERE id=$3", cloned, skipped, task_id)
        await notify_user(task["user_telegram_id"], f"✅ 您的克隆任务 #{task_id} 已完成！克隆 {cloned} 条，跳过 {skipped} 条。")

    except Exception as e:
        logger.error(f"异常: {traceback.format_exc()}")
        try:
            async with pool.acquire() as conn:
                await conn.execute("UPDATE clone_tasks SET status='error', error_msg=$1 WHERE id=$2", str(e)[:500], task_id)
        except: pass
        await notify_user(task["user_telegram_id"], f"❌ 任务 #{task_id} 出错：{str(e)[:200]}")
    finally:
        if user_client:
            try: await user_client.disconnect()
            except: pass
        await release_account(pool, account["id"])
        logger.info(f"任务 #{task_id} 结束，账号已释放")