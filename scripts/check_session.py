import sys, json
sid = '78b406e7'
d = json.loads(sys.stdin.read())
for s in d['sessions']:
    s_id = s.get('session_id', '')
    p_id = s.get('parent_session_id', '') or ''
    if sid in s_id or sid in p_id:
        print(f'  {s_id[:45]:45s} status={s["status"]:10s} tokens={s.get("tokens",0):6d} role={s.get("role","?"):12s} parent={p_id[:25]}')
