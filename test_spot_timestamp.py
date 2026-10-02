import unittest
from server import dated_spot_row

class SpotTimestampTests(unittest.TestCase):
    def test_observation_time_is_preserved_and_generation_cannot_refresh_it(self):
        row={'price':4200,'price_as_of':'2026-10-02T07:00:00Z','computed_at':'2026-10-02T07:05:00Z','is_stale':False}
        self.assertEqual(dated_spot_row(row,1790924400+30),(4200.,30.,row['price_as_of']))
        with self.assertRaises(ValueError):dated_spot_row(row,1790924400+181)
        for changes in ({'price_as_of':None},{'price_as_of':'2026-10-02T07:00:00'},{'price':True},{'price':float('inf')},{'is_stale':True},{'price_as_of':'2026-10-02T07:00:31Z'}):
            with self.assertRaises(ValueError):dated_spot_row(dict(row,**changes),1790924400+30)

if __name__=='__main__':unittest.main()
