import asyncio
import asyncpg


async def check():
    conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/testai")
    rows = await conn.fetch("SELECT provider, config FROM provider_configs")
    for r in rows:
        p = r["provider"]
        c = str(r["config"])[:300]
        print(f"Provider: {p}")
        print(f"Config: {c}")
        print()
    await conn.close()


asyncio.run(check())
