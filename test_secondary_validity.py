import unittest
from unittest.mock import patch
from datetime import datetime, timezone
import secondary_validity as s

ISIN='DE000FG34XV8'
NOW=datetime(2026,10,7,15,tzinfo=timezone.utc)
URL=s.sources(ISIN)[1][1]
PAGE='''<h1>Gold (USD) ISIN DE000FG34XV8</h1><table>
<tr><td>Strike (07.10.2026)</td><td>4’524.4731</td><td>Knock-Out (07.10.2026)</td><td>4’524.4731</td></tr></table>'''
PRIMARY=dict(isin=ISIN,importActive=True,productVerified=True,found=False,eligible=False,
 metadata=dict(status=1,termsDated=False,ko=4524.473138,strike=4524.473138),conditions={})

class SecondaryValidityTests(unittest.TestCase):
 def row(self, html=PAGE):return s.parse_page(html,ISIN,'finanzen.ch',URL,NOW)
 def apply(self, rows, p=PRIMARY):
  with patch.object(s,'get_evidence',return_value=rows):return s.apply(p,ISIN,NOW)
 def test_dates_and_precision_confirm_without_promoting_quote(self):
  r=self.apply([self.row()])
  self.assertTrue(r['metadata']['termsDated']);self.assertFalse(r['eligible']);self.assertFalse(r['found'])
  self.assertIsNone(r['conditions']['ko']['at']);self.assertEqual(r['conditions']['ko']['dateText'],'07.10.2026')
  self.assertFalse(PRIMARY['metadata']['termsDated'])
 def test_quote_issue_and_retrieval_dates_never_date_terms(self):
  for page in [PAGE.replace(' (07.10.2026)','')+'<div>Kurszeit 07.10.2026 Emissionstag 07.10.2026</div>',PAGE.replace('07.10.2026','06.10.2026'),PAGE.replace('07.10.2026','08.10.2026'),PAGE.replace('07.10.2026','99.10.2026')]:
   r=self.apply([self.row(page)]);self.assertFalse(r['metadata']['termsDated']);self.assertEqual(r['secondaryValidity']['state'],'open')
 def test_conflict_and_wrong_identity(self):
  bad=self.row(PAGE.replace('4’524.4731','4’526.54'))
  self.assertFalse(self.apply([self.row(),bad])['metadata']['termsDated'])
  with self.assertRaises(ValueError):self.row(PAGE.replace(ISIN,'DE000FG7EPT1'))
 def test_partial_and_terminal(self):
  r=self.apply([self.row(PAGE.replace('Knock-Out (07.10.2026)','Knock-Out'))])
  self.assertEqual(r['secondaryValidity']['state'],'partial');self.assertIn('strike',r['conditions']);self.assertNotIn('ko',r['conditions'])
  for meta in [dict(status=2),dict(status=1,termsDated=True),dict(status=1,termsFixed=True)]:
   p=dict(PRIMARY,metadata=meta)
   with patch.object(s,'get_evidence') as get:self.assertEqual(s.apply(p,ISIN,NOW),p);get.assert_not_called()
 def test_duplicate_rows_and_non_usd_rejected(self):
  page=PAGE+PAGE.replace('4’524.4731','4’526.54')
  self.assertFalse(self.apply([self.row(page)])['metadata']['termsDated'])
  self.assertEqual(self.row(PAGE.replace('Gold (USD)','Gold (EUR)'))['terms'],{})
 def test_comdirect_explicit_field_date(self):
  html='<h2>WKN: FG34XV ISIN: '+ISIN+'</h2><table><tr><th>Basispreis (07.10.2026)</th><td>4.524,4731 USD</td></tr></table>'
  r=s.parse_page(html,ISIN,'comdirect',s.sources(ISIN)[0][1],NOW)
  self.assertTrue(r['terms']['strike']['conditionVerified'])
 def test_cache_does_not_retimestamp_and_background_is_bounded(self):
  with patch.dict(s._CACHE,{ISIN:(s.time.monotonic(),[self.row()])},clear=True),patch.object(s._POOL,'submit') as submit:
   self.assertEqual(s.get_evidence(ISIN)[0]['checkedAt'],NOW.isoformat());submit.assert_not_called()
  with patch.dict(s._CACHE,{},clear=True),patch.object(s,'_PENDING',set()),patch.object(s._POOL,'submit') as submit:
   self.assertEqual(s.get_evidence(ISIN)[0]['state'],'checking');s.get_evidence(ISIN);self.assertEqual(submit.call_count,1)

if __name__=='__main__':unittest.main()
