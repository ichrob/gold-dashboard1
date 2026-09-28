import unittest


def rank_fixture(items, direction, min_ko=3, max_lev=12, trade_score=85, max_loss=5):
    valid=[]
    for x in items:
        if x["direction"]!=direction or x["ko_pct"]<min_ko or x["lev"]>max_lev or x["spread"]>2:
            continue
        product=30
        product += min(25,25 if x["ko_pct"]>=10 else 20 if x["ko_pct"]>=6 else x["ko_pct"]*3.2)
        product += min(15,max(0,x["ko_buffer"]*3))
        product += max(0,min(15,15 if x["lev"]<=8 else 15-(x["lev"]-8)*1.5))
        product += 10 if x["spread"]<=.5 else 7 if x["spread"]<=1 else 3
        score=round(trade_score*.55+product*.45)
        valid.append((score,x["name"]))
    return sorted(valid,reverse=True)


class ProductSelectorTests(unittest.TestCase):
    def test_larger_ko_buffer_beats_higher_leverage(self):
        products=[
            {"name":"A 15x tight KO","direction":"LONG","lev":15,"ko_pct":3.2,"ko_buffer":0.6,"spread":1.2},
            {"name":"B 9x safer KO","direction":"LONG","lev":9,"ko_pct":7.4,"ko_buffer":3.0,"spread":0.5},
        ]
        ranked=rank_fixture(products,"LONG")
        self.assertEqual(ranked[0][1],"B 9x safer KO")

    def test_wrong_direction_is_excluded(self):
        products=[{"name":"Wrong","direction":"SHORT","lev":5,"ko_pct":12,"ko_buffer":5,"spread":.3}]
        self.assertEqual(rank_fixture(products,"LONG"),[])

    def test_spread_over_two_percent_is_excluded(self):
        products=[{"name":"Wide","direction":"LONG","lev":5,"ko_pct":10,"ko_buffer":5,"spread":2.1}]
        self.assertEqual(rank_fixture(products,"LONG"),[])

    def test_leverage_above_max_is_excluded(self):
        products=[{"name":"Too high","direction":"LONG","lev":13,"ko_pct":12,"ko_buffer":8,"spread":.2}]
        self.assertEqual(rank_fixture(products,"LONG",max_lev=12),[])

    def test_short_products_are_ranked_in_short_direction(self):
        products=[
            {"name":"Short A","direction":"SHORT","lev":6,"ko_pct":11,"ko_buffer":6,"spread":.4},
            {"name":"Long A","direction":"LONG","lev":6,"ko_pct":11,"ko_buffer":6,"spread":.4},
        ]
        ranked=rank_fixture(products,"SHORT")
        self.assertEqual(ranked[0][1],"Short A")


if __name__ == "__main__":
    unittest.main()
