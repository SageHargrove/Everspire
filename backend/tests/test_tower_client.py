import sys, traceback, os
# backend dir, relative to this file -- survives any folder rename/move
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient
from main import app
client = TestClient(app)
try:
    response = client.post('/tower/floor/enter', json={'floor_number': 1, 'team_id': 1})
    if response.status_code != 200:
        print('Error:', response.json())
    else:
        print('OK')
except Exception as e:
    traceback.print_exc()
