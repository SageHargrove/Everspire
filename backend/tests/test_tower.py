import sys, traceback, os
# backend dir, relative to this file -- survives any folder rename/move
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from routers.tower import enter_floor, EnterFloorReq
try:
    req = EnterFloorReq(floor_number=1, team_id=1)
    res = enter_floor(req)
    print('OK')
except Exception as e:
    traceback.print_exc()
