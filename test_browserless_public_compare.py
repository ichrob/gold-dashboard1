import unittest

from browserless_public_compare import compare, _number


class PublicComparisonTests(unittest.TestCase):
    def setUp(self):
        self.research={'isin':'DE000FB0A490','state':'unverified-research',
                       'fields':{'direction':'Put','knockOut':'4.151,2285 USD',
                                 'bid':'0,90 EUR','quoteTime':'heute 21:00'}}
        self.issuer={'isin':'DE000FB0A490','productVerified':True,
                     'source':'SG · offizieller Produktnachweis',
                     'metadata':{'direction':'SHORT','ko':4151.2285},
                     'chartEvidence':{'pointAt':'2026-11-19T16:00:00+01:00'}}

    def test_statically_equal_not_execution(self):
        c=compare(self.research,self.issuer)
        self.assertEqual(c['state'],'static-fields-match')
        self.assertEqual(c['matches'],['direction','knockOut'])
        self.assertFalse(c['tradeApproved'])
        self.assertFalse(c['executableQuoteVerified'])
        self.assertFalse(c['originalQuoteTimeVerified'])
        self.assertEqual(c['issuerObservationAt'],'2026-11-19T16:00:00+01:00')

    def test_ko_mismatch_detected(self):
        self.research['fields']['knockOut']='4.120,0000 USD'
        self.assertEqual(compare(self.research,self.issuer)['mismatches'],['knockOut'])

    def test_non_identity_or_unverified_source_not_accepted(self):
        self.issuer['isin']='DE000FG77FN1'
        self.assertEqual(compare(self.research,self.issuer)['state'],'reference-unavailable')
        self.issuer['isin']='DE000FB0A490'
        self.issuer['productVerified']=False
        self.assertEqual(compare(self.research,self.issuer)['state'],'reference-unavailable')

    def test_invalid_directions_not_guessed(self):
        self.research['fields']['direction']='evtl. Put'
        c=compare(self.research,self.issuer)
        self.assertIn('direction',c['unknown'])
        self.assertFalse(c['tradeApproved'])

    def test_localized_numeric_reject_ambiguous(self):
        self.assertEqual(_number('4.151,2285 USD'),4151.2285)
        self.assertIsNone(_number('4,151.2285 USD'))
        self.assertIsNone(_number('unbekannt'))
        self.assertIsNone(_number(None))


if __name__ == '__main__':
    unittest.main()
