import sys
print("Starting test...", flush=True)
from api.main import app
import asyncio

async def test():
    print("Entering lifespan...", flush=True)
    async with app.router.lifespan_context(app):
        print("Inside lifespan", flush=True)
        from harness.api.state import get_agent_factory
        af = get_agent_factory()
        print(f"Agent factory: {'SET' if af else 'NOT SET'}", flush=True)
    print("Exited lifespan", flush=True)

asyncio.run(test())
