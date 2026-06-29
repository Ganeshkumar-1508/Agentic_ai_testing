"""External integrations — PRs, webhooks, notifications, traceability, test cases."""

from .routers.integrations import router
from .routers.pr_webhook import router as pr_webhook_router
from .routers.pr_manager import router as pr_manager_router
from .routers.notify_api import router as notify_router
from .routers.traceability_api import router as traceability_router
from .routers.testcases import router as testcases_router
from .routers.test_plans import router as test_plans_router
# Q1+Q2+Q3: generic TestAI webhook. HMAC-protected, tier-2 default.
# Registered here (alongside the PR webhook) so external systems
# have a single integration surface.
from .routers.webhooks import router as testai_webhook_router
# Q1+Q2+Q4: Slack incoming webhook (Events API + slash commands).
# HMAC-SHA256 verified against SLACK_SIGNING_SECRET.
from .routers.slack_webhooks import router as slack_webhook_router

integration_routers = [
    router,
    pr_webhook_router,
    pr_manager_router,
    notify_router,
    traceability_router,
    testcases_router,
    test_plans_router,
    testai_webhook_router,
    slack_webhook_router,
]
