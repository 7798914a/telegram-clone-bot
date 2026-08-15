import asyncio
from telethon import TelegramClient

API_ID = 38835328
API_HASH = "814822151f2b158e015906d1f2c99e73"

async def main():
    session_file = "sessions/account_1"
    client = TelegramClient(session_file, API_ID, API_HASH)
    await client.start(phone="+16395261747")
    print("✅ 账号已连接")
    
    source = await client.get_entity("@lieqiba")
    target = await client.get_entity("@xjxjxnxnxndjdn")
    print(f"源: {source.title}")
    print(f"目标: {target.title}")
    
    cloned = 0
    processed_groups = set()
    pending_group = {}
    last_group_id = None
    
    async def send_group(target, group_msgs):
        media = []
        caption = ""
        for m in sorted(group_msgs.values(), key=lambda x: x.id):
            if getattr(m, 'photo', None): media.append(m.photo)
            elif getattr(m, 'video', None): media.append(m.video)
            elif getattr(m, 'document', None): media.append(m.document)
            txt = getattr(m, 'text', '') or ''
            if txt and not caption: caption = txt[:1024]
        if media:
            return await client.send_file(target, media, group=True, caption=caption)
        return None
    
    async for msg in client.iter_messages(source, limit=20):
        gid = getattr(msg, 'grouped_id', None)
        
        if gid:
            if gid in processed_groups: continue
            if last_group_id != gid and pending_group:
                # 上一个组收齐，发送
                try:
                    r = await send_group(target, pending_group)
                    if r:
                        cloned += 1
                        print(f"✅ 媒体组发送成功 ({len(pending_group)}个文件)")
                except Exception as e:
                    print(f"❌ 媒体组失败: {e}")
                pending_group = {}
            pending_group[msg.id] = msg
            last_group_id = gid
            continue
        
        # 非媒体组，先发积累的
        if pending_group:
            try:
                r = await send_group(target, pending_group)
                if r:
                    cloned += 1
                    print(f"✅ 媒体组发送成功 ({len(pending_group)}个文件)")
            except Exception as e:
                print(f"❌ 媒体组失败: {e}")
            pending_group = {}
            last_group_id = None
        
        # 单条
        caption = (getattr(msg, 'text', '') or '')[:2000]
        try:
            if getattr(msg, 'photo', None):
                r = await client.send_file(target, msg.photo, caption=caption)
                cloned += 1; print(f"✅ 图片 msg_id={msg.id}")
            elif getattr(msg, 'video', None):
                r = await client.send_file(target, msg.video, caption=caption)
                cloned += 1; print(f"✅ 视频 msg_id={msg.id}")
            elif caption:
                r = await client.send_message(target, caption)
                cloned += 1; print(f"✅ 文字 msg_id={msg.id}")
        except Exception as e:
            print(f"❌ 失败 msg_id={msg.id}: {e}")
        
        await asyncio.sleep(1)
    
    # 最后残留的组
    if pending_group:
        try:
            r = await send_group(target, pending_group)
            if r:
                cloned += 1
                print(f"✅ 最后媒体组 ({len(pending_group)}个文件)")
        except Exception as e:
            print(f"❌ 最后媒体组失败: {e}")
    
    print(f"\n=== 完成: {cloned} 条帖子 ===")
    await client.disconnect()

asyncio.run(main())
