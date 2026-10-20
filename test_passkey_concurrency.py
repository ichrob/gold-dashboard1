"""Concurrent dashboard reads never cache a completed authentication decision."""
import threading
import unittest
from concurrent.futures import Future, ThreadPoolExecutor
from unittest.mock import patch
import bob_passkey as passkey

class StatusConcurrencyTests(unittest.TestCase):
    def burst(self, failure=False):
        followers=threading.Barrier(12)
        start=threading.Barrier(12)
        class WaitingFuture(Future):
            def result(self, timeout=None):
                followers.wait(timeout=5)
                return super().result(timeout)
        def upstream(*args, **kwargs):
            followers.wait(timeout=5)
            if failure: raise OSError('unavailable')
            return {'enabled':True,'verified':True}
        headers={'Cookie':'__Host-bob_session=fixture'}
        def call():
            start.wait(timeout=5)
            try:return passkey.rpc('status',headers,'user')
            except OSError:return 'unavailable'
        with patch.object(passkey,'Future',WaitingFuture), patch.object(passkey,'_rpc',side_effect=upstream) as rpc:
            with ThreadPoolExecutor(max_workers=12) as pool:
                results=list(pool.map(lambda _:call(),range(12)))
            self.assertEqual(rpc.call_count,1)
            self.assertEqual(results,(['unavailable'] if failure else [{'enabled':True,'verified':True}])*12)
        self.assertFalse(passkey._status_pending)
        with patch.object(passkey,'_rpc',return_value={'enabled':True,'verified':False}) as rpc:
            self.assertFalse(passkey.rpc('status',headers,'user')['verified'])
            self.assertEqual(rpc.call_count,1,'New calls must check current revocation state')
    def test_overlap_only(self):self.burst()
    def test_failure_denies_every_waiter_and_next_call_rechecks(self):self.burst(True)
    def test_sessions_and_mutations_are_not_shared(self):
        barrier=threading.Barrier(2)
        def upstream(action,headers,user,**fields):
            barrier.wait(timeout=5)
            return {'verified':headers['Cookie'].endswith('a')}
        with patch.object(passkey,'_rpc',side_effect=upstream) as rpc:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda x:passkey.rpc('status',{'Cookie':'__Host-bob_session='+x},'user'),['a','b']))
            self.assertEqual(results,[{'verified':True},{'verified':False}])
            self.assertEqual(rpc.call_count,2)
        with patch.object(passkey,'_rpc',return_value={'ok':True}) as rpc:
            for _ in range(2):passkey.rpc('revoke-credential',{},'user')
            self.assertEqual(rpc.call_count,2)
if __name__=='__main__':unittest.main()
