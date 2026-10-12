import asyncio
import os
import redis.asyncio as r

async def t():
    c = r.from_url(
        os.environ["REDIS_URL"],
        decode_responses=True,
    )
    print(await c.ping())
    await c.aclose()

asyncio.run(t())
