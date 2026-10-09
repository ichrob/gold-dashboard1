import copy
import unittest
from unittest.mock import Mock
import rule_learning as r

class LearningTests(unittest.TestCase):
    def state(self):return dict(protocol=copy.deepcopy(r.PROTOCOL),phase='collection',active='baseline',history=[])
    def rows(self,a,b,good=True):
        rows=[]
        for i,s in enumerate(r.slots(a,b)):
            # Both LONG and SHORT, paired baseline and candidate, no outcome overlap.
            d='LONG' if i%2 else 'SHORT';filtered=i%3==0
            v=(-.2 if good else .2) if filtered else .1
            payload=dict(slot=s,at=s+10000,valid=True,price=100,direction=d,adx=20 if filtered else 35)
            truth=dict(at=s+10000+r.HOUR,price=100+v*(1 if d=='LONG' else -1))
            rows.append((payload,truth))
        return rows
    def test_frozen_before_holdout_and_adoption(self):
        train=self.rows(r.START,r.SPLIT-r.HOUR)
        s=r.transition(self.state(),train,r.SPLIT)
        self.assertEqual(s['phase'],'validation');self.assertEqual(s['active'],'baseline')
        valid=self.rows(s['validationStart'],r.END)
        s2=r.transition(s,train+valid,r.END)
        self.assertEqual(s2['phase'],'validation')
        done=r.transition(s,train+valid,r.END+r.HOUR+60000)
        self.assertEqual(done['phase'],'adopted');self.assertGreater(done['lowerBound99Pct'],0)
        self.assertEqual(done,r.transition(done,[],r.END+10*r.DAY))
    def test_holdout_cannot_rescue_bad_selection(self):
        s=r.transition(self.state(),self.rows(r.START,r.SPLIT,False)+self.rows(r.SPLIT,r.END),r.SPLIT)
        self.assertEqual(s['phase'],'rejected');self.assertEqual(s['active'],'baseline')
    def test_losing_holdout_and_missing_coverage_block_adoption(self):
        train=self.rows(r.START,r.SPLIT-r.HOUR);s=r.transition(self.state(),train,r.SPLIT)
        for valid in (self.rows(s['validationStart'],r.END,False),self.rows(s['validationStart'],r.END)[::2]):
            done=r.transition(s,train+valid,r.END+r.HOUR+60000)
            self.assertEqual(done['phase'],'rejected');self.assertEqual(done['active'],'baseline')
    def test_late_selection_does_not_reuse_past_holdout(self):
        now=r.SPLIT+10*r.DAY
        s=r.transition(self.state(),self.rows(r.START,r.END),now)
        self.assertGreater(s['validationStart'],now)
    def test_missing_outcome_is_not_zero_or_resampled(self):
        rows=self.rows(r.START,r.SPLIT-r.HOUR)
        first=next(i for i,(p,t) in enumerate(rows) if p['adx']==20)
        rows[first]=(rows[first][0],None)
        m=r.metrics(rows,r.START,r.SPLIT-r.HOUR,'adx25')
        self.assertEqual(m['samples'],len(rows)-1)
        self.assertLess(m['coverage'],1)
    def test_neutral_counts_coverage_but_not_sample_size(self):
        rows=self.rows(r.START,r.SPLIT-r.HOUR)
        for p,t in rows:p['direction']='NEUTRAL'
        m=r.metrics(rows,r.START,r.SPLIT-r.HOUR,'adx25')
        self.assertEqual(m['coverage'],1);self.assertEqual(m['samples'],0)
        self.assertFalse(r.sufficient(m))
    def test_protocol_change_requires_new_trial(self):
        s=self.state();s['protocol']['thresholds']=[20]
        self.assertEqual(s,r.transition(s,self.rows(r.START,r.END),r.END+2*r.HOUR))
    def test_policy_expiry_and_rollback_audit(self):
        s=self.state();s.update(phase='adopted',active='adx25')
        c=Mock();c.execute.return_value.fetchone.return_value=(s,)
        out=r.rollback(c,1000)
        self.assertEqual(out['variant'],'baseline');self.assertEqual(out['expiresAt'],121000)
        self.assertEqual(s['history'][-1]['event'],'manual-rollback')
    def test_source_validity(self):
        now=r.START+10000
        m=dict(ruleVersion=r.BASE,ready=True,priceFresh=True,price=100,dataAt=now,analysisBarAt=now-300000,direction='LONG',context={'adx':26})
        self.assertTrue(r.observation(m,now)['valid'])
        for updates in ({'priceFresh':False},{'context':{}},{'dataAt':now+1},{'ruleVersion':'other'}):
            self.assertFalse(r.observation({**m,**updates},now)['valid'])

if __name__=='__main__':unittest.main()
