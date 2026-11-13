"""Isolated 800/1000 EUR campaign entry policies: no broker or live gate changes."""
import copy
import unittest
import paper_portfolios as portfolio


def market(profile, direction='SHORT', rr=2.0):
    source, distance = portfolio._PAPER_CAMPAIGN_GATES[profile]
    entry=3900.
    plan={'kind':'candidate','direction':direction,'entry':entry,
          'stop':3920. if direction=='SHORT' else 3880.,
          'target':entry-(20*rr) if direction=='SHORT' else entry+(20*rr),
          'unit':'USD/oz','experimental':True,'entrySuitable':True,'source':source}
    gate={'paperOnly':True,'paperProfile':profile,'spotDistance':distance,
          'maxSignalMinutes':20,'maxDeviationAtr':1.5,'allowed':True}
    trial={'version':'campaign-entry-v1','paperOnly':True,'profile':profile,
           'source':source,'gate':gate,'plan':plan,
           'entryPlanState':{'state':'ready','reason':'paper candidate'},
           'preparation':{'entryApproved':False,'productApproved':False}}
    return {'ready':True,'priceFresh':True,'price':entry,'direction':direction,
            'plan':None,'paperCampaignEntries':{profile:trial}}


class PaperCampaignEntryTests(unittest.TestCase):
    def test_two_profiles_only_are_enabled(self):
        self.assertTrue(portfolio.POLICIES['trend800nov']['paper_campaign_entry'])
        self.assertTrue(portfolio.POLICIES['normal1000nov']['paper_campaign_entry'])
        for name in portfolio.POLICIES:
            if name not in portfolio._PAPER_CAMPAIGN_GATES:
                self.assertFalse(portfolio.POLICIES[name].get('paper_campaign_entry',False),name)

    def test_accepts_only_isolated_matching_proposals(self):
        for profile in portfolio._PAPER_CAMPAIGN_GATES:
            for side in ('LONG','SHORT'):
                m=market(profile,side)
                original=copy.deepcopy(m)
                scoped=portfolio.campaign_paper_market(m,profile)
                self.assertEqual(scoped['plan']['direction'],side)
                self.assertEqual(scoped['paperEntrySource'],portfolio._PAPER_CAMPAIGN_GATES[profile][0])
                self.assertTrue(scoped['entryTimingGate']['allowed'])
                self.assertFalse(scoped['paperCampaignPreparation']['entryApproved'])
                self.assertEqual(m,original,'input not mutated')

    def test_stale_missing_invalid_crv_and_wrong_profile_reject(self):
        for profile in portfolio._PAPER_CAMPAIGN_GATES:
            source=market(profile)
            variations=[]
            for field,value in [('priceFresh',False),('ready',False)]:
                x=copy.deepcopy(source);x[field]=value;variations.append(x)
            for field,value in [('profile','wrong'),('source','other')]:
                x=copy.deepcopy(source);x['paperCampaignEntries'][profile][field]=value;variations.append(x)
            x=copy.deepcopy(source);x['paperCampaignEntries'][profile]['gate']['allowed']=False;variations.append(x)
            x=copy.deepcopy(source);x['paperCampaignEntries'][profile]['gate']['spotDistance']=.8;variations.append(x)
            x=copy.deepcopy(source);x['paperCampaignEntries'][profile]['plan']['target']=3880.;variations.append(x)
            x=market(profile,rr=1.5);variations.append(x)
            for trial in variations:
                scoped=portfolio.campaign_paper_market(trial,profile)
                self.assertIsNone(scoped['plan'],(profile,trial))
            old=copy.deepcopy(source);del old['paperCampaignEntries']
            self.assertEqual(portfolio.campaign_paper_market(old,profile),old)

    def test_wrong_profile_not_addressable(self):
        with self.assertRaises(KeyError):
            portfolio.campaign_paper_market({},'ema3000nov')


if __name__=='__main__':
    unittest.main()
