import unittest
from research_overview import overview

class OverviewTests(unittest.TestCase):
    def test_scans_late_scenarios_and_keeps_conditions_numbers(self):
        segments=[{'at':0,'text':'Gold befindet sich heute in einer Korrektur.'},
                  {'at':40,'text':'Bitte abonnieren und den Rabatt beim Broker nutzen.'},
                  {'at':150,'text':'Die Unterstützung liegt bei 4.165 und das Ziel bei 4.300.'},
                  {'at':350,'text':'Falls Gold den Widerstand nicht überwindet, bleibt das bärische Szenario gültig.'},
                  {'at':480,'text':'Wenn Gold den Widerstand überwindet, ist ein bullisches Szenario für nächste Woche möglich.'}]
        result=overview(segments,'de')
        texts=' '.join(x['text'] for x in result['evidence'])
        self.assertIn('4.165',texts);self.assertIn('4.300',texts)
        self.assertIn('nicht überwindet',texts);self.assertIn('Wenn Gold',texts)
        self.assertNotIn('Rabatt',texts)
        self.assertTrue(any(e['at']==480 for e in result['evidence']))
        self.assertLessEqual(len(result['moments']),5)
        self.assertEqual(result['sourceWords'],sum(len(s['text'].split()) for s in segments))
        self.assertTrue(all(e['text'] in ' '.join(s['text'] for s in segments) for e in result['evidence']))
    def test_visual_moments_can_cover_both_scenarios_and_levels(self):
        segments = [
            {'at': 0, 'text': 'Gold befindet sich aktuell in einer Korrektur.'},
            {'at': 60, 'text': 'Der Goldpreis könnte steigen und ein bullisches Szenario bilden.'},
            {'at': 180, 'text': 'Das bärische Szenario würde Gold wieder fallen lassen.'},
            {'at': 300, 'text': 'Die Unterstützung bei Gold liegt bei 4100 und der Widerstand bei 4200.'},
            {'at': 420, 'text': 'Falls Gold über 4200 steigt, verändert sich die Einordnung.'},
        ]
        result = overview(segments, 'de')
        self.assertGreaterEqual(len(result['moments']), 3)
        self.assertLessEqual(len(result['moments']), 5)
        self.assertTrue(all(m['at'] in {0, 60, 180, 300, 420} for m in result['moments']))

    def test_caption_boundaries_do_not_drop_negation(self):
        result=overview([{'at':10,'text':'Falls Gold den Widerstand nicht'}, {'at':15,'text':'überwindet, bleibt das bärische Szenario gültig.'}],'de')
        self.assertEqual(result['evidence'][0]['at'],10)
        self.assertIn('nicht überwindet',result['evidence'][0]['text'])
    def test_absence_is_not_invented(self):
        result=overview([{'at':0,'text':'Gold bewegt sich in einer engen Handelsspanne.'}],'de')
        self.assertEqual(next(s for s in result['sections'] if s['key']=='bullish')['status'],'not_identified')
        self.assertIsNone(overview([{'at':0,'text':'bonjour'}],'fr'))
    def test_unsplit_long_text_is_not_truncated_into_false_claim(self):
        result=overview([{'at':0,'text':'Gold '+('bullish ' * 150)+'unless the condition fails'}],'en')
        self.assertEqual(result['evidence'],[])

if __name__=='__main__':unittest.main()
