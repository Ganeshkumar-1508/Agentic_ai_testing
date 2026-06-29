"""Find all remaining imports of removed protocol types."""
import re, ast
from pathlib import Path

ROOT = Path("/backup")

# All Protocol types that were removed (only dataclasses remain)
REMOVED = {"AgentStore", "ArtifactStore", "EventStore", "JobSpecStore", "PipelineStore", 
           "ProposalStore", "RunStore", "SessionStore", "SkillStore", "KnowledgeGraphStore"}

for py in sorted(ROOT.rglob("*.py")):
    try:
        source = py.read_text(encoding="utf-8", errors="ignore")
    except:
        continue
    for name in REMOVED:
        if name in source:
            print(f"{py.relative_to(ROOT)} contains {name}")
            break
