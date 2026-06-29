"""StoreRegistry — composition root for all store interfaces.

Create once at startup, inject into Agent/API dependencies.
Supports both Postgres adapters and in-memory (testing) adapters
through the Protocol interfaces defined in protocols.py.
"""

from __future__ import annotations

from typing import Any

from harness.memory.database import Database
from harness.store.adapters.postgres import (
    PostgresAgentStore,
    PostgresArtifactStore,
    PostgresEventStore,
    PostgresPipelineStore,
    PostgresRunStore,
    PostgresSessionStore,
    PostgresSkillStore,
)
from harness.store.protocols import (
    AgentStore,
    ArtifactStore,
    EventStore,
    RunStore,
    SessionStore,
    SkillStore,
)


class StoreRegistry:
    """Composition root for all store interfaces.

    Attributes are typed with Protocol interfaces so alternative
    implementations (in-memory, SQLite) can be swapped in.
    """

    def __init__(self, db: Database) -> None:
        self.db = db
        self.events: EventStore = PostgresEventStore(db)
        self.sessions: SessionStore = PostgresSessionStore(db)
        self.agents: AgentStore = PostgresAgentStore(db)
        self.artifacts: ArtifactStore = PostgresArtifactStore(db)
        self.skills: SkillStore = PostgresSkillStore(db)
        self.runs: RunStore = PostgresRunStore(db)
        self.pipelines = PostgresPipelineStore(db)
        self.knowledge_graph: Any = None

    def set_knowledge_graph(self, kg: Any) -> None:
        self.knowledge_graph = kg
