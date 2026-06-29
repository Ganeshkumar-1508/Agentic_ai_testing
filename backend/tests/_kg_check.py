import json, urllib.request

req = urllib.request.Request("http://localhost:8000/api/knowledge-graph/a901b404fa3c2b12", method="GET")
with urllib.request.urlopen(req, timeout=30) as r:
    data = json.loads(r.read().decode())

graph = data.get("graph", {})
nodes = graph.get("nodes", [])
edges = graph.get("edges", [])
metadata = graph.get("metadata", {})

print(f"nodes: {len(nodes)}")
print(f"edges: {len(edges)}")
print(f"metadata keys: {list(metadata.keys())[:8]}")
print(f"version: {graph.get('version', 'N/A')}")
print(f"total_nodes (from metadata): {metadata.get('nodeCount', 'N/A')}")
print(f"total_edges (from metadata): {metadata.get('edgeCount', 'N/A')}")
