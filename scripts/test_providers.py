import httpx, json

r = httpx.post('https://api.pricepertoken.com/mcp/mcp',
    headers={'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'},
    json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'get_providers', 'arguments': {}}},
    timeout=10)
data = r.json()
content = data.get('result', {}).get('content', [])
for entry in content:
    if entry.get('type') == 'text':
        text = entry['text']
        providers = json.loads(text) if isinstance(text, str) else text
        if isinstance(providers, list):
            print(f"Got {len(providers)} providers")
            for p in providers[:5]:
                print(f"  {p}")
        else:
            print(f"Type: {type(providers)}")
            print(f"Preview: {str(providers)[:200]}")
