import unittest
from video_values import extract
from video_ocr_evaluation import score,aggregate,promotion_allowed

class VideoValueTests(unittest.TestCase):
    def read(self,*texts):return extract([dict(text=t) for t in texts])
    def test_types_and_explicit_context(self):
        data=self.read('XAU/USD 15m','Gold: 4200.50','EMA 20: 4199.40','RSI (14): 61.8','Fib 61.8%: 4180.5','Target: 4250','Stop: 4100')
        self.assertEqual([v['metric'] for v in data['values']],['goldPrice','ema','rsi','fibonacci','target','stop'])
        self.assertEqual(self.read('XAU/USD15m','Gold: 4200')['timeframe'],'15m');
        self.assertEqual(data['values'][2]['period'],14);self.assertEqual(data['values'][3]['ratio'],61.8)
        self.assertTrue(all(not v['verified'] and v['marketTimeStatus']=='unknown' for v in data['values']))
    def test_unlabeled_ambiguous_and_mixed_values_stay_open(self):
        self.assertFalse(self.read('4200.50')['values'])
        self.assertFalse(self.read('Gold: 4.200')['values'])
        self.assertEqual(self.read('Gold: 4,200.50')['values'][0]['value'],4200.5)
        data=self.read('XAU/USD 15m EUR 1h','EMA 20: 4200')
        self.assertIsNone(data['currency']);self.assertIsNone(data['timeframe']);self.assertFalse(data['values'][0]['contextComplete'])
        self.assertIsNone(self.read('XAU/USD CFD 15m','Gold: 4200')['instrument'])
        self.assertEqual(self.read('RSI: 61.8')['values'][0]['period'],None)
    def test_scoring_wrong_labels_and_promotion_gate(self):
        expected=[dict(metric='rsi',value=61.8,unit='Punkte')]
        self.assertEqual(score(expected,[dict(metric='goldPrice',value=61.8,unit='USD')]),dict(correct=0,wrong=1,missed=1))
        self.assertFalse(promotion_allowed({}))
        report=dict(status='evaluated',engine='rapidocr-local-v3',candidate='contrast',disjointSets=True,holdoutImages=8)
        for split in ('development','holdout'):report[split]=dict(baseline=dict(error=3,wrong=1,correct=4),contrast=dict(error=1,wrong=0,correct=5))
        self.assertTrue(promotion_allowed(report));report['holdout']['contrast']['wrong']=2
        self.assertFalse(promotion_allowed(report))

class RuntimeBenchmarkTests(unittest.TestCase):
    def test_actual_separate_image_benchmark(self):
        try:import rapidocr_onnxruntime
        except ImportError:self.skipTest('Offline OCR dependencies unavailable')
        from video_ocr_evaluation import evaluate,source_fingerprint
        import video_ocr
        report=evaluate();stored=video_ocr.evaluation_report()
        self.assertEqual(stored['status'],'evaluated');self.assertEqual(stored['sourceFingerprint'],source_fingerprint())
        self.assertTrue(report['disjointSets']);self.assertEqual(report['holdoutImages'],8)
        for split in ('development','holdout'):
            for profile in ('baseline','contrast'):
                self.assertEqual(report[split][profile],stored[split][profile])
        self.assertEqual(report['activeProfile'],stored['activeProfile'])
