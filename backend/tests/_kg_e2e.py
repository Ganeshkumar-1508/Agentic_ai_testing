import json, urllib.request, urllib.error, sys

API = "http://localhost:8000"
GRAPH = "a901b404fa3c2b12"

def get(path):
    try:
        req = urllib.request.Request(f"{API}{path}", method="GET")
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return "ERR", str(e)

# 1. Get metadata - has real node IDs
print("=== Step 1: Get metadata (lists node kinds) ===")
status, body = get(f"/api/knowledge-graph/{GRAPH}/metadata")
print(f"  HTTP {status}, size={len(body)} bytes")
if status == 200:
    d = json.loads(body)
    meta = d.get("metadata", {})
    print(f"  nodes: {meta.get('nodeCount')}, edges: {meta.get('edgeCount')}")
    print(f"  node_kinds: {[(k['kind'], k['n']) for k in d.get('node_kinds', [])[:5]]}")

# 2. Get a real file path
print("\n=== Step 2: Get a real file path ===")
status, body = get(f"/api/knowledge-graph/{GRAPH}/metadata")
files = json.loads(body).get("files", [])
if files:
    test_file = files[0]["path"]
    print(f"  testing file: {test_file}")
    status, body = get(f"/api/knowledge-graph/{GRAPH}/file?path={urllib.parse.quote(test_file, safe='/')}")
    print(f"  HTTP {status}, size={len(body)} bytes")
    if status == 200:
        d = json.loads(body)
        print(f"  nodes in file: {d.get('node_count')}, edges: {d.get('edge_count')}")

# 3. Get a real node ID and test neighborhood
print("\n=== Step 3: Get a real node from the file ===")
import urllib.parse
test_file = files[0]["path"]
status, body = get(f"/api/knowledge-graph/{GRAPH}/file?path={urllib.parse.quote(test_file, safe='/')}")
if status == 200:
    file_data = json.loads(body)
    if file_data.get("nodes"):
        test_node = file_data["nodes"][0]["id"]
        print(f"  testing node: {test_node}")
        # Test depth=1
        status, body = get(f"/api/knowledge-graph/{GRAPH}/neighborhood?node_id={urllib.parse.quote(test_node, safe='')}&depth=1")
        print(f"\n  depth=1: HTTP {status}, size={len(body)} bytes")
        if status == 200:
            d = json.loads(body)
            print(f"    nodes: {d.get('node_count')}, edges: {d.get('edge_count')}, truncated: {d.get('truncated')}")
        # Test depth=2
        status, body = get(f"/api/knowledge-graph/{GRAPH}/neighborhood?node_id={urllib.parse.quote(test_node, safe='')}&depth=2")
        print(f"  depth=2: HTTP {status}, size={len(body)} bytes")
        if status == 200:
            d = json.loads(body)
            print(f"    nodes: {d.get('node_count')}, edges: {d.get('edge_count')}, truncated: {d.get('truncated')}")
        # Test depth=3
        status, body = get(f"/api/knowledge-graph/{GRAPH}/neighborhood?node_id={urllib.parse.quote(test_node, safe='')}&depth=3")
        print(f"  depth=3: HTTP {status}, size={len(body)} bytes")
        if status == 200:
            d = json.loads(body)
            print(f"    nodes: {d.get('node_count')}, edges: {d.get('edge_count')}, truncated: {d.get('truncated')}")
