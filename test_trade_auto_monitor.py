import unittest
from datetime import datetime,timezone
from unittest.mock import Mock,patch
import trade_auto_monitor as a
import trade_workflow as w

class AutoMonitorTests(unittest.TestCase):
 def receipt(self):
  return dict(isin='DE000FG309G0',side='BUY',quantity=2,priceEur=10,status='pending-review',orderIdDigest='a'*64,executedLocal='14.10.2026 13:00:00')
 def quote(self):
  return dict(isin='DE000FG309G0',productVerified=True,currency='EUR',bid=10,bidAt='2026-10-14T11:00:00Z',
   metadata=dict(currency='EUR',direction='LONG',underlyingType='SPOT',ratio=.1,strike=3900,ko=3900),
   productModel=dict(isin='DE000FG309G0',verifiedSimpleTurbo=True))
 def lookup(self,when,currency):
  return dict(available=True,originalTime=when,maxSkewSeconds=30,goldReference=4000,fxReference=.9)
 def test_product_identity_currency_and_reference_required(self):
  p=a.product_reference(self.quote(),self.receipt(),self.lookup)
  self.assertTrue(p['referenceConfirmed']);self.assertEqual(p['entry'],10)
  for mutate in ({'productVerified':False},{'productModel':{}},{'isin':'OTHER'}):
   with self.assertRaises(ValueError):a.product_reference({**self.quote(),**mutate},self.receipt(),self.lookup)
  q=self.quote();q['metadata']['currency']='CHF'
  with self.assertRaises(ValueError):a.product_reference(q,self.receipt(),self.lookup)
  with self.assertRaises(ValueError):a.product_reference(self.quote(),self.receipt(),lambda *_:dict(available=False))
 def test_original_and_forwarded_copy_do_not_block_but_other_fill_does(self):
  r=self.receipt();copy={**r,'totalChf':20}
  now=datetime(2026,10,14,14,tzinfo=timezone.utc)
  self.assertTrue(w.eligible_purchase(r,[r,copy],now))
  self.assertFalse(w.eligible_purchase(r,[r,{**copy,'orderIdDigest':'b'*64}],now))
  self.assertFalse(w.eligible_purchase(r,[r,{**copy,'side':'SELL'}],now))
 def test_active_trade_skips_network(self):
  c=Mock();c.execute.return_value.fetchone.return_value=(1,)
  db=Mock();db.return_value.__enter__=Mock(return_value=c);db.return_value.__exit__=Mock(return_value=False)
  fetch=Mock();a.tick(db,{},quote_fetch=fetch);fetch.assert_not_called()
 def test_delay_is_not_backdated(self):
  out=a.timing(dict(purchase=dict(executedLocal='14.10.2026 13:00:00'),monitorStartedAt='2026-10-14T11:00:30Z'))
  self.assertEqual(out['delaySeconds'],30);self.assertTrue(out['timezoneAssumed'])
 def test_closed_trade_never_reopens(self):
  r=self.receipt();c=Mock();c.execute.return_value.fetchone.side_effect=[None,(False,{'active':False})]
  c.execute.return_value.fetchall.return_value=[('mail',{'result':r})]
  db=Mock();db.return_value.__enter__=Mock(return_value=c);db.return_value.__exit__=Mock(return_value=False)
  fetch=Mock()
  with patch.object(w,'eligible_purchase',return_value=True):a.tick(db,{},quote_fetch=fetch)
  fetch.assert_not_called()

class ServerActivationTests(AutoMonitorTests):
 def test_server_start_uses_checked_model_and_real_purchase(self):
  from contextlib import contextmanager
  c=Mock();r=self.receipt()
  c.execute.return_value.fetchall.return_value=[('mail',{'result':r})]
  pending={'tradeId':'degiro-email-'+'a'*64,'recordOnly':True,'active':False,'purchase':{'executedLocal':r['executedLocal']}}
  c.execute.return_value.fetchone.side_effect=[None,None,None,(False,pending)]
  @contextmanager
  def db():yield c
  market=dict(ready=True,priceFresh=True,monitorPlan=dict(direction='LONG',entry=4000,stop=3980,target=4040))
  with patch.object(w,'eligible_purchase',return_value=True),patch.object(w,'import_purchase',return_value={'tradeId':pending['tradeId']}),patch.object(a.curve,'calculate',return_value={'fxRate':.9}),patch.object(a.bp,'analyze',return_value=market),patch('real_trade_journal.handle') as save,patch('real_trade_journal.event'),patch('real_trade_journal.sync_devices'):
   a.tick(db,{},quote_fetch=lambda _:self.quote(),lookup=self.lookup)
  trade=save.call_args.args[2]['trade']
  self.assertTrue(trade['active']);self.assertEqual(trade['product']['entry'],10)
  self.assertEqual(trade['stop'],3980);self.assertEqual(trade['purchase'],pending['purchase'])
 def test_sale_during_lookup_aborts_activation(self):
  from contextlib import contextmanager
  c=Mock();r=self.receipt();c.execute.return_value.fetchall.return_value=[('mail',{'result':r})]
  c.execute.return_value.fetchone.side_effect=[None,None,None]
  @contextmanager
  def db():yield c
  market=dict(ready=True,priceFresh=True,monitorPlan=dict(direction='LONG',entry=4000,stop=3980,target=4040))
  with patch.object(w,'eligible_purchase',return_value=True),patch.object(w,'import_purchase',side_effect=ValueError('Verkauf vorhanden')),patch.object(a.curve,'calculate',return_value={'fxRate':.9}),patch.object(a.bp,'analyze',return_value=market),patch('real_trade_journal.handle') as save:
   with self.assertRaises(ValueError):a.tick(db,{},quote_fetch=lambda _:self.quote(),lookup=self.lookup)
   save.assert_not_called()
