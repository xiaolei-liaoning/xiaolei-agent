#!/usr/bin/env python3
"""Test EverOS full memory flow"""
import urllib.request, json, time, os

BASE = 'http://127.0.0.1:8000'
ts = int(time.time() * 1000)

# 1. Add
data = {'session_id':'test-005','app_id':'default','project_id':'default','messages':[{'sender_id':'xiaolei','role':'user','timestamp':ts,'content':'我在用Claude Code做AI Agent系统'}]}
r = urllib.request.Request(f'{BASE}/api/v1/memory/add', data=json.dumps(data).encode(), headers={'Content-Type':'application/json'})
resp = urllib.request.urlopen(r, timeout=10)
print('Add:', resp.read().decode())

# 2. Flush
time.sleep(2)
data = {'session_id':'test-005','app_id':'default','project_id':'default'}
r = urllib.request.Request(f'{BASE}/api/v1/memory/flush', data=json.dumps(data).encode(), headers={'Content-Type':'application/json'})
resp = urllib.request.urlopen(r, timeout=60)
print('Flush:', resp.read().decode())

# 3. Search
time.sleep(3)
data = {'user_id':'xiaolei','app_id':'default','project_id':'default','query':'Claude Code Agent','top_k':5}
r = urllib.request.Request(f'{BASE}/api/v1/memory/search', data=json.dumps(data).encode(), headers={'Content-Type':'application/json'})
resp = urllib.request.urlopen(r, timeout=10)
result = json.loads(resp.read())
episodes = result.get('data',{}).get('episodes',[])
print(f'Search: {len(episodes)} episodes')
if episodes:
    print('✓ First episode:', json.dumps(episodes[0], ensure_ascii=False)[:200])
else:
    print('Response:', json.dumps(result, ensure_ascii=False)[:300])

# 4. Check markdown files
md_dir = os.path.expanduser('~/.evermem/default_app/default_project/users/xiaolei/episodes/')
if os.path.isdir(md_dir):
    print('✓ Markdown files:', os.listdir(md_dir))
