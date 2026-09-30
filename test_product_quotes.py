import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
import product_quotes as q

ISIN='DE000PJ9NCK0'
NOW=datetime(2026,9,30,15,42,20,tzinfo=timezone.utc)
def page():
    fields=dict(bid='15,92',ask='15,93',leverage='23,00',bidsize='8.000',asksize='8.000',quotetime='30.09.2026 17:42:17')
    return ('<script type="application/ld+json">{"@type":"FinancialProduct","identifier":"'+ISIN+'","name":"GOLD Unlimited Long"}</script>Markt geöffnet Knock-Out Schwelle (30.09.2026) 3.978,9026 USD '+''.join(('€ ' if k in ('bid','ask') else '')+'<span data-item="X000'+ISIN+'" data-field="'+k+'">'+v+'</span>' for k,v in fields.items())+'<span data-item="underlying" data-field="quotetime">17:42:20</span>')

class ProductQuoteTests(unittest.TestCase):
    def test_current_product_timestamp_and_european_numbers(self):
        x=q.parse_bnp(page(),ISIN,NOW)
        self.assertTrue(x['eligible']);self.assertEqual(x['ageSeconds'],3)
        self.assertEqual(x['price'],15.93);self.assertEqual(x['spread'],.01)
        self.assertEqual(x['ko'],3978.9026);self.assertFalse(x['isDegiroQuote'])
    def test_stale_cached_quote_expires_without_refetch(self):
        x=q.parse_bnp(page(),ISIN,NOW)
        self.assertFalse(q.freshness(x,NOW+timedelta(seconds=60))['eligible'])
    def test_future_closed_and_missing_timestamp(self):
        self.assertFalse(q.parse_bnp(page(),ISIN,NOW-timedelta(seconds=10))['eligible'])
        self.assertFalse(q.parse_bnp(page().replace('geöffnet','geschlossen'),ISIN,NOW)['eligible'])
        with self.assertRaises(ValueError):q.parse_bnp(page().replace('30.09.2026 17:42:17','17:42:17'),ISIN,NOW)
    def test_wrong_identity_crossed_quotes_and_old_ko(self):
        for html in [page().replace('"identifier":"'+ISIN+'"','"identifier":"DE000FC1CHB7"'),page().replace('15,93','15,91'),page().replace('Schwelle (30.09.2026)','Schwelle (29.09.2026)')]:
            with self.assertRaises(ValueError):q.parse_bnp(html,ISIN,NOW)
    def test_checksum_and_arbitrary_url_blocked(self):
        with patch.object(q,'urlopen') as fetch:
            for value in ['https://localhost','DEOOOPJONB98','DE000PJ9NCK1']:
                self.assertFalse(q.get_quote(value)['eligible'])
            fetch.assert_not_called()
    def test_no_underlying_timestamp_substitution(self):
        html=page().replace('data-field="quotetime">30.09.2026 17:42:17','data-field="other">30.09.2026 17:42:17')
        with self.assertRaises(ValueError):q.parse_bnp(html,ISIN,NOW)

if __name__=='__main__':unittest.main()
