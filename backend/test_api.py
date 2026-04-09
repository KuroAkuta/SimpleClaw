import requests
import json

BASE = 'http://localhost:8000'

# 1. Create session
resp = requests.post(f'{BASE}/api/sessions')
data = resp.json()
session_id = data['session_id']
print(f'Created session: {session_id}')

# 2. Send message
resp = requests.post(f'{BASE}/api/chat',
    json={'message': 'Hello', 'session_id': session_id})
print(f'Chat response: {resp.json()[:50] if isinstance(resp.json(), str) else resp.json()}')

# 3. Check debug
resp = requests.get(f'{BASE}/api/sessions/{session_id}/debug')
print(f'Debug info:')
print(json.dumps(resp.json(), indent=2))

# 4. Check messages
resp = requests.get(f'{BASE}/api/sessions/{session_id}/messages')
print(f'\nMessages:')
print(json.dumps(resp.json(), indent=2))
