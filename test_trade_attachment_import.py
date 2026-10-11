"""AgentMail PDF retrieval security and original-DEGIRO-layout regression."""
import json
import unittest

import trade_attachment_import as imp
from test_trade_document_import import TEXT

MID = "<example-message@sender.test>"
AID = "att-pdf-123"
INBOX = imp.INBOX
SIGNED_PDF = "https://d111111abcdef8.cloudfront.net/signed/path?Signature=fake"
SIGNED_TEXT = "https://d111111abcdef8.cloudfront.net/signed/plain?Signature=fake"


def event(pdf=True):
    return {
        "type": "event", "event_type": "message.received",
        "message": {
            "inbox_id": INBOX, "message_id": MID,
            "from_": ["robsimon@gmx.de"], "to": [INBOX],
            "subject": "DEGIRO Order ausgeführt", "text": "Anbei Bestätigung",
            "attachments": [{
                "attachment_id": AID, "size": 1001, "filename": "Transaktion.pdf",
                "content_type": "application/pdf"
            }] if pdf else []
        }
    }


class FakeHTTP:
    def __init__(self, **opts):
        self.calls = []
        self.opts = opts
    def __call__(self, url, headers=None, limit=None, timeout=None):
        self.calls.append((url, dict(headers or {})))
        if "api.agentmail.to" in url:
            payload = dict(attachment_id=AID, download_url=self.opts.get("download", SIGNED_PDF))
            if self.opts.get("text", True):
                payload["text_url"] = self.opts.get("text_url", SIGNED_TEXT)
            return json.dumps(payload).encode()
        if "plain" in url:
            return self.opts.get("body", TEXT).encode("utf-8")
        return b"%PDF-1.4\nfake bounded content\n"


class AttachmentImportTests(unittest.TestCase):
    def test_pdf_download_and_stage_only(self):
        mock=FakeHTTP()
        out=imp.enrich_event(event(), {"status":"incomplete"},
                             "robsimon@gmx.de", "local-only-test-api-key", mock)
        self.assertEqual(out["status"], "pending-review")
        self.assertEqual((out["isin"],out["side"],out["quantity"],out["priceEur"]),
                         ("DE000FG5GUX2","BUY",1,5.95))
        self.assertEqual(out["sourceKind"], "AgentMail-DEGIRO-PDF")
        self.assertEqual(out["attachmentCount"], 1)
        self.assertFalse(out["activeTrade"])
        self.assertEqual(len(mock.calls), 3)
        self.assertIn("Bearer ",mock.calls[0][1].get("Authorization",""))
        self.assertNotIn("Authorization",mock.calls[1][1])
        self.assertNotIn("Authorization",mock.calls[2][1])
        self.assertEqual(out["executedAt"],None)

    def test_no_credentials_causes_retry_not_false_success(self):
        with self.assertRaises(imp.FetchError):
            imp.enrich_event(event(),{}, "robsimon@gmx.de", "", FakeHTTP())

    def test_untrusted_sender_and_wrong_inbox_not_fetched(self):
        for mutation in ("from_", "to", "inbox_id", "event_type"):
            e=event()
            e["message"][mutation]=["unknown@example.test"] if mutation in ("from_", "to") else (
                "unknown@agentmail.to" if mutation=="inbox_id" else "message.received.spam")
            if mutation == "event_type":
                e["event_type"]="message.received.spam"
            fake=FakeHTTP()
            out=imp.enrich_event(e,{"status":"incomplete"}, "robsimon@gmx.de",
                                 "local-only-test-api-key",fake)
            self.assertNotEqual(out.get("sourceKind"),"AgentMail-DEGIRO-PDF")
            self.assertEqual(fake.calls,[])

    def test_ssrf_url_and_malformed_pdf_fail_closed(self):
        for url in ("http://169.254.169.254/latest/meta-data",
                    "https://127.0.0.1/file",
                    "https://evil.example/file",
                    "https://d111111abcdef8.cloudfront.net:8443/file",
                    "https://evil.example@localhost/file"):
            with self.subTest(url=url):
                with self.assertRaises(imp.FetchError):
                    imp.fetch_pdf_confirmation(event()["message"],"local-only-test-api-key",
                                               FakeHTTP(download=url))
        with self.assertRaises(imp.FetchError):
            imp.fetch_pdf_confirmation(event()["message"],"local-only-test-api-key",
                                       lambda url,headers,limit,timeout: (
                                           b'{"attachment_id": "different", "download_url": "https://d111111abcdef8.cloudfront.net/a"}'))

    def test_incomplete_pdf_not_represented_as_executed(self):
        mock=FakeHTTP(body="DEGIRO\nBestätigung nur über Auftrag\n")
        out=imp.fetch_pdf_confirmation(event()["message"],"local-only-test-api-key",mock)
        self.assertEqual(out["status"],"incomplete")

    def test_multi_receipt_and_limits(self):
        e=event()
        e["message"]["attachments"]=e["message"]["attachments"]*2
        mock=FakeHTTP()
        out=imp.fetch_pdf_confirmation(e["message"],"local-only-test-api-key",mock)
        self.assertEqual(out["status"],"incomplete")
        e=event()
        e["message"]["attachments"][0]["size"]=imp.MAX_PDF_SIZE+1
        self.assertEqual(imp.fetch_pdf_confirmation(e["message"],
                     "local-only-test-api-key",mock)["status"],"incomplete")

    def test_no_pdf_preserves_original_event(self):
        mock=FakeHTTP()
        e=event(pdf=False)
        out=imp.enrich_event(e,{"status":"ignored","reason":"Keine DEGIRO-Bestätigung"},
                              "robsimon@gmx.de","",mock)
        self.assertEqual(out["status"],"ignored")
        self.assertEqual(mock.calls,[])


if __name__ == "__main__":
    unittest.main()
