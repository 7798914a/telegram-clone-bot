import asyncio
import os
import time
import threading
from telethon import TelegramClient, errors
from config import SESSION_DIR, PG_CONFIG
import asyncpg

_code_lock = threading.Lock()
pending_code_requests = {}

def set_pending_code(account_id, data):
    with _code_lock: pending_code_requests[account_id] = data

def get_pending_code(account_id):
    with _code_lock: return pending_code_requests.get(account_id, {}).copy()

def del_pending_code(account_id):
    with _code_lock:
        if account_id in pending_code_requests: del pending_code_requests[account_id]

def get_session_path(account_id):
    return os.path.join(SESSION_DIR, f"account_{account_id}")

async def _update_status(account_id, status, session_file=None):
    try:
        p = await asyncpg.create_pool(**PG_CONFIG, min_size=1, max_size=2)
        async with p.acquire() as conn:
            if session_file:
                await conn.execute("UPDATE tg_accounts SET status=$1, session_file=$2 WHERE id=$3", status, session_file, account_id)
            else:
                await conn.execute("UPDATE tg_accounts SET status=$1 WHERE id=$2", status, account_id)
        await p.close()
    except Exception as e:
        print(f"更新状态失败: {e}")

async def _get_account(account_id):
    p = await asyncpg.create_pool(**PG_CONFIG, min_size=1, max_size=2)
    async with p.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM tg_accounts WHERE id=$1", account_id)
    await p.close()
    return row

async def _login_account_async(account_id):
    account = await _get_account(account_id)
    
    if not account:
        print("账号不存在")
        return
    
    phone_val = account["phone"]
    print(f"开始登录账号 {phone_val}")

    session_file = get_session_path(account_id)
    del_pending_code(account_id)
    set_pending_code(account_id, {"status": "connecting", "phone": account["phone"]})

    client = TelegramClient(
        session_file, 
        account["api_id"], 
        account["api_hash"],
        timeout=30,
        connection_retries=3
    )
    
    try:
        print("连接TG...")
        await client.connect()
        print("TG已连接")

        if await client.is_user_authorized():
            set_pending_code(account_id, {"status": "connected", "phone": account["phone"]})
            await _update_status(account_id, "connected", session_file)
            await client.disconnect()
            return

        set_pending_code(account_id, {"status": "sending_code", "phone": account["phone"]})
        try:
            print("发送验证码...")
            result = await client.send_code_request(account["phone"])
            print("验证码已发送")
            set_pending_code(account_id, {
                "status": "waiting_code", 
                "phone": account["phone"], 
                "phone_code_hash": result.phone_code_hash
            })
        except Exception as e:
            set_pending_code(account_id, {"status": "error", "phone": account["phone"], "error": f"发送失败: {e}"})
            await client.disconnect()
            return

        code = None
        for _ in range(300):
            req = get_pending_code(account_id)
            if req.get("status") == "code_submitted":
                code = req.get("code", "").strip()
                break
            if req.get("status") == "cancelled":
                set_pending_code(account_id, {"status": "cancelled"})
                await client.disconnect()
                return
            await asyncio.sleep(1)

        if not code:
            set_pending_code(account_id, {"status": "timeout"})
            await client.disconnect()
            return

        try:
            await client.sign_in(account["phone"], code, phone_code_hash=get_pending_code(account_id).get("phone_code_hash", ""))
            set_pending_code(account_id, {"status": "connected", "phone": account["phone"]})
            await _update_status(account_id, "connected", session_file)
            await client.disconnect()
            return
        except errors.SessionPasswordNeededError:
            set_pending_code(account_id, {"status": "waiting_2fa", "phone": account["phone"]})
            
            password = None
            for _ in range(300):
                req = get_pending_code(account_id)
                if req.get("status") == "code_submitted":
                    password = req.get("code", "").strip()
                    break
                if req.get("status") == "cancelled":
                    set_pending_code(account_id, {"status": "cancelled"})
                    await client.disconnect()
                    return
                await asyncio.sleep(1)

            if not password:
                set_pending_code(account_id, {"status": "timeout"})
                await client.disconnect()
                return

            try:
                await client.sign_in(password=password)
                set_pending_code(account_id, {"status": "connected", "phone": account["phone"]})
                await _update_status(account_id, "connected", session_file)
                await client.disconnect()
                return
            except Exception as e:
                set_pending_code(account_id, {"status": "error", "phone": account["phone"], "error": f"2FA失败: {e}"})
                await client.disconnect()
                return
        except Exception as e:
            set_pending_code(account_id, {"status": "error", "phone": account["phone"], "error": f"验证码错误: {e}"})
            await client.disconnect()
            return

    except asyncio.TimeoutError:
        set_pending_code(account_id, {"status": "timeout", "phone": account["phone"], "error": "连接超时"})
        try: await client.disconnect()
        except: pass
    except Exception as e:
        set_pending_code(account_id, {"status": "error", "phone": account["phone"], "error": str(e)[:200]})
        try: await client.disconnect()
        except: pass

def login_account_sync(account_id):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_login_account_async(account_id))
    finally:
        loop.close()

def start_login_thread(account_id):
    t = threading.Thread(target=login_account_sync, args=(account_id,), daemon=True)
    t.start()
    return t
