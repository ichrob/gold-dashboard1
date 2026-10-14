"""Safe error categories for failed browser decision-audit evidence writes."""
import json
import unittest

import decision_audit


class RejectionCodeTests(unittest.TestCase):
    def test_known_rejections_have_static_categories(self):
        cases = {
            'Prüfprotokoll zu groß oder ungültig': 'payload-invalid-or-large',
            'Ungültige Richtung': 'direction-invalid',
            'Entscheidungs-Kerzenzeit fehlt oder liegt in der Zukunft': 'bar-time-invalid',
            'Zu viele Produkte': 'product-count-invalid',
            'Ungültige Protokollquelle': 'origin-invalid',
            'Screenshot-Quellenzuordnung fehlt': 'screenshot-origin-missing',
            'Ungültiger Screenshot-Listenstand': 'screenshot-generation-invalid',
            'Ungültiger zukünftiger Screenshot-Listenstand': 'screenshot-generation-time-invalid',
            'Produktliste ungültig': 'simulation-products-invalid',
            'Produktnachweise zu groß': 'simulation-evidence-large',
            'Prüfprotokoll muss ein Objekt sein': 'payload-shape-invalid',
            'Ungültige Payload-Größe': 'payload-size-invalid',
        }
        for message, code in cases.items():
            self.assertEqual(decision_audit.rejection_code(ValueError(message)), code)

    def test_unknown_and_json_errors_never_log_untrusted_details(self):
        secret = 'token-fixture-DO-NOT-LOG-123'
        self.assertEqual(
            decision_audit.rejection_code(ValueError(secret)), 'other-validation-error')
        self.assertEqual(
            decision_audit.rejection_code(json.JSONDecodeError(secret, secret, 0)),
            'invalid-json')
        for error in [ValueError(secret), json.JSONDecodeError(secret, secret, 0)]:
            self.assertNotIn(secret, decision_audit.rejection_code(error))


if __name__ == '__main__':
    unittest.main()
