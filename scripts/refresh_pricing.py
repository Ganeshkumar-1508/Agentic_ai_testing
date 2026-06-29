import asyncio

async def refresh():
    from harness.memory.database import Database
    from harness.pricing_cache import PricingCache
    db = Database()
    await db.connect()
    Database._instance = db
    cache = PricingCache(db)
    result = await cache.refresh_if_stale()
    print("Refreshed:", result)
    rows = await db.fetch("SELECT count(*) as cnt FROM model_pricing_cache")
    print("Models cached:", rows[0]["cnt"])
    ds = await db.fetch("SELECT slug, input_per_1m, output_per_1m FROM model_pricing_cache WHERE slug LIKE '%deepseek%' LIMIT 5")
    for r in ds:
        print(f"  {r['slug']}: input={r['input_per_1m']}/1M, output={r['output_per_1m']}/1M")
    await db.disconnect()

asyncio.run(refresh())
