"""Configuration & management — providers, tools, permissions, cost, kanban."""

from .routers.settings import router
from .routers.provider_defs import router as provider_defs_router
from .routers.saved_filters import router as saved_filters_router
from .routers.sandbox_config import router as sandbox_config_router
from .routers.admin_api import router as admin_api_router
from .routers.agents import router as agents_router
from .routers.tools_management import router as tools_mgmt_router
from .routers.permissions import router as permissions_router
from .routers.cost import router as cost_router
from .routers.kanban import router as kanban_router

settings_routers = [
    router,
    provider_defs_router,
    saved_filters_router,
    sandbox_config_router,
    admin_api_router,
    agents_router,
    tools_mgmt_router,
    permissions_router,
    cost_router,
    kanban_router,
]
