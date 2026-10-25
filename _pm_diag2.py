import time
faulthandler = __import__('faulthandler')
faulthandler.dump_traceback_later(25)
t = time.time()
from pm import server
from fastapi.testclient import TestClient
c = TestClient(server.app)
print('health', c.get('/api/health').status_code, flush=True)
print('before chat', round(time.time()-t,1), flush=True)
r = c.post('/api/chat', json={'requirement': '录一个软件操作演示'})
print('chat', r.status_code, flush=True)
print('DONE', round(time.time()-t,1), flush=True)
