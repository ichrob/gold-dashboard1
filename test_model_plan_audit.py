"""Private bounded per-ISIN original/model reference audit, not fills."""
import unittest
from datetime import datetime,timezone
from unittest.mock import patch
import handset_planning


class ModelPlanAuditTests(unittest.TestCase):
    def test_all_screen_rows_including_exclusions_and_stale_are_explicit(self):
        products=[
            {'isin':'DE000SQ02JQ6','direction':'LONG','state':'analysis-evidence-complete'},
            {'isin':'DE000FB0A490','direction':'SHORT','state':'analysis-evidence-complete'},
            {'isin':'DE000FA9UFD4','direction':'LONG','state':'terminated'},
            {'isin':'DE000PU0D101','direction':'LONG','state':'excluded-factor'}]
        now=int(datetime(2026,11,16,18,0,tzinfo=timezone.utc).timestamp()*1000)
        source=dict(items=products,listUploadedAt='2026-11-16T13:38:00Z')
        plan=dict(resultFresh=True,result={
            'listUploadedAt':source['listUploadedAt'],'calculatedAt':now-10000,
            'items':[
                dict(isin=products[0]['isin'],planState='model-only-reference',
                    modelMode='anchored-estimate',modelStop=17.3,modelTarget=25.4,
                    modelCurrency='EUR',modelReferenceAt='2026-11-16T17:57:00Z',
                    modelOriginalGoldAt='2026-11-16T17:59:50Z',modelFxAt='2026-11-16T17:59:50Z'),
                dict(isin=products[1]['isin'],planState='reference-unavailable',
                    modelMode=None,modelStop=None,modelTarget=None,
                    modelEvidenceCode='DATED_TERMS_MISSING',
                    modelEvidenceMissing=['ko','strike'],
                    modelEstimateReason='Datierten KO-/Basispreisnachweis prüfen',
                    goldReference={'state':'available','direction':'SHORT',
                        'unit':'USD/oz','entry':4200,'stop':4230,'target':4140,
                        'sourceAt':'2026-11-16T17:59:50Z','entrySuitable':True},
                    reasons=['Produktkurs und Vertragsquelle fehlen'])]})
        with patch('degiro_product_audit.read',return_value=source),patch.object(
                handset_planning,'read',return_value=plan):
            result=handset_planning.model_plan_audit(object(),now=now)
        self.assertEqual(result['listed'],4)
        self.assertEqual(result['modeled'],1)
        self.assertEqual(result['blocked'],1)
        self.assertEqual(result['excluded'],2)
        self.assertTrue(result['readOnly'])
        self.assertFalse(result['realOrders'])
        self.assertFalse(result['items'][0]['tradeApproved'])
        self.assertEqual(result['items'][0]['modelStop'],17.3)
        self.assertEqual(result['items'][1]['status'],'unavailable')
        self.assertEqual(result['goldReferences'],1)
        self.assertEqual(result['goldOnly'],1)
        self.assertEqual(result['items'][1]['goldReference']['stop'],4230)
        self.assertEqual(result['items'][1]['goldReference']['target'],4140)
        self.assertFalse(result['items'][1]['goldReference']['modelTradeApproved'])
        self.assertEqual(result['items'][1]['modelEvidenceCode'],'DATED_TERMS_MISSING')
        self.assertEqual(result['items'][1]['modelEvidenceMissing'],['ko','strike'])
        self.assertEqual(result['items'][2]['status'],'terminated')
        self.assertEqual(result['items'][3]['status'],'excluded-factor')
        # Intermittent issuer reads must never promote a previously terminal
        # or unconfirmed row to a plan just because Gold itself is fresh.
        source['items'][1]['state']='incomplete'
        with patch('degiro_product_audit.read',return_value=source),patch.object(
                handset_planning,'read',return_value=plan):
            uncertain=handset_planning.model_plan_audit(object(),now=now)
        self.assertEqual(uncertain['goldReferences'],0)
        self.assertEqual(uncertain['goldOnly'],0)
        self.assertEqual(uncertain['items'][1]['goldReference']['state'],'unavailable')
        source['items'][1]['state']='analysis-evidence-complete'
        plan['resultFresh']=False
        with patch('degiro_product_audit.read',return_value=source),patch.object(
                handset_planning,'read',return_value=plan):
            stale=handset_planning.model_plan_audit(object(),now=now+100000)
        self.assertEqual(stale['status'],'not-current')
        self.assertEqual(stale['modeled'],0)
        self.assertEqual(stale['blocked'],2)
        self.assertTrue(all(x['modelStop'] is None for x in stale['items']))
        self.assertEqual(stale['goldReferences'],0)
        self.assertEqual(stale['goldOnly'],0)
        self.assertTrue(all(x['goldReference']['state']=='unavailable' for x in stale['items']))


if __name__=='__main__':
    unittest.main()
