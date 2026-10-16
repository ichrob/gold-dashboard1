"""Signed inbox ingestion / conservative DEGIRO proposal tests."""
import base64
import hashlib
import hmac
import json
import time
import unittest
from unittest.mock import Mock

import trade_email_import as m

EMAIL = """DEGIRO
Transaktion: Kauf
ISIN: DE000PJ9NCK0
Anzahl: 10
Ausführungskurs: 4,25 EUR
Währung: EUR
Ausführungsdatum: 2026-10-12T09:12:03+02:00
Order wurde ausgeführt
"""
SECRET = "whsec_" + base64.b64encode(b"local-test-only-secret-material-1234").decode()


def signed(payload, now=1000000):
    body=json.dumps(payload,separators=(",",":")).encode()
    msg_id="msg-123"
    when=str(now)
    key=base64.b64decode(SECRET[6:])
    digest=base64.b64encode(hmac.new(key, msg_id.encode()+b"."+when.encode()+b"."+body,
                                      hashlib.sha256).digest()).decode()
    headers={"svix-id":msg_id,"svix-timestamp":when,
             "svix-signature":"v1,"+digest}
    return body,headers


def event(body=EMAIL, sender="forwarder@example.test", msgid="mail1"):
    return {"type":"event","event_type":"message.received","event_id":"event-1",
        "message":{"message_id":msgid,"inbox_id":"bob-degiro@agentmail.to","from":sender,
                   "subject":"DEGIRO Ausführung", "text":body}}


class EmailImportTests(unittest.TestCase):
    def test_signature_and_replay(self):
        body,headers=signed(event())
        result,key=m.verify_svix(body,headers,SECRET,now=1000000)
        self.assertEqual(key,"msg-123")
        self.assertEqual(result["message"]["text"],EMAIL)
        with self.assertRaises(ValueError):
            m.verify_svix(body+b" ",headers,SECRET,now=1000000)
        with self.assertRaises(ValueError):
            m.verify_svix(body,headers,SECRET,now=1000301)
        with self.assertRaises(ValueError):
            m.verify_svix(body,headers,"",now=1000000)
        with self.assertRaises(ValueError):
            m.verify_svix(body,{"svix-id":"msg-123"},SECRET,now=1000000)
        altered=dict(headers, **{"svix-signature":"v1,not-a-valid-signature"})
        with self.assertRaises(ValueError):
            m.verify_svix(body,altered,SECRET,now=1000000)

    def test_extract_explicit_buy(self):
        p=m.parse_confirmation("DEGIRO Ausführung",EMAIL)
        self.assertEqual(p["status"],"pending-review")
        self.assertEqual(p["isin"],"DE000PJ9NCK0")
        self.assertEqual((p["side"],p["quantity"],p["priceEur"]),("BUY",10,4.25))
        self.assertEqual(p["executedAt"],"2026-10-12T07:12:03+00:00")
        self.assertNotIn("activeTrade",p)

    def test_sell_and_duplicate_conflicting_terms_fail_closed(self):
        p=m.parse_confirmation("DEGIRO Ausführung",
            EMAIL.replace("Transaktion: Kauf","Transaktion: Verkauf"))
        self.assertEqual(p["side"],"SELL")
        for extra in ["\nISIN: DE000FG5GUT0",
                      "\nAnzahl: 20", "\nTransaktion: Verkauf"]:
            q=m.parse_confirmation("DEGIRO Ausführung",EMAIL+extra)
            self.assertEqual(q["status"],"incomplete")
        for text in [EMAIL.replace("Order wurde ausgeführt","Order pending"),
                     EMAIL.replace("Transaktion: Kauf","Produkt Long"),
                     EMAIL.replace("Ausführungskurs: 4,25 EUR","Kurs: 4,25 EUR"),
                     EMAIL.replace("Anzahl: 10","Anzahl: unklar"),
                     EMAIL.replace("Währung: EUR","Währung: CHF").replace("4,25 EUR","4,25 CHF"),
                     EMAIL.replace("2026-10-12T09:12:03+02:00","2026-10-12 09:12")]:
            q=m.parse_confirmation("DEGIRO Ausführung",text)
            self.assertNotEqual(q["status"],"pending-review")

    def test_signed_message_is_not_broker_authentication(self):
        e=event()
        self.assertEqual(m.import_event(e,"forwarder@example.test")["status"],"pending-review")
        self.assertEqual(m.import_event(e,"other@example.test")["status"],"sender-unconfirmed")
        self.assertEqual(m.import_event(e,"")["status"],"sender-unconfirmed")
        self.assertEqual(m.import_event({**e,"event_type":"message.received.spam"},
                                        "forwarder@example.test")["status"],"ignored")
        self.assertEqual(m.import_event(event("Account notice"),
                                        "forwarder@example.test")["status"],"incomplete")

    def test_original_degiro_sender_is_staged_not_verified(self):
        from test_trade_document_import import TEXT
        e=event(body=TEXT,sender="DEGIRO <notifications@degiro.com>")
        e['message']['subject']='DEGIRO - Transaktionsbestätigung: Kauf'
        e['message']['to']=['original-customer@example.com']
        staged=m.import_event(e,'forwarder@example.test')
        self.assertEqual(staged['status'],'pending-review')
        self.assertEqual(staged['senderKind'],'original-degiro-unverified')
        self.assertEqual(staged['totalChf'],6.04)
        self.assertFalse(staged['activeTrade'])
        e['message']['inbox_id']='other@agentmail.to'
        self.assertEqual(m.import_event(e,'forwarder@example.test')['status'],'ignored')
        e['message']['inbox_id']='bob-degiro@agentmail.to'
        e['message']['subject']='DEGIRO Kontoauszug'
        self.assertEqual(m.import_event(e,'forwarder@example.test')['status'],'sender-unconfirmed')
        e['message']['subject']='DEGIRO - Transaktionsbestätigung: Kauf'
        e['message']['from']='Other <no-reply@example.test>'
        self.assertEqual(m.import_event(e,'forwarder@example.test')['status'],'sender-unconfirmed')

    def test_real_agentmail_sender_array_and_inbox_scope(self):
        actual=event()
        actual['message'].pop('from')
        actual['message']['from_']=['forwarder@example.test']
        actual['message']['to']=['bob-degiro@agentmail.to']
        self.assertEqual(m.import_event(actual,'forwarder@example.test')['status'],'pending-review')
        actual['message']['from_']=['forwarder@example.test','spoof@example.test']
        self.assertEqual(m.import_event(actual,'forwarder@example.test')['status'],'sender-unconfirmed')
        actual['message']['from_']=['forwarder@example.test']
        actual['message']['to']=['other@agentmail.to']
        self.assertEqual(m.import_event(actual,'forwarder@example.test')['status'],'pending-review')
        actual['message']['inbox_id']='other@agentmail.to'
        actual['message']['to']=['bob-degiro@agentmail.to']
        self.assertEqual(m.import_event(actual,'forwarder@example.test')['status'],'ignored')

    def test_redirected_mail_scope_does_not_bypass_sender_or_signature(self):
        e = event()
        e['message']['to'] = ['original-recipient@example.test']
        body, headers = signed(e)
        verified, _ = m.verify_svix(body, headers, SECRET, now=1000000)
        self.assertEqual(m.import_event(verified, 'forwarder@example.test')['status'], 'pending-review')
        self.assertEqual(m.import_event(verified, 'other@example.test')['status'], 'sender-unconfirmed')
        e['message'].pop('inbox_id')
        self.assertEqual(m.import_event(e, 'forwarder@example.test')['status'], 'ignored')
        e['message']['to'] = ['bob-degiro@agentmail.to']
        self.assertEqual(m.import_event(e, 'forwarder@example.test')['status'], 'pending-review')
        e['message'].pop('to')
        self.assertEqual(m.import_event(e, 'forwarder@example.test')['status'], 'ignored')

    def test_database_dedup_never_starts_trade(self):
        conn=Mock()
        conn.execute.return_value.fetchone.side_effect=[("mail1",),None]
        first=m.receive(conn,event(),"signed-1","forwarder@example.test")
        second=m.receive(conn,event(),"signed-1","forwarder@example.test")
        self.assertEqual(first,{"ok":True,"new":True})
        self.assertEqual(second,{"ok":True,"new":False})
        self.assertEqual(conn.execute.call_count,2)
        written=json.loads(conn.execute.call_args_list[0].args[1][1])
        self.assertEqual(written["result"]["status"],"pending-review")
        self.assertNotIn("text",str(written).lower())
        self.assertNotIn("activate",str(written).lower())


class HtmlForwardTests(unittest.TestCase):
    def test_html_only_forward_preserves_confirmation(self):
        rows = [('Order-ID', '11111111-2222-3333-4444-555555555555'),
                ('Ausführungsdatum', '14.10.2026, 10:54:59'),
                ('ISIN', 'DE000PJ9NCK0'), ('Auftrag', 'Kauf'),
                ('Anzahl', '2'), ('Kurs', 'EUR 9.7300')]
        html = '<div>DEGIRO</div><p>Die folgende Order wurde ausgeführt:</p><table>'
        html += ''.join('<tr><td>'+k+'</td><td><strong>'+v+'</strong></td></tr>' for k,v in rows)
        html += '</table><script>Anzahl 999</script><style>ISIN invalid</style>'
        e = event()
        e['message'].pop('text')
        e['message']['html'] = html
        e['message']['extracted_html'] = '<div>Gesendet mit GMX</div>'
        r = m.import_event(e, 'forwarder@example.test')
        self.assertEqual(r['status'], 'pending-review')
        self.assertEqual((r['quantity'], r['priceEur']), (2, 9.73))
        self.assertEqual(r['sourceKind'], 'DEGIRO-execution-email-HTML')
        self.assertFalse(r['activeTrade'])
        self.assertEqual(m.import_event(e, 'other@example.test')['status'], 'sender-unconfirmed')
        e['message']['html'] += '<table><tr><td>Anzahl</td><td>3</td></tr></table>'
        self.assertEqual(m.import_event(e, 'forwarder@example.test')['status'], 'incomplete')

    def test_html_limits(self):
        self.assertEqual(m.confirmation_html_text('x' * (m.MAX_BODY + 1)), '')


if __name__ == "__main__":
    unittest.main()
