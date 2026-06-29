import json, sys
d = json.load(sys.stdin)
for g in d["graphs"]:
    rid = g["id"][:12]
    nodes = g.get("node_count", 0)
    repo = g.get("repo_url") or "<none>"
    indexed = g.get("indexed_at") or "<no indexed_at>"
    print(f"{rid}  nodes={nodes:>6}  repo={repo:<45}  indexed={indexed}")
