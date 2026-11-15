import unittest
from degiro_screen_replay import replay, demonstration


class ReplayTests(unittest.TestCase):
    def frames(self):
        return [dict(frameId='a', screen='SEARCH', challenge=False,
                     observedAt=100, receivedAt=101, candidates=['SYNTHETIC']),
                dict(frameId='b', screen='DETAIL', challenge=False,
                     observedAt=102, receivedAt=103, isin='SYNTHETIC',
                     currency='EUR', bid=1, ask=1.02)]

    def check_block(self, patch, code):
        frames = self.frames()
        frames[1].update(patch)
        result = replay(frames, 'SYNTHETIC')
        self.assertEqual(result['code'], code)
        self.assertEqual(result['actionsExecuted'], 0)
        self.assertEqual(len(result['journal']), 1)

    def test_normal_and_no_broker_claim(self):
        result = demonstration()
        self.assertEqual(result['code'], 'OBSERVATION_ACCEPTED_OFFLINE')
        for flag in ('brokerConnected', 'liveOrdersEnabled',
                     'isExecutableQuote', 'recognitionVerified'):
            self.assertFalse(result[flag])
        self.assertEqual(result['actionsExecuted'], 0)

    def test_challenge_stops_before_processing(self):
        for challenge in (True, None, 0, 'false'):
            self.check_block(dict(challenge=challenge), 'CHALLENGE_OR_UNKNOWN')

    def test_protected_screens(self):
        for screen in ('LOGIN', 'ORDER', 'CONFIRMATION'):
            self.check_block(dict(screen=screen), 'PROTECTED_SCREEN')

    def test_duplicate_and_no_transition(self):
        self.check_block(dict(frameId='a'), 'REPEATED_FRAME')
        self.check_block(dict(screen='SEARCH'), 'UNEXPECTED_SCREEN')

    def test_wrong_identity(self):
        self.check_block(dict(isin='OTHER'), 'IDENTITY_MISMATCH')
        frames = self.frames()
        frames[0]['candidates'] *= 2
        result = replay(frames, 'SYNTHETIC')
        self.assertEqual(result['code'], 'AMBIGUOUS_IDENTITY')
        self.assertEqual(result['journal'], [])

    def test_known_target_in_multi_product_list(self):
        frames = self.frames()
        frames[0]["candidates"] = ["OTHER", "SYNTHETIC", "THIRD"]
        self.assertEqual(replay(frames, "SYNTHETIC")["code"],
                         "OBSERVATION_ACCEPTED_OFFLINE")

    def test_missing_target_and_malformed_list(self):
        for candidates in (["OTHER"], ["SYNTHETIC", None], "SYNTHETIC"):
            frames = self.frames()
            frames[0]["candidates"] = candidates
            self.assertEqual(replay(frames, "SYNTHETIC")["code"],
                             "AMBIGUOUS_IDENTITY")

    def test_clock_errors(self):
        for patch, code in [({'receivedAt': 133}, 'STALE_OR_FUTURE_FRAME'),
                            ({'receivedAt': 101}, 'STALE_OR_FUTURE_FRAME'),
                            ({'observedAt': 100}, 'NON_MONOTONIC_FRAME'),
                            ({'observedAt': float('nan')}, 'INVALID_TIME')]:
            self.check_block(patch, code)

    def test_bad_quotes_and_currency(self):
        for bid, ask in ((2, 1), (0, 1), (True, 1), (1, float('inf'))):
            self.check_block(dict(bid=bid, ask=ask), 'INVALID_QUOTES')
        self.check_block(dict(currency=''), 'INVALID_CURRENCY')

    def test_bounded_and_incomplete(self):
        for frames in ([], self.frames() * 11):
            with self.assertRaises(ValueError):
                replay(frames, 'SYNTHETIC')
        self.assertEqual(replay(self.frames()[:1], 'SYNTHETIC')['code'], 'INCOMPLETE')

    def test_unexpected_extra_frame_does_not_succeed(self):
        frames = self.frames()
        frames.append(dict(frames[1], frameId='c', observedAt=104, receivedAt=105))
        self.assertEqual(replay(frames, 'SYNTHETIC')['code'], 'UNEXPECTED_SCREEN')


if __name__ == '__main__':
    unittest.main()
