import sys, traceback, os
# backend dir, relative to this file -- survives any folder rename/move
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import db
with db() as conn:
    heroes = [dict(r) for r in conn.execute('SELECT * FROM heroes WHERE is_alive=1 LIMIT 4').fetchall()]
from services.combat_service import run_combat
try:
    print(run_combat(heroes, 1, False))
except Exception as e:
    traceback.print_exc()
