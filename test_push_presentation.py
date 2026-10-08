import unittest
import background_push as p

class Presentation(unittest.TestCase):
    def event(self,kind,body):
        return {'title':kind,'body':body,'data':{'eventKind':kind,'kind':'general' if kind=='signal-change' else 'trade'}}

    def test_urgent_keeps_risks_not_conflicting_plans(self):
        events=[self.event('target-extension','new target'),self.event('stop-hit','stop hit'),self.event('ko-hit','KO'),self.event('personal-risk','budget')]
        message=p.compose_events(events)
        self.assertEqual(message['title'],'ko-hit')
        self.assertEqual(message['body'],'KO | stop hit | budget')
        self.assertEqual(len(message['data']['events']),4)
        self.assertEqual(events[0]['body'],'new target')

    def test_target_merge_and_separate_entry(self):
        events=[self.event('target','target reached'),self.event('target-extension','new target'),self.event('signal-change','LONG')]
        result=p.present_events(events,{'trade':{'dir':'SHORT'}},{'trendContext':{'available':True,'intact':True,'direction':'SHORT'}})
        self.assertEqual(len(result),2)
        self.assertIn('Dein SHORT-Trade: Haupttrend intakt',result[1]['body'])
        self.assertEqual(p.compose_events(result)['title'],'target-extension')

if __name__=='__main__':unittest.main()
