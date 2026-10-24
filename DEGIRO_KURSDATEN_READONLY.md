# DEGIRO-Kursdaten in Bob – lesende Ausbauphase (24.10.2026)

## Stand der bisherigen Ansätze

- **DEGIRO-Liste**: Auf Original-Screenshots gelistete ISINs und Handelsplätze sind verknüpft, aber ohne Bid/Ask-Quellenzeit und ohne verbindliche Broker-Quote.
- **DEGIRO-Produktdetail**: Bobs bestehender Screenshot-Parser `parseDegiroDisplayedQuote` erkennt `Kursdaten`, Symbol/ISIN, Handelsplatz, Geld, Brief, Währung und angezeigte Zeit, sofern auf einer Nutzeraufnahme eindeutig. Die Anzeigezeit ist nicht unbedingt die originale Bid-/Ask-Zeit.
- **Android**: `degiro_android_bridge.js` übernimmt user-initiiertes OCR von 1–4 Bildern, kennzeichnet die Angaben als ungeprüft und setzt keine Ausführungsfreigabe.
- **SnapTrade**: Read-only-Depot-/Positions-/Ordersynchronisation, kein Nachweis für aktuelle DEGIRO-Gold-Knock-out-Bid-/Ask-Quotes; etwaige Quoten des SnapTrade-Kurs-Endpunkts sind nicht als Broker-Ausführung zu behandeln.
- **Optionaler DEGIRO-SDK-Lesetest**: nicht offiziell unterstützt und aktuell keine bestätigte Verbindung. Keine Hintergrundabfrage der DEGIRO-Webseite.

## Implementiert

Das ausklappbare Panel **DEGIRO-Kursdaten · Leseprüfung** ist direkt beim Produktlistenimport.
Es liest den vorhandenen lokalen Produktdatensatz und die bereits vorhandenen, bewusst hochgeladenen Produktdetailbilder; pro ISIN zeigt es eine datierte DEGIRO-Geld-/Briefanzeige oder den konkreten fehlenden Nachweis. Ein Button je ISIN verwendet exakt den bereits existierenden Bildimport und dessen OCR, Serienlogik und lokal gespeicherte Originalbilder. Die Ansicht prüft selbstständig alle vorhandenen Bilder bei jeder Aktualisierung des Produktbereichs, **nicht** das DEGIRO-Konto.

Der Status unterscheidet `missing`, `invalid-time`, `display-recent` (angezeigte Zeit höchstens 90 Sekunden alt) und `historical`. Selbst bei `display-recent` bleiben:
- `brokerConnected=false`
- `executionConfirmed=false`
- `isExecutableQuote=false`
- `tradeApproved=false`.

Ausschlüsse: fremde ISIN, gekreuztes Bid/Ask, falsche Währung, fehlender Zeitbeleg, uneindeutige Quelle, gefälschte Ausführungsfelder. Die Darstellung nutzt keine SG-/comdirect-/Swissquote-Kurse als scheinbare DEGIRO-Kurse. Alte Kursbilder erhalten keine neue Kurszeit.

## Verbleibende Grenzen und nächster erlaubter Ausbau

DEGIRO veröffentlicht keine offizielle Konto-API und unterstützt keine externen Browser- oder API-Automatisierungstools für sein Konto. Deshalb werden keine versteckten Logins, 30-Sekunden-Pollings, simulierten Klicks oder verbindlichen RFQ-Aufrufe implementiert.

Eine **verbindliche Orderquote** lässt sich ausschließlich aus einem künftig autorisierten, offiziell unterstützten Broker-Kanal oder einer ausdrücklich bestätigten konkreten Order-/Ausführungsbestätigung belegen. Der derzeitige Nutzer-Screenshot beweist nur eine Bildschirm-Anzeige. Ein historischer SnapTrade-Fill ist kein aktuell kaufbarer Preis; selbst Zeit/ISIN/Preis/Stückzahl einer ausgeführten Order gelten nur für diese Ausführung.

Am nächsten Handelstag: Ein DEGIRO-Produktdetailbild mit sichtbarer ISIN, Geld/Brief, Handelsplatz und Kurszeit im DEGIRO-Kursdaten-Panel einmal bewusst importieren. Bob aktualisiert dann selbstständig die zugehörige Produktbeobachtung und zeichnet ihre Alterung korrekt auf. Keine Echtgeldorder, keine automatische Handelsfreigabe.
