"""Admin, ops, health, logs, analytics, and speculative feature routers."""

from .routers.admin import router
from .routers.ops import router as ops_router
from .routers.health import router as health_router, system_router as health_system_router
from .routers.logs import router as logs_router
from .routers.analytics import router as analytics_router
from .routers.dashboard_api import router as dashboard_router
from .routers.dashboard_widgets import router as dashboard_widgets_router

# Analytics & speculative feature stubs
from .routers.coverage_api import router as coverage_router
from .routers.quality_api import router as quality_router
from .routers.rca_api import router as rca_router
from .routers.impact_api import router as impact_router
from .routers.curator_api import router as curator_router
from .routers.testing_features_api import router as testing_features_router
from .routers.defect_api import router as defect_router
from .routers.sprint_api import router as sprint_router
from .routers.triage_api import router as triage_router
from .routers.generate_api import router as generate_router
from .routers.digest_api import router as digest_router
from .routers.artifacts_api import router as artifacts_router
from .routers.healing_api import router as healing_router
from .routers.stakeholder_api import router as stakeholder_router
from .routers.knowledge_graph_api import router as knowledge_graph_router
from .routers.projects_api import router as projects_router

admin_routers = [
    router,
    ops_router,
    health_router,
    health_system_router,
    logs_router,
    analytics_router,
    dashboard_router,
    dashboard_widgets_router,
    coverage_router,
    quality_router,
    rca_router,
    impact_router,
    curator_router,
    testing_features_router,
    defect_router,
    sprint_router,
    triage_router,
    generate_router,
    digest_router,
    artifacts_router,
    healing_router,
    stakeholder_router,
    knowledge_graph_router,
    projects_router,
]
