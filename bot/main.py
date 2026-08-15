import engine
import asyncio
import logging
from telethon import TelegramClient, events
from config import BOT_TOKEN

logging.basicConfig(level=logging.INFO, format='%(asctime)s [Bot] %(message)s')
logger = logging.getLogger(__name__)

API_ID = 38835328
API_HASH = "814822151f2b158e015906d1f2c99e73"

async def main():
    bot = TelegramClient('bot_bot_session', API_ID, API_HASH)
    await bot.start(bot_token=BOT_TOKEN)

    # 设置 engine 的 bot 实例
    engine.bot_instance = bot

    from bot.handlers import start, clone, tasks, account, recharge, support, delete, account_selector

    start.register(bot)
    clone.register(bot)
    tasks.register(bot)
    account.register(bot)
    recharge.register(bot)
    support.register(bot)
    delete.register(bot)
    account_selector.register(bot)

    logger.info("Bot 已启动")
    await bot.run_until_disconnected()
