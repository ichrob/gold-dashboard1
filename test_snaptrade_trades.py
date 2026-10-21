import copy
import unittest
import snaptrade_trades as t
import snaptrade_portfolio as p
import snaptrade_bridge as b


def row(key, side, units, price, fee='1', day='2026-10-01', **fields):
    return dict(key=key,type=side,quantity=units,price=price,fee=fee,name='Synthetic stock',
                date=day,currency='EUR',securityCurrency='EUR',securityKind='cs',
                securityKey='synthetic-security',amount=None,**fields)


def report(rows, complete=True):
    return t.build({'activities':{'rows':rows,'complete':complete,'code':'READ_OK','checkedAt':'2026-10-21T12:00:00Z'}})


class TradesTests(unittest.TestCase):
    def test_fifo_partial_sales_allocate_purchase_fees_once(self):
        rows=[row('b','BUY','10','10',fee='2'),row('s1','SELL','4','12',day='2026-10-02'),row('s2','SELL','6','11',day='2026-10-03')]
        out=report(list(reversed(rows)))
        self.assertEqual(len(out['events']),3)
        self.assertEqual(len(out['realized']),2)
        self.assertEqual(out['totals'],[dict(currency='EUR',sales=2,grossPnl='14.0',netPnl='10.0')])
        self.assertEqual(out['realized'][0]['openQuantityAfter'],'0')
        self.assertEqual(out['realized'][1]['fees'],'1.8')
        self.assertEqual(report(rows),report(rows),'Repeated fetches do not accumulate duplicate trades')
        self.assertFalse(out['learningEligible'])

    def test_multiple_lots_and_fifo_not_average_cost(self):
        out=report([row('b1','BUY','2','10',day='2026-10-01'),row('b2','BUY','2','20',day='2026-10-02'),row('s','SELL','3','30',day='2026-10-03')])
        sale=out['realized'][0]
        self.assertEqual(sale['cost'],'40.0')
        self.assertEqual(sale['grossPnl'],'50.0')
        self.assertEqual(sale['fees'],'2.5')
        self.assertEqual(sale['openQuantityAfter'],'1')

    def test_missing_fee_stays_unknown_and_cash_movement_is_not_profit(self):
        out=report([row('b','BUY','1','10',fee=None),row('s','SELL','1','11',day='2026-10-02'),
                    dict(key='cash',type='CONTRIBUTION',amount='1000',currency='CHF')])
        self.assertIsNone(out['realized'][0]['netPnl'])
        self.assertIsNone(out['totals'][0]['netPnl'])
        self.assertEqual(len(out['cashMovements']),1)

    def test_incomplete_history_unmatched_sell_and_adjustments_block(self):
        base=[row('b','BUY','1','10'),row('s','SELL','1','11',day='2026-10-02')]
        for rows,complete in [(base,False),([base[1]],True),(base+[dict(base[0],key='split',type='SPLIT')],True),
                              (base+[dict(base[0],key='split',type='SPLIT',currency=None)],True),
                              (base+[dict(key='transfer',type='TRANSFER',name='Unknown transfer')],True),
                              (base+[row('s2','SELL','1','12',day='2026-10-03')],True)]:
            out=report(rows,complete)
            self.assertEqual(out['realized'],[])
            self.assertTrue(out['unresolved'])

    def test_ambiguous_same_day_order_and_naive_timestamp_block(self):
        for date in ('2026-10-01','2026-10-01T00:00:00Z','2026-10-01T12:00:00'):
            out=report([row('b','BUY','1','10',day=date),row('s','SELL','1','11',day='2026-10-01T13:00:00Z')])
            self.assertEqual(out['realized'],[])
        out=report([row('b','BUY','1','10',day='2026-10-01T12:00:00Z'),row('s','SELL','1','11',day='2026-10-01T13:00:00Z')])
        self.assertEqual(len(out['realized']),1)

    def test_options_multipliers_fx_and_bad_cash_never_guessed(self):
        for changes in ({'securityKind':'op'},{'optionType':'BUY_TO_OPEN'}, {'amount':'-1000'},
                        {'currency':'CHF','securityCurrency':'EUR','fxRate':'.9'}, {'quantity':'NaN'}):
            buy=row('b','BUY','1','10');buy.update(changes)
            self.assertEqual(report([buy,row('s','SELL','1','11',day='2026-10-02')])['realized'],[])

    def test_unknown_unit_certificate_requires_cash_arithmetic_proof(self):
        buy=row('b','BUY','2','10',fee='1');buy.update(securityKind='other',amount='-21')
        sell=row('s','SELL','2','12',fee='1',day='2026-10-02');sell.update(securityKind='other',amount='23')
        out=report([buy,sell])
        self.assertEqual(out['realized'][0]['netPnl'],'2')
        buy['amount']='-999'
        self.assertEqual(report([buy,sell])['realized'],[])

    def test_external_fee_is_visible_but_never_double_counted(self):
        buy=row('b','BUY','1','10');buy['externalReference']='ref'
        out=report([buy,row('s','SELL','1','12',day='2026-10-02'),dict(key='f',type='FEE',externalReference='ref',amount='-1',currency='EUR')])
        self.assertEqual(len(out['separateCharges']),1)
        self.assertIsNone(out['realized'][0]['netPnl'])

    def test_currencies_and_identity_do_not_merge_by_name(self):
        buy=row('b','BUY','1','10');sell=row('s','SELL','1','11',day='2026-10-02');sell['securityKey']='different'
        self.assertEqual(report([buy,sell])['realized'],[])
        buy['securityKey']=None
        self.assertTrue(report([buy])['unresolved'])

    def test_normalization_keeps_native_currency_and_hashed_ids(self):
        raw=dict(id='activity-secret',symbol={'id':'instrument-secret','symbol':'TEST','currency':{'code':'EUR'},'type':{'code':'cs'}},
                 type='BUY',trade_date='2026-10-01',currency=None,units=1,price=10,fee=None,external_reference_id='external-secret')
        got=p.journal_rows([raw],'activities',b.number,b.text)[0]
        self.assertEqual(got['currency'],'EUR')
        self.assertIsNone(got['fee'])
        self.assertNotIn('secret',str(got))
        self.assertEqual(got['securityCurrency'],'EUR')


if __name__=='__main__':unittest.main()
