#!/usr/bin/env python3
"""
独立账号登录脚本
用法: python3 login_account.py
"""

import os
import sys
import asyncio
from telethon import TelegramClient, errors
from telethon.tl.types import UserStatusOnline, UserStatusOffline
import asyncpg
from config import PG_CONFIG, SESSION_DIR

# 确保 sessions 目录存在
os.makedirs(SESSION_DIR, exist_ok=True)

async def get_api_from_db():
    """从数据库获取账号信息"""
    conn = await asyncpg.connect(**PG_CONFIG)
    rows = await conn.fetch("SELECT id, phone, api_id, api_hash, status FROM tg_accounts ORDER BY id")
    await conn.close()
    return rows

async def login_account(account_id, phone, api_id, api_hash):
    """登录单个账号"""
    session_file = os.path.join(SESSION_DIR, f"account_{account_id}")
    
    print(f"\n{'='*50}")
    print(f"📱 登录账号: {phone}")
    print(f"📁 Session文件: {session_file}.session")
    print(f"{'='*50}")
    
    # 检查是否已有 session 文件
    if os.path.exists(f"{session_file}.session"):
        print(f"✅ 已存在 session 文件，尝试复用...")
    
    client = TelegramClient(session_file, api_id, api_hash)
    
    try:
        await client.connect()
        
        # 检查是否已授权
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"✅ 账号已登录: {me.first_name} (@{me.username or '无'})")
            await client.disconnect()
            return True
        
        print("⏳ 发送验证码请求...")
        
        # 发送验证码
        try:
            result = await client.send_code_request(phone)
            print(f"✅ 验证码已发送！")
            print(f"📌 请检查:")
            print(f"   1. Telegram App 的通知")
            print(f"   2. 短信验证码")
            print(f"   3. 垃圾短信箱")
        except errors.PhoneNumberInvalidError:
            print("❌ 手机号无效")
            await client.disconnect()
            return False
        except errors.FloodWaitError as e:
            print(f"⏰ 请等待 {e.seconds} 秒后再试")
            await client.disconnect()
            return False
        except Exception as e:
            print(f"❌ 发送验证码失败: {e}")
            await client.disconnect()
            return False
        
        # 获取验证码
        code = input("请输入验证码: ").strip()
        
        if not code:
            print("❌ 验证码不能为空")
            await client.disconnect()
            return False
        
        try:
            await client.sign_in(phone, code)
            me = await client.get_me()
            print(f"✅ 登录成功！")
            print(f"   👤 {me.first_name} (@{me.username or '无'})")
            print(f"   📁 Session已保存: {session_file}.session")
            
            # 更新数据库状态
            conn = await asyncpg.connect(**PG_CONFIG)
            await conn.execute(
                "UPDATE tg_accounts SET status='connected', session_file=$1 WHERE id=$2",
                session_file, account_id
            )
            await conn.close()
            
            await client.disconnect()
            return True
            
        except errors.SessionPasswordNeededError:
            print("🔐 需要2FA验证码")
            password = input("请输入2FA密码: ").strip()
            try:
                await client.sign_in(password=password)
                me = await client.get_me()
                print(f"✅ 登录成功！")
                print(f"   👤 {me.first_name} (@{me.username or '无'})")
                
                conn = await asyncpg.connect(**PG_CONFIG)
                await conn.execute(
                    "UPDATE tg_accounts SET status='connected', session_file=$1 WHERE id=$2",
                    session_file, account_id
                )
                await conn.close()
                
                await client.disconnect()
                return True
            except Exception as e:
                print(f"❌ 2FA验证失败: {e}")
                await client.disconnect()
                return False
                
        except errors.PhoneCodeInvalidError:
            print("❌ 验证码错误")
            await client.disconnect()
            return False
        except errors.PhoneCodeExpiredError:
            print("❌ 验证码已过期，请重新请求")
            await client.disconnect()
            return False
        except Exception as e:
            print(f"❌ 登录失败: {e}")
            await client.disconnect()
            return False
            
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        try:
            await client.disconnect()
        except:
            pass
        return False

async def main():
    print("🤖 Telegram 账号登录工具")
    print("="*50)
    
    # 获取账号列表
    accounts = await get_api_from_db()
    
    if not accounts:
        print("❌ 数据库中没有账号")
        print("请先在 Web 后台添加账号")
        return
    
    print("\n📋 可用的账号:")
    for i, acc in enumerate(accounts, 1):
        status = "✅" if acc["status"] == "connected" else "⏳"
        print(f"  {i}. {status} ID:{acc['id']} {acc['phone']} ({acc['status']})")
    
    print("\n" + "="*50)
    print("选项:")
    print("  1 - 登录指定账号")
    print("  2 - 登录所有未登录账号")
    print("  3 - 退出")
    
    choice = input("\n请选择: ").strip()
    
    if choice == "1":
        idx = int(input("请输入账号序号: ").strip()) - 1
        if 0 <= idx < len(accounts):
            acc = accounts[idx]
            await login_account(acc["id"], acc["phone"], acc["api_id"], acc["api_hash"])
        else:
            print("❌ 无效序号")
            
    elif choice == "2":
        for acc in accounts:
            if acc["status"] != "connected":
                await login_account(acc["id"], acc["phone"], acc["api_id"], acc["api_hash"])
            else:
                print(f"⏭️ 跳过已登录账号: {acc['phone']}")
    else:
        print("👋 退出")

if __name__ == "__main__":
    asyncio.run(main())
