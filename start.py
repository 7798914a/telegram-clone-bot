import asyncio
import logging
import uvicorn

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s')
logger = logging.getLogger(__name__)

async def main():
    from models import init_db, get_pool
    await init_db()
    
    # 启动时清理
    p = await get_pool()
    async with p.acquire() as conn:
        await conn.execute('UPDATE tg_accounts SET is_assigned=FALSE, assigned_task_id=NULL')
        await conn.execute("UPDATE clone_tasks SET status='cancelled' WHERE status NOT IN ('done','cancelled','error','stopped')")
        # 不清除账号登录状态
    logger.info("数据库初始化+清理完成")
    
    # 定期清理超时状态
    async def cleanup_states():
        while True:
            await asyncio.sleep(60)
            try:
                async with p.acquire() as conn:
                    await conn.execute("DELETE FROM user_states WHERE updated_at < NOW() - INTERVAL '5 minutes'")
            except: pass
    
    asyncio.create_task(cleanup_states())
    
    # 启动 Worker（同一事件循环）
    from engine import run_clone_task
    from redis_queue import pop_task
    
    async def worker():
        logger.info("Worker 启动")
        while True:
            try:
                task_data = await pop_task()
                if task_data:
                    task_id = task_data["task_id"]
                    logger.info(f"收到任务 #{task_id}")
                    await run_clone_task(task_id)
                else:
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Worker 异常: {e}")
                await asyncio.sleep(1)
    
    asyncio.create_task(worker())
    
    # 启动 Bot（同一事件循环）
    from bot.main import main as bot_main
    asyncio.create_task(bot_main())
    
    # Web 启动
    from web.main import app
    config = uvicorn.Config(app, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    logger.info("Web 后台启动 :8000")
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
