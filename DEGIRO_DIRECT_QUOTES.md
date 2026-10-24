# Bob – DEGIRO-Kursvergleich / Broker-Ausführung (24.10.2026)

## Tatsächlicher Stand

- Die DEGIRO-Listenbilder belegen **ISIN, Listenpräsenz, OTC-Handelsplatz und Währung** je Produkt.
- Bob liest Emittenten- und Vergleichskurse über SG, BNP, comdirect bzw. Swissquote; sie sind **keine direkt bestätigten DEGIRO-Orderkurse**.
- Der optionale DEGIRO-SDK-Prototyp `degiro_sync` liefert höchstens Portfolio-Bewertungen; er ist **nicht gestartet**, liefert ausdrücklich keine Live-Quotes und ist kein freigegebener Ausführungskanal.
- Die lokale Android-Bildschirmübergabe `degiro_android_bridge.js` kann Geld/Brief und eine sichtbare Anzeigezeit eines ausdrücklich geteilten Bilds **als ungeprüften Entwurf** zeigen. Die Werte beeinflussen weder Top 3 noch den Livehandel.

## Zulässige Integration / klare Stufen

| Stufe | Quelle | Was Bob daraus weiss | Status |
|---|---|---|---|
| A | Aktuelles, vom Nutzer geteiltes DEGIRO-Listenbild | ISIN, Listenplatz, Handelsplatz, Währung | Implementiert |
| B | Bewusst geteilter DEGIRO-Produktbildschirm | Angezeigte Geld-/Briefwerte als ungeprüfte, lokale OCR-Beobachtung | Vergleichsvorschau implementiert; Nutzerbild notwendig |
| C | Autorisierte, vom Broker unterstützte Kurs-API inkl. einzelner Kurszeit und Währung | Verifizierter direkter DEGIRO-Marktpreis | **Nicht verfügbar** |
| D | Ordervorschau mit Stückzahl, Gebühren, Zeitpunkt und Gültigkeit | Konkrete unverbindliche Ordervorschau | **Nicht implementiert** |
| E | Tatsächliche Ausführung / Fill vom Broker | Ausführungspreis der gebuchten Order | **Nicht implementiert**, nie aus Listen/Chartwerten ableiten |

DEGIRO sagt ausdrücklich, dass keine offizielle Konto-API angeboten wird und Drittanbieter-Wrapper / automatisierte Handels-Bots nicht unterstützt werden. Deshalb keine automatisierten Logins, inoffizielles Quote-Scraping, Umgehung von 2FA oder versteckte Android-Bedienung zur Kurs- oder Orderbeschaffung.

Offizielle Quellen:
- https://www.degiro.ch/helpdesk/de/handelsplattform/bietet-degiro-eine-api
- https://www.degiro.ch/helpdesk/de/handelsplattform/verwendung-der-handelsplattform/kann-ich-mit-degiro-automatisierte-trades-oder
- https://www.degiro.ch/datenanbieter-quellen (BNP OTC, SocGen OTC als kostenlose DEGIRO-Kursquellen)

## Nächster sinnvoller Schritt

1. Der Nutzer kann einen *manuell geteilten* DEGIRO-Produktbildschirm für genau eine ISIN in den bereits vorhandenen Android-OCR-Entwurf bringen.
2. Bob zeigt ihn getrennt vom Emittentenreferenzkurs, mit Handelsplatz, Anzeigezeit, OCR-Sicherheitsstatus und Quelle. Ohne datierten Original-Geld-/Brief-Nachweis ist dieser Wert nicht zur automatischen Marktrangfolge zugelassen.
3. Vor einem echten Livefeed muss DEGIRO einen autorisierten Broker-Kanal bereitstellen. Bis dahin bleiben die direkt gebuchten Ausführungskurse **nicht angeschlossen**, unabhängig davon, wie aktuell ein Emittentenangebot aussieht.
4. Kein automatischer Echtgeldhandel; Orders bleiben ausschliesslich manuell beim Broker.

Hinweis: Realtime-Marktkurs, Screenshot-Anzeige, indikatives Geld/Brief, persönlicher RFQ-Preis und tatsächlicher Fill sind unterschiedliche Datenarten. Nicht als austauschbar speichern oder labeln.
