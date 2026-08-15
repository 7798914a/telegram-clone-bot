import json
import redis.asyncio as aioredis
from config import REDIS_CONFIG

QUEUE_KEY = "clone:queue"
PROGRESS_KEY = "clone:progress:{}"

async def get_redis():
    return aioredis.Redis(**REDIS_CONFIG, decode_responses=True)

async def push_task(task_id: int):
    r = await get_redis()
    await r.lpush(QUEUE_KEY, json.dumps({"task_id": task_id}))

async def pop_task():
    r = await get_redis()
    data = await r.rpop(QUEUE_KEY)
    return json.loads(data) if data else None

async def update_progress(task_id: int, data: dict):
    r = await get_redis()
    await r.set(PROGRESS_KEY.format(task_id), json.dumps(data), ex=3600)

async def get_progress(task_id: int):
    r = await get_redis()
    data = await r.get(PROGRESS_KEY.format(task_id))
    return json.loads(data) if data else None