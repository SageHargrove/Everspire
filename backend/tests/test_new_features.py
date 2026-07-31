import requests
import json
import time
import subprocess
import os
import signal
import sys

def main():
    print("Starting tests...")
    
    # 1. Start arena_server
    print("Starting arena_server...")
    _repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    arena_proc = subprocess.Popen(["python", "-m", "uvicorn", "main:app", "--port", "8001"], cwd=os.path.join(_repo, "arena_server"), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # 2. Start backend server
    print("Starting backend server...")
    backend_proc = subprocess.Popen(["python", "-m", "uvicorn", "main:app", "--port", "8000"], cwd=os.path.join(_repo, "backend"), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    time.sleep(5)
    
    try:
        # Check health
        res = requests.get("http://localhost:8001/arena/health")
        print("Arena health:", res.json())
        
        # Test backend mail endpoint
        res = requests.post("http://localhost:8000/api/base/mail/receive", json={
            "sender": "System",
            "subject": "Test",
            "body": "This is a test mail.",
            "rewards_json": {"gems": 10}
        })
        print("Mail receive response:", res.status_code)
        
        res = requests.get("http://localhost:8000/api/base/mail/list")
        print("Mail list response:", res.status_code)
        mail_list = res.json()
        print("Mail list:", len(mail_list))
        
        if len(mail_list) > 0:
            mail_id = mail_list[0]['id']
            res = requests.post("http://localhost:8000/api/base/mail/claim", json={"mail_id": mail_id})
            print("Mail claim response:", res.status_code, res.text)
        
        # Test apply training endpoint
        res = requests.post("http://localhost:8000/api/arena/apply_training", json={
            "student_id": 9999, # likely 404
            "gem_cost": 10,
            "teacher_stats": {"max_health": 100},
            "teacher_skills": []
        })
        print("Apply training 404 response:", res.status_code, res.text)
        assert res.status_code == 404, "Expected 404 for missing student hero"

        print("Tests passed successfully.")

    finally:
        print("Terminating servers...")
        arena_proc.terminate()
        backend_proc.terminate()
        arena_proc.wait()
        backend_proc.wait()

if __name__ == "__main__":
    main()
