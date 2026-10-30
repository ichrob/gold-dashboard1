import copy
import threading
import unittest
from concurrent.futures import Future
from unittest.mock import MagicMock, Mock, patch

import quote_updates as q
import paper_simulation as sim
import comdirect_quotes as cd
import swissquote_quotes as sq


class QuoteUpdateTests(unittest.TestCase):
    def test_only_tracked_products_wake_and_old_list_is_removed(self):
        updates=q.QuoteUpdates()
        updates.track(['a'])
        updates.notify('b')
        self.assertFalse(updates._event.is_set())
        updates.notify('a')
        self.assertTrue(updates._event.is_set())
        updates.clear();updates.track(['b']);updates.notify('a')
        self.assertFalse(updates._event.is_set())

    def test_burst_is_coalesced_and_minimum_cycle_spacing_is_bounded(self):
        updates=q.QuoteUpdates();updates.track(['a','b'])
        with patch.object(q.time,'monotonic',side_effect=[100,100,102,110]),patch.object(q.time,'sleep') as sleep:
            for _ in range(10):updates.notify('a');updates.notify('b')
            self.assertTrue(updates.wait(0));updates.clear()
            updates.notify('a');self.assertTrue(updates.wait(0));updates.clear()
            sleep.assert_called_once_with(8)
        self.assertFalse(updates._event.is_set())

    def test_completed_future_wakes_without_mutating_price_or_starting_work(self):
        updates=q.QuoteUpdates();updates.track(['a'])
        original={'isin':'a','bid':2,'bidAt':'2026-10-30T12:00:00Z'}
        before=copy.deepcopy(original)
        with patch.object(q,'updates',updates):
            for kind in ('cancelled','error','wrong','failed','valid'):
                future=Future()
                if kind=='cancelled':future.cancel()
                elif kind=='error':future.set_exception(ValueError('failure'))
                else:future.set_result(original if kind=='valid' else {'isin':'wrong' if kind=='wrong' else 'a','sourceFailure':True})
                q.completed('a',future)
                self.assertEqual(updates._event.is_set(),kind=='valid')
        self.assertEqual(original,before)

    def test_primary_completion_wakes_worker_before_next_bundle(self):
        future=Future();pool=Mock();pool.submit.return_value=future
        updates=q.QuoteUpdates()
        with patch.object(sim,'_pool',pool),patch.object(sim,'_pending',{}),patch.object(sim,'_quotes',{}),patch.object(sim,'_requested',{}),patch.object(q,'updates',updates),patch('comdirect_fields.apply',side_effect=lambda raw,isin:raw),patch('comdirect_quotes.apply',side_effect=lambda raw,isin:raw),patch('swissquote_quotes.apply',side_effect=lambda raw,isin:raw),patch('leverage_backup.apply',side_effect=lambda raw:raw),patch('hybrid_product_price.apply',side_effect=lambda raw:raw):
            sim.quote_cache([{'isin':'a'}],[],100000)
            self.assertFalse(updates._event.is_set())
            future.set_result({'isin':'a','bidAt':'original'})
            self.assertTrue(updates._event.is_set())
            quotes=sim.quote_cache([{'isin':'a'}],[],101000)
            self.assertEqual(quotes['a']['bidAt'],'original')
            pool.submit.assert_called_once()

    def test_backup_cache_is_published_before_notification(self):
        observation={'state':'observed','isin':'a','bid':2}
        def inspect(isin):
            self.assertEqual(sq._CACHE[isin][1],observation)
            self.assertNotIn(isin,sq._PENDING)
        with patch.object(sq,'_CACHE',{}),patch.object(sq,'_PENDING',{'a'}),patch.object(sq,'fetch',return_value=observation),patch.object(q.updates,'notify',side_effect=inspect) as notify:
            sq._refresh('a');notify.assert_called_once_with('a')
        with patch.object(sq,'_CACHE',{}),patch.object(sq,'_PENDING',{'a'}),patch.object(sq,'fetch',return_value={'state':'unavailable'}),patch.object(q.updates,'notify') as notify:
            sq._refresh('a');notify.assert_not_called()

    def test_comdirect_notifies_new_cache_but_not_retained_failure(self):
        original={'isin':'a','quoteAt':'2026-10-30T12:00:00+00:00','bid':2}
        response=MagicMock();response.__enter__.return_value=response
        response.url=cd.ORIGIN+'inf/zertifikate/a';response.read.return_value=b'fixture'
        def inspect(isin):
            self.assertEqual(cd._CACHE[isin][1]['quote'],original)
            self.assertNotIn(isin,cd._PENDING)
        with patch.object(cd,'_CACHE',{}),patch.object(cd,'_PENDING',{'a'}),patch.object(cd,'open_public_page',return_value=response),patch('comdirect_fields.parse_page',return_value={}),patch.object(cd,'parse_page',return_value=original),patch.object(q.updates,'notify',side_effect=inspect) as notify:
            cd._refresh('a');notify.assert_called_once_with('a')
        with patch.object(cd,'_CACHE',{'a':(1,{'quote':original})}),patch.object(cd,'_PENDING',{'a'}),patch.object(cd,'open_public_page',side_effect=OSError()),patch.object(q.updates,'notify') as notify:
            cd._refresh('a');notify.assert_not_called()
            self.assertEqual(cd._CACHE['a'][1]['quote'],original)


if __name__=='__main__':unittest.main()
