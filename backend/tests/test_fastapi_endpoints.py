from fastapi.testclient import TestClient
import json
import sys
import os

# repo + backend dirs, relative to this file — survives any folder rename/move
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO = os.path.dirname(_BACKEND)
sys.path.insert(0, _REPO)
sys.path.insert(0, _BACKEND)

try:
    from main import app as backend_app
    sys.path.insert(0, os.path.join(_REPO, "arena_server"))
    from arena_server.main import app as arena_app
except Exception as e:
    print("Error importing apps:", e)
    sys.exit(1)

backend_client = TestClient(backend_app)
arena_client = TestClient(arena_app)

print("Testing Arena Server health...")
res = arena_client.get("/arena/health")
print(res.status_code, res.json())
assert res.status_code == 200

print("Testing Backend Mail...")
res = backend_client.post("/base/mail/receive", json={
    "sender": "System",
    "subject": "Test",
    "body": "This is a test mail.",
    "rewards_json": {"gems": 10}
})
print(res.status_code)
assert res.status_code == 200

res = backend_client.get("/base/mail/list")
print(res.status_code)
assert res.status_code == 200
mail_list = res.json()
print("Mail count:", len(mail_list))

if len(mail_list) > 0:
    mail_id = mail_list[0]['id']
    res = backend_client.post("/base/mail/claim", json={"mail_id": mail_id})
    print("Claim response:", res.status_code, res.json())
    assert res.status_code == 200

print("Testing Training endpoint validation...")
res = backend_client.post("/arena/apply_training", json={
    "student_id": 999999, # non-existent hero
    "gem_cost": 0,
    "teacher_stats": {"max_health": 100},
    "teacher_skills": []
})
print("Training response:", res.status_code, res.json())
assert res.status_code == 404

print("All tests passed!")
