import sys
sys.path.insert(0, "/app")
from api.routers.events import router
for p in router.routes:
    methods = list(p.methods or [])
    print(f"{p.path} {methods}")
