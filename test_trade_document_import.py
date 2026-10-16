"""Regression for DEGIRO execution PDF layout (synthetic, no real account data)."""
import unittest
import trade_document_import as m

TEXT = """DEGIRO
Datum der Benachrichtigung: 02.10.2026, 19:46
Die folgende Order wurde ausgeführt:
Synthetic SG Gold BEST
Order-ID
11111111-2222-4333-8444-555555555555
Ausführungsdatum
02.10.2026, 19:46:08
ISIN
DE000FG5GUX2
Auftrag
Kauf
Ordertyp
Limit
Anzahl
1
Kurs
EUR 5.9500
Wert in Lokalwährung
EUR -5.95
Wert
CHF -5.55
Gesamte Kosten
CHF -0.48
Gesamt
CHF -6.04
www.degiro.ch
clients@degiro.ch
"""


class PdfReceiptTests(unittest.TestCase):
    def test_pdf_two_column_text_and_no_execution(self):
        p=m.parse_document_text(TEXT)
        self.assertEqual(p["status"],"pending-review")
        self.assertEqual((p["isin"],p["side"],p["quantity"],p["priceEur"]),
                         ("DE000FG5GUX2","BUY",1,5.95))
        self.assertEqual(p["executedLocal"],"02.10.2026 19:46:08")
        self.assertFalse(p["timezoneConfirmed"])
        self.assertIsNone(p["executedAt"])
        self.assertEqual(p["costsChf"],0.48)
        self.assertFalse(p["activeTrade"])
        self.assertEqual(len(p["orderIdDigest"]),64)
        self.assertNotIn("clients@degiro.ch",str(p))
        self.assertNotIn("11111111",str(p))

    def test_single_line_cells_are_accepted_too(self):
        s=(TEXT.replace("Auftrag\nKauf","Auftrag Kauf")
               .replace("Kurs\nEUR 5.9500","Kurs EUR 5.9500")
               .replace("Anzahl\n1","Anzahl: 1"))
        self.assertEqual(m.parse_document_text(s)["status"],"pending-review")

    def test_unclear_or_non_execution_is_not_promoted(self):
        for s in [
            TEXT.replace("Die folgende Order wurde ausgeführt:", "Order wurde angenommen:"),
            TEXT.replace("Auftrag\nKauf","Auftrag\nLong"),
            TEXT.replace("Kurs\nEUR 5.9500","Kurs\nCHF 5.9500"),
            TEXT.replace("ISIN\nDE000FG5GUX2","ISIN\nDE000FG5GUX3"),
            TEXT.replace("Ausführungsdatum\n02.10.2026, 19:46:08",
                         "Ausführungsdatum\n02.10.2026, 19:46"),
            TEXT+"\nKurs\nEUR 3.0000",
            TEXT+"\nAuftrag\nVerkauf",
            TEXT.replace("Order-ID\n11111111-2222-4333-8444-555555555555","Order-ID\nunbekannt"),
        ]:
            with self.subTest(s=s[-80:]):
                self.assertNotEqual(m.parse_document_text(s)["status"],"pending-review")

    def test_signed_chf_totals_from_full_receipt(self):
        buy=m.parse_document_text(TEXT)
        self.assertEqual(buy['grossChf'],5.55)
        self.assertEqual(buy['totalChf'],6.04)
        self.assertEqual(buy['costsChf'],0.48)
        sale=(TEXT.replace("Auftrag\nKauf","Auftrag\nVerkauf")
                  .replace("EUR -5.95","EUR 5.95")
                  .replace("CHF -5.55","CHF 5.55")
                  .replace("CHF -6.04","CHF 5.07"))
        result=m.parse_document_text(sale)
        self.assertEqual(result['status'],'pending-review')
        self.assertEqual(result['totalChf'],5.07)
        tampered=sale.replace("CHF 5.07","CHF 8.99")
        self.assertEqual(m.parse_document_text(tampered)['status'],'incomplete')

    def test_sell(self):
        sold=(TEXT.replace("Auftrag\nKauf","Auftrag\nVerkauf")
              .replace("EUR -5.95","EUR 5.95")
              .replace("CHF -5.55","CHF 5.55")
              .replace("CHF -6.04","CHF 5.07"))
        p=m.parse_document_text(sold)
        self.assertEqual(p["side"],"SELL")


if __name__ == "__main__":
    unittest.main()
