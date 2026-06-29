import httpx, json

r = httpx.post('https://api.pricepertoken.com/mcp/mcp',
    headers={'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'},
    json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}},
    timeout=10)
data = r.json()
tools = data.get('result', {}).get('tools', [])
for t in tools:
    name = t.get('name', '?')
    desc = t.get('description', '')[:80]
    print(f"  {name}: {desc}")
