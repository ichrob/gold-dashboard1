import unittest
from browserless_sg_markdown import extract_public_fields

class SGMarkdownTests(unittest.TestCase):
    def test_public_sg_fixture(self):
        markdown="""# BEST Turbo-Optionsschein Open-End | Put | auf Gold | 4.151,2285 USD
## FB0A49
## Stammdaten
ISIN
DE000FB0A490
WKN
FB0A49
Produktart
BEST Turbo-Optionsscheine
Basiswert info_outlined
Gold
Bezugsverhältnis info_outlined
10:1
Typ
Put
Basispreis info_outlined
4.151,2285 USD
Knock-Out-Barriere info_outlined
4.151,2285 USD
( 06.11.2026 )
"""
        got=extract_public_fields(markdown)
        self.assertEqual(got['direction'],'SHORT')
        self.assertEqual(got['knockOut'],'4.151,2285 USD')
        self.assertEqual(got['underlying'],'Gold')
        self.assertEqual(got['ratio'],'10:1')
        self.assertNotIn('quoteTime',got)
        self.assertNotIn('ask',got)
        self.assertNotIn('bid',got)

    def test_unrelated_home_page_fails_closed(self):
        self.assertEqual(extract_public_fields('# Produkte\\nGold Suche'),{})
        self.assertEqual(extract_public_fields(''),{})
        self.assertEqual(extract_public_fields(None),{})

    def test_forged_value_or_heading_not_accepted(self):
        md='## Stammdaten\\nTyp\\nVielleicht Put\\nKnock-Out-Barriere\\nunbekannt'
        self.assertEqual(extract_public_fields(md),{})

    def test_page_with_generic_markers_far_from_labels_does_not_extract(self):
        md='## Stammdaten\\n'+'bla\\n'*170+'Typ\\nPut\\nKnock-Out-Barriere\\n4.151,2285 USD'
        self.assertEqual(extract_public_fields(md),{})

if __name__=='__main__':
    unittest.main()
