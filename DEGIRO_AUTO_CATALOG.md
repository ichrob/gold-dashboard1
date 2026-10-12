# Bob · Automatischer Emittenten-Kandidatenimport (12.10.2026)

## Status und ehrliche Abgrenzung

DEGIRO Schweiz stellt **keine offizielle API** für die eigene Plattform / das Konto bereit:
https://www.degiro.ch/helpdesk/de/handelsplattform/bietet-degiro-eine-api

DEGIRO unterstützt keine API-Wrapper oder Kontoskripte und untersagt entsprechende externe Automatisierung:
https://www.degiro.ch/helpdesk/de/handelsplattform/verwendung-der-handelsplattform/kann-ich-mit-degiro-automatisierte-trades-oder

Deshalb gibt es **keinen** belegten kostenlosen und zulässigen Echtzeit-Abruf der vollständigen individuell für ein Schweizer Konto handelbaren DEGIRO-Knock-out-Liste. Ein Börsenlisting oder Emittentenprodukt ist keine DEGIRO-Handelsberechtigung. Es wurden keine DEGIRO-Logins, Session-Cookies, inoffiziellen APIs, bezahlten Anbieter-Verträge oder Broker-Orders eingerichtet.

## Tatsächlich implementiert

- Separates Modul `degiro_catalog.py` mit maximal zwölf historischen, vom Nutzer bereits anhand eines DEGIRO-Listenbilds belegten ISIN-Identitäten; irreversibel beendete Produkte und Faktorprodukte ausgeschlossen.
- Selbständige Nachforschung beim Emittenten über **bereits vorhandene** begrenzte Bob-Adapter, wenn `BOB_AUTO_COLLECTION=1`. Geplante Prüfung werktags ab 08:00 und nochmals ab 18:00 Uhr Schweizer Zeit; Wiederholungsversuche bei Fehlern und Server-Neustarts. Die App braucht dafür nicht geöffnet zu sein, der Render-Prozess muss allerdings laufen. Keine Garantie einer ausfallsicheren Ausführung auf Render Free.
- Exakte ISIN-Prüfziffer, Richtung, EUR-Handelswährung, Status, Gold-Spot-Basis und Faktor/Future-Ausschluss. Fehlende Kurs- oder Zeitdaten bleiben als fehlend markiert. Emittentenseiten ersetzen keinen DEGIRO-Bestand.
- `GET /api/degiro/candidates` ist **authentifiziert**; zeigt nur den abgeschlossenen Forschungsstand, startet selbst keine längere Produktrecherche.
- In der Produktansicht: einklappbares Feld **„Automatische Gold-Produktrecherche · externe Kandidaten“**. Es zeigt den letzten Abruf und die externen Kandidaten getrennt von der eigentlichen Liste `DEGIRO-Liste hochladen`. Keine automatische Übernahme in die aktuelle Screenshot-Liste, keine eigenständige Top-3- oder Trade-Freigabe.
- Keine automatisierte Entdeckung von **neuen** DEGIRO-Listings: die Erfassung neuer ISINs erfordert momentan noch eine echte DEGIRO-Liste per Screenshot oder eine künftig offiziell erlaubte Produktkatalog-Schnittstelle.

## Was als nächstes nötig ist

1. DEGIRO um einen **autorisierten read-only Produktkatalog-Export / Feed für den Schweizer Account** mit ISIN, Suchbarkeit, Produkten, Zeitstand und Nutzungsbedingungen bitten. Kontoauthentifizierung nur über einen offiziell unterstützten Zugang.
2. Alternativ eine rechtlich zulässige kostenlose oder explizit genehmigte Emittenten-/Börsen-Katalogquelle für neue Gold Knock-outs abonnieren; diese Treffer bleiben **externe Kandidaten**. DEGIRO-Verfügbarkeit darf nicht ohne unabhängige Brokerbestätigung als „ja“ markiert werden.
3. Erst nach erfolgreichem originalgetreuem Broker-Abgleich den manuellen Listen-Screenshot ganz ersetzen.

Test: `python -m unittest test_degiro_catalog.py`; reguläre CI führt sämtliche `test_*.py` und `test_*.js` aus.
