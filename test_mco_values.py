import unittest
from mco_values import extract
import youtube_research as y

class ValuesTests(unittest.TestCase):
    def test_typed_values_and_units(self):
        text='XAU/USD 15 Minuten. Stand: 2026-10-17 10:00 UTC. EMA 20 bei 4.200,50. RSI (14) bei 61,8. ADX (14) bei 25. ATR (14) bei 8,5. SMA 50 bei 4100. Unterstützung bei 4050. Widerstand bei 4250. Ziel bei 4300. Stop-Loss bei 4000.'
        rows=extract([dict(at=0,text=text)])['values'];by={r['metric']:r for r in rows}
        self.assertEqual(by['ema']['price'],4200.5);self.assertEqual(by['rsi']['price'],61.8)
        self.assertEqual(by['rsi']['period'],14);self.assertEqual(by['rsi']['unit'],'Punkte')
        self.assertEqual(by['target']['price'],4300);self.assertEqual(by['stop']['price'],4000)
        self.assertEqual(by['ema']['comparisonContext']['timeframe'],'15m')
    def test_zero_negative_and_missing_parameters(self):
        rows=extract([dict(at=0,text='MACD (12,26,9) bei -1.234. MACD Signal (12,26,9) bei 0. RSI bei 50. Bollinger Oberband (20,2) bei 4250.')])['values']
        by={r['metric']:r for r in rows};self.assertEqual(by['macd']['price'],-1.234)
        self.assertEqual(by['macdSignal']['price'],0);self.assertIsNone(by['rsi']['period'])
        self.assertEqual(by['boll']['multiplier'],2)
    def test_retain_unclassified_numeric_evidence(self):
        report=extract([dict(at=1,text='Die Wahrscheinlichkeit beträgt 67 Prozent.'),dict(at=2,text='RSI (14) bei 180.')])
        self.assertFalse(report['values']);self.assertEqual(len(report['numericStatements']),2)
        self.assertEqual(report['totalNumericStatements'],2)
    def test_assessment_integrates_values(self):
        text='XAU/USD im 15 Minuten Chart. RSI (14) bei 55. '+'Wir prüfen heute die Entwicklung von Gold und die möglichen Bedingungen. '*7
        result=y.assess([dict(at=0,text=text)],'de');self.assertEqual(result['mcoValues']['values'][0]['metric'],'rsi')
    def test_limits_are_disclosed_and_no_invented_defaults(self):
        report=extract([dict(at=i,text='RSI bei 50.') for i in range(205)])
        self.assertEqual(len(report['values']),200);self.assertEqual(report['totalValues'],205)
        self.assertTrue(all(r['period'] is None for r in report['values']))

    def test_wrong_currency_and_instrument_are_not_gold_usd(self):
        rows=extract([dict(at=0,text='XAU/USD 15 Minuten. EMA 20 bei 4200 EUR.')])['values']
        self.assertIsNone(rows[0]['comparisonContext']['currency'])
        rows=extract([dict(at=0,text='XAU/USD und silver. RSI (14) bei 50.')])['values']
        self.assertIsNone(rows[0]['comparisonContext']['instrument'])
