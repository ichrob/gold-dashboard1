import unittest
import youtube_research as y


class McoFibonacciTranscriptTests(unittest.TestCase):
    def test_verified_price_pairs_and_spoken_sources(self):
        rows = [
            {'at': 11, 'text': 'Für Gold schauen wir auf die Fibonacci Retracements.'},
            {'at': 18, 'text': 'Das 61,8 Prozent Level liegt bei 4.200,50 Dollar.'},
            {'at': 24, 'text': 'Und das 38,2 % Retracement liegt bei 4,050.25 USD.'},
        ]
        found = y.extract_fibonacci_levels(rows)
        levels = {(x['key'], x['price']) for x in found}
        self.assertIn(('r618', 4200.50), levels)
        self.assertIn(('r382', 4050.25), levels)
        self.assertTrue(all(x['quote'] and x['at'] >= 0 for x in found))
        self.assertEqual(len(found), len(levels))

    def test_no_inferred_levels_or_unpaired_percent(self):
        rows = [
            {'at': 0, 'text': 'Der Goldpreis liegt bei 4.250 Dollar, wir schauen auf Charts.'},
            {'at': 10, 'text': 'Fibonacci 61,8 Prozent ist ein wichtiger Bereich.'},
            {'at': 40, 'text': 'Im Jahr 2026 wird es spannend und 4200 ist unser Ziel.'},
        ]
        self.assertEqual(y.extract_fibonacci_levels(rows), [])
        self.assertEqual(y.extract_fibonacci_levels([{'at': 2, 'text': 'Fibonacci 61,8 Prozent bei 4200'}])[0]['price'], 4200)

    def test_independent_percent_types_and_no_duplicate_sliding_window(self):
        rows = [
            {'at': 11, 'text': 'Fibonacci: 50 % bei 4.000 USD und 127,2 % bei 4.300 Dollar.'},
            {'at': 12, 'text': 'Goldanalyse geht weiter.'},
        ]
        found = y.extract_fibonacci_levels(rows)
        self.assertEqual({(x['key'], x['price']) for x in found},
                         {('r500', 4000.0), ('e1272', 4300.0)})

    def test_assessment_exposes_only_transcript_evidence(self):
        rows = [{'at': 3, 'text': 'Fibonacci 61,8 Prozent bei 4200 Dollar. ' +
                 'Gold bewegt sich unter und über verschiedene Linien. '*12}]
        result = y.assess(rows, 'de')
        self.assertEqual(result['mcoFibonacci'][0]['key'], 'r618')
        self.assertEqual(result['mcoFibonacci'][0]['price'], 4200)


    def test_spoken_decimal_markers_and_exact_number_words(self):
        examples = [
            ('Fibonacci 61 Komma 8 Prozent bei 4.200 Dollar.', 'r618', 4200),
            ('Das 38 point 2 percent retracement is at 4,050.25 USD.', 'r382', 4050.25),
            ('Fibonacci einundsechzig komma acht Prozent bei 4200 Dollar.', 'r618', 4200),
            ('Fibonacci achtunddreißig komma zwei Prozent bei 4050 Dollar.', 'r382', 4050),
            ('Fib thirty-eight point two percent at 4050 USD.', 'r382', 4050),
            ('Fibo fifty percent at 4100 dollars.', 'r500', 4100),
            ('Fibo 127 Punkt 2 Prozent bei 4300 Dollar.', 'e1272', 4300),
        ]
        for quote, key, price in examples:
            with self.subTest(quote=quote):
                found = y.extract_fibonacci_levels([{'at': 15, 'text': quote}])
                self.assertEqual([(x['key'], x['price']) for x in found], [(key, price)])

    def test_timestamp_is_ratio_subtitle_not_followup_line(self):
        rows = [
            {'at': 10, 'text': 'Fibonacci, das 61 Komma 8 Prozent Level'},
            {'at': 19, 'text': 'liegt bei 4200 Dollar.'},
            {'at': 21, 'text': 'Der Goldpreis bewegt sich weiter.'},
        ]
        found = y.extract_fibonacci_levels(rows)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['at'], 10)

    def test_no_guessing_without_explicit_price_ratio_join_or_anchor(self):
        rows = [
            {'at': 0, 'text': 'Fibonacci 61 Komma 8 Prozent ist interessant. Der Goldpreis liegt bei 4200 Dollar.'},
            {'at': 40, 'text': 'Heute ist der Markt bei 4200 Dollar.'},
        ]
        self.assertEqual(y.extract_fibonacci_levels(rows), [])
        self.assertEqual(y.extract_fibonacci_levels([{'at': 10, 'text': '61 Komma 8 Prozent bei 4200 Dollar.'}]), [])
        self.assertEqual(y.extract_fibonacci_levels([{'at': 10, 'text': 'Fibonacci 62 Komma 8 Prozent bei 4200 Dollar.'}]), [])


if __name__ == '__main__':
    unittest.main()
