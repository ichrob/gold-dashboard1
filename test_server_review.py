import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler
import server

class ReviewTests(unittest.TestCase):
    def test_mtf_verification_carries_original_time_and_rejects_future(self):
        now=1800000000
        bars=[dict(openTime=(now-300*(220-i))*1000,close=4000+i*.2,isOpen=False) for i in range(220)]
        with patch.object(server.time,'time',return_value=now):
            result=server._mtf_score(bars,'5m')
            self.assertTrue(result['fresh'])
            self.assertEqual(result['openTime'],bars[-1]['openTime'])
            bars[-1]['openTime']=(now+10)*1000
            result=server._mtf_score(bars,'5m')
            self.assertFalse(result['available']);self.assertFalse(result['fresh'])

    def test_disconnected_clients_do_not_retry_completed_requests(self):
        handler=object.__new__(server.Handler)
        for error in (BrokenPipeError(),ConnectionResetError()):
            with patch.object(BaseHTTPRequestHandler,'handle',side_effect=error) as call:
                handler.handle();call.assert_called_once()
                self.assertTrue(handler.close_connection)
        with patch.object(BaseHTTPRequestHandler,'handle',side_effect=ValueError('real bug')):
            with self.assertRaises(ValueError):handler.handle()

if __name__=='__main__':unittest.main()

class IntradayMtfTests(unittest.TestCase):
    def test_optional_four_hour_and_mandatory_confirmation(self):
        frames={tf:dict(dir='LONG',available=True,fresh=True) for tf in ('5m','15m','1h')}
        frames['4h']=dict(dir='SHORT',available=False,fresh=False)
        with patch.object(server,'_mtf_score',side_effect=lambda bars,tf:frames[tf]):
            self.assertEqual(server.build_mtf_verification({})['overall'],'LONG')
            frames['15m']['dir']='NEUTRAL'
            self.assertEqual(server.build_mtf_verification({})['overall'],'NEUTRAL')
