import os,time,unittest
from unittest.mock import patch
import server,bob_diagnostics

class HistoryBasisTests(unittest.TestCase):
    def test_future_cannot_evict_spot_and_recovery_can_replace_future(self):
        now=1791276000
        spot=[dict(openTime=(now-1200)*1000,instrument='XAU/USD',isOpen=False)]
        future=[dict(openTime=(now-300)*1000,instrument='GC=F',isOpen=False)]
        with patch.object(server.time,'time',return_value=now),patch.dict(server._technical_history,{},clear=True):
            server.retain_technical_history('5m',spot)
            self.assertEqual(server.retain_technical_history('5m',future),spot)
            server._technical_history['5m']=future
            self.assertEqual(server.retain_technical_history('5m',spot),spot)
            self.assertFalse(server.technical_history_fresh(spot,5))

    def test_aggregation_preserves_provenance_and_estimation(self):
        at=1791275400000
        rows=[dict(openTime=at+i*300000,instrument='XAU/USD',source='fixture',estimated=i==1,open=100,high=102,low=99,close=101,isOpen=False) for i in range(3)]
        result=server.aggregate_bars(rows,15)[0]
        self.assertEqual(result['source'],'fixture');self.assertTrue(result['estimated'])

    def test_diagnostic_attention_includes_basis_gaps_and_recurrence(self):
        result=bob_diagnostics.summary({'frames':{'5m':{'state':'wrong-basis'},'30m':{'state':'insufficient'}},'repairs':{'items':[{'state':'recurred'}]}})
        self.assertEqual(len(result['attention']),3)

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class DeviceLockTests(unittest.TestCase):
    def test_inactive_and_busy_devices_do_not_block_sync(self):
        import psycopg,real_trade_journal
        dsn=os.environ['BOB_TEST_DATABASE_URL'];schema='lock_test_'+str(time.time_ns())
        with psycopg.connect(dsn) as c:
            c.execute('CREATE SCHEMA '+schema);c.execute('SET search_path TO '+schema)
            c.execute('CREATE TABLE bob_real_trades(id text,settings jsonb,state jsonb,active boolean,snapshot jsonb)')
            c.execute('CREATE TABLE subscriptions(id int,active_trade boolean,background_config jsonb,trade_enabled boolean)')
            c.execute("INSERT INTO subscriptions VALUES(1,false,'{}',false),(2,false,'{}',true)")
        with psycopg.connect(dsn) as a,psycopg.connect(dsn) as b:
            a.execute('SET search_path TO '+schema);b.execute('SET search_path TO '+schema)
            a.execute('SELECT * FROM subscriptions WHERE id=2 FOR UPDATE')
            b.execute("SET LOCAL lock_timeout='200ms'")
            real_trade_journal.sync_devices(b)
            # Sync also must leave an unrelated disabled device unlocked.
            a.execute('SELECT * FROM subscriptions WHERE id=1 FOR UPDATE NOWAIT')
        with psycopg.connect(dsn) as c:c.execute('DROP SCHEMA '+schema+' CASCADE')
