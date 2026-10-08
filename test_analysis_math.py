"""Cross-runtime agreement and independent analysis boundaries."""
import json
import math
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import server

NOW = 1800000000000

class AnalysisMathTests(unittest.TestCase):
    def test_one_minute_context_uses_one_minute_timing(self):
        bars=[dict(openTime=NOW-(220-i)*60000,open=100,close=100,high=101,low=99,isOpen=False) for i in range(220)]
        with patch.object(server.time,'time',return_value=NOW/1000):
            self.assertTrue(server._mtf_score(bars,'1m')['available'])
        with patch.object(server.time,'time',return_value=(NOW+60001)/1000):
            self.assertFalse(server._mtf_score(bars,'1m')['available'])

    def test_browser_server_collective_agreement(self):
        fixtures=[]
        for phase in range(20):
            values=[4200+i*.02+5*math.sin(i/7+phase/3) for i in range(240)]
            fixtures.append([dict(openTime=NOW-(240-i)*300000,open=v,close=v,high=v+1,low=v-1,isOpen=False) for i,v in enumerate(values)])
        for price in (100,4200):
            fixtures.append([dict(openTime=NOW-(240-i)*300000,open=price,close=price,high=price,low=price,isOpen=False) for i in range(240)])
        script="""
const fs=require('fs'),vm=require('vm'),input=JSON.parse(fs.readFileSync(0,'utf8')),html=fs.readFileSync('Bob.html','utf8');
const core=html.slice(html.indexOf('function ema('),html.indexOf('function calc('));
const score=html.slice(html.indexOf('function rsiS('),html.indexOf('function buildMtfHierarchy('));
const env={dataAge:(t,limit,now)=>({fresh:now>=t&&now-t<=limit})};vm.createContext(env);vm.runInContext(core+score,env);
process.stdout.write(JSON.stringify(input.fixtures.map(b=>env.timeframeScore(b,'5m',input.now))));
"""
        browser=json.loads(subprocess.check_output(['node','-e',script],input=json.dumps(dict(fixtures=fixtures,now=NOW)),text=True))
        with patch.object(server.time,'time',return_value=NOW/1000):
            for bars,js in zip(fixtures,browser):
                py=server._mtf_score(bars,'5m')
                self.assertTrue(py['available']);self.assertTrue(js['available'])
                self.assertEqual(py['dir'],js['dir'])
                self.assertEqual(py['score'],js['score'])
                self.assertAlmostEqual(py['rsi'],js['rsi'],places=1)

    def test_rsi_first_full_period(self):
        self.assertEqual(server._rsi(list(range(100,115))),100)
        self.assertEqual(server._rsi([100]*15),50)

    def test_mtf_invalid_ohlc_and_recent_gap(self):
        bars=[dict(openTime=NOW-(220-i)*300000,open=100,close=100,high=101,low=99,isOpen=False) for i in range(220)]
        with patch.object(server.time,'time',return_value=NOW/1000):
            self.assertFalse(server._mtf_score(bars[:-2]+bars[-1:],'5m')['available'])
            bars[-1]['low']=102
            self.assertFalse(server._mtf_score(bars,'5m')['available'])
