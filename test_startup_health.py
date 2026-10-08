import unittest
from unittest.mock import patch, Mock
import server
class StartupHealthTests(unittest.TestCase):
 def test_startup_not_reported_ready(self):
  with patch.object(server.auto_collection,'health',return_value={'enabled':True,'running':True,'cfdFeed':{'state':'starting'}}), patch.dict(server.FIB_MONITOR_HEALTH,configured=True,status='starting',lastSuccessAt=None):
   result=server.service_health()
   self.assertFalse(result['ready']);self.assertEqual(result['status'],'degraded')
   self.assertIn('market-feed-not-current',result['reasons']);self.assertIn('background-not-current',result['reasons'])
 def test_recovered_same_runtime_identity(self):
  with patch.object(server.auto_collection,'health',return_value={'enabled':True,'running':True,'cfdFeed':{'state':'current'}}), patch.dict(server.FIB_MONITOR_HEALTH,configured=True,status='active',lastSuccessAt=int(server.time.time())):
   a=server.service_health();b=server.service_health()
   self.assertTrue(a['ready']);self.assertEqual(a['runtime']['processId'],b['runtime']['processId'])
 def test_dead_worker_restarts_once(self):
  worker=Mock();worker.is_alive.return_value=True
  with patch.dict(server.FIB_MONITOR_HEALTH,configured=True),patch.object(server,'_FIB_THREAD',None),patch.object(server.threading,'Thread',return_value=worker) as ctor:
   server.ensure_fibonacci_monitor();server.ensure_fibonacci_monitor()
   ctor.assert_called_once();worker.start.assert_called_once()
if __name__=='__main__':unittest.main()
