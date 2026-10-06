import unittest
from unittest.mock import Mock, patch
from http.server import BaseHTTPRequestHandler
import server

class ReviewTests(unittest.TestCase):
    def test_mtf_verification_carries_original_time_and_rejects_future(self):
        now=1800000000
        bars=[dict(openTime=(now-300*(220-i))*1000,open=4000+i*.2,high=4001+i*.2,low=3999+i*.2,close=4000+i*.2,isOpen=False) for i in range(220)]
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

    def test_live_client_disconnect_is_not_logged_as_data_failure(self):
        for error in (BrokenPipeError(), ConnectionResetError()):
            handler=object.__new__(server.Handler)
            handler.path='/api/live'
            handler.headers={}
            handler.authenticated=Mock(return_value=True)
            handler.send_response=Mock()
            handler.send_header=Mock()
            handler.end_headers=Mock()
            handler.wfile=Mock()
            handler.wfile.write.side_effect=error
            with patch.object(server,'build_live_bundle',return_value={}), patch('builtins.print') as output:
                handler.do_GET()
            handler.send_response.assert_called_once_with(200)
            output.assert_not_called()
            self.assertTrue(handler.close_connection)

if __name__=='__main__':unittest.main()

class IntradayMtfTests(unittest.TestCase):
    def test_optional_four_hour_and_mandatory_confirmation(self):
        frames={tf:dict(dir='LONG',available=True,fresh=True) for tf in ('5m','15m','1h')}
        frames['4h']=dict(dir='SHORT',available=False,fresh=False)
        with patch.object(server,'_mtf_score',side_effect=lambda bars,tf:frames[tf]):
            self.assertEqual(server.build_mtf_verification({})['overall'],'LONG')
            frames['15m']['dir']='NEUTRAL'
            self.assertEqual(server.build_mtf_verification({})['overall'],'NEUTRAL')

class ChartSourceTests(unittest.TestCase):
    def test_snapshot_is_not_a_closed_candle_and_times_are_not_rounded(self):
        t=1791243600
        candle=dict(t=t,o=4165.7,h=4166,l=4165.1,c=4165.5)
        points=[candle,dict(t=t+3,o=4165.5,h=4165.5,l=4165.5,c=4165.5)]
        result=server.normalize_chart_points(points,5)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['openTime'],t*1000)
        with patch.object(server.time,'time',return_value=t+10):
            self.assertTrue(server.mark_bar_state(result,5)[0]['isOpen'])
        with patch.object(server.time,'time',return_value=t+300):
            self.assertFalse(server.mark_bar_state(result,5)[0]['isOpen'])

    def test_invalid_and_duplicate_candles_remain_missing(self):
        t=1791243600
        good=dict(t=t,o=100,h=102,l=99,c=101)
        for bad in [dict(good,t=True),dict(good,h=float('inf')),dict(good,l=103),dict(good,c=True),dict(good,t=t+1)]:
            self.assertEqual(server.normalize_chart_points([bad],5),[])
        self.assertEqual(server.normalize_chart_points([good,dict(good,c=100)],5),[])
        self.assertEqual(server.normalize_chart_points([dict(good,t=t//3600*3600)],60)[0]['openTime'],t//3600*3600000)


class HistoryRefreshTests(unittest.TestCase):
    def setUp(self):
        self.independent=patch.object(server.technical_candles,"fetch",return_value=[]);self.independent.start();self.addCleanup(self.independent.stop)
        self.now=1791276000
        self.clock=patch.object(server.time,'time',return_value=self.now);self.clock.start();self.addCleanup(self.clock.stop)
        self.cache=patch.dict(server._technical_history,{},clear=True);self.cache.start();self.addCleanup(self.cache.stop)

    def point(self,age):
        return dict(t=self.now-age,o=100,h=102,l=99,c=101)

    def yahoo(self,age):
        return {'chart':{'result':[{'timestamp':[self.now-age],'indicators':{'quote':[{'open':[100],'high':[102],'low':[99],'close':[101]}]}}]}}

    def test_stale_nonempty_primary_tries_newer_fallback(self):
        with patch.object(server,'fetch_json',side_effect=[{'points':[self.point(1200)]},self.yahoo(300)]) as fetch:
            rows=server.fetch_technical_history('5m','5d')
        self.assertEqual(fetch.call_count,2)
        self.assertIn('&fresh=',fetch.call_args_list[0].args[0])
        self.assertEqual(rows[-1]['openTime'],(self.now-300)*1000)
        self.assertEqual(rows[-1]['instrument'],'GC=F')

    def test_fresh_primary_skips_fallback(self):
        with patch.object(server,'fetch_json',return_value={'points':[self.point(300)]}) as fetch:
            rows=server.fetch_technical_history('5m','5d')
        self.assertEqual(fetch.call_count,1)
        self.assertTrue(server.technical_history_fresh(rows,5))

    def test_failed_or_older_fallback_preserves_original_stale_clock(self):
        for fallback in [OSError('offline'),self.yahoo(1800)]:
            with patch.object(server,'fetch_json',side_effect=[{'points':[self.point(1200)]},fallback]):
                rows=server.fetch_technical_history('5m','5d')
            self.assertEqual(rows[-1]['openTime'],(self.now-1200)*1000)
            self.assertFalse(server.technical_history_fresh(rows,5))
            saved=server.retain_technical_history('5m',[])
            self.assertEqual(saved,rows)
            saved[0]['close']=999
            self.assertEqual(server.retain_technical_history('5m',[])[0]['close'],101)

    def test_open_bar_cannot_make_old_closed_history_fresh(self):
        rows=server.normalize_chart_points([self.point(1200),self.point(0)],5)
        self.assertFalse(server.technical_history_fresh(rows,5))
