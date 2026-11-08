# Bob: Vier Stufen vom Signal zur geprüften Position

Stand: 8. November 2026. Die ergänzte Prüfung ist ausschließlich lesend und sendet niemals Brokerorders.

## 1. Marktsignal

Bobs bestehende Intraday-Engine liefert LONG/SHORT/ABWARTEN, Zeitstempel und Frische. Der neue Prüfbaustein fordert ein bestätigtes Hauptsignal bis 60 Sekunden alt, frische Marktdaten und belegte Handelszeit. Frühwarnung allein oder Wochenende ohne gültige Kurse ergeben keinen Ordervorschlag.

## 2. Produkt und Risiko

Die vorhandenen Produkt-Rankings, KO-Nachweise und Stop-/Ziel-Pläne bleiben bestehen. trade_execution_readiness.build_review verbindet die Nachweise konservativ: gültige ISIN, Richtung, XAU/USD Spot, einfaches Turbo-Produkt ohne Faktor, DEGIRO-Listing-/Identitätsnachweis, KO-Schwelle, Basispreis, Ratio, Hebel, EUR-Geld-/Brief mit Originalzeit innerhalb 90 Sekunden, Emittentenquelle und nicht geschätzter Kurs. Zusätzlich werden Geld, Einsatzlimit, Tagesverlustgrenze, Positionsanzahl, Gebühren und verifizierte EUR-Produkt-Stop-/Zielwerte verlangt.

Unvollständige, veraltete oder widersprüchliche Daten ergeben BLOCKED. Die Stückzahl berücksichtigt konservativ den gesamten möglichen Knock-out-Verlust samt angenommener Kosten, nicht den Stop als garantierten Ausführungspreis. Spread beeinflusst weiterhin nicht das bestehende Produktranking, ist aber für Order- und Nettokosten relevant.

## 3. Ordervorbereitung / Ausführung

DEGIRO: MANUAL_REVIEW bedeutet ausschließlich ein informatives Arbeitsblatt für eigene manuelle Kontrolle: ISIN, BUY des LONG- oder SHORT-Turbos, ganze Menge, indikatives Limit, Quellzeit, Worst-Case-Einsatz und Stop/Ziel. Es gibt keinen Orderbutton oder Broker-POST; Ausführungskurs, Handelsberechtigung und Order-ID bleiben ausdrücklich unbestätigt.

IBKR/IG: BROKER_API_NOT_CONNECTED. Ein Konto mit offizieller API, nachgewiesenes Instrumentenmapping, verfügbare Broker-Quote, Berechtigungen, idempotente Quittungen und separate, spezifische Live-Freigabe fehlen weiterhin. Der bestehende BrokerAdapter.submit_order bleibt gesperrt.

DEGIRO bietet keine offizielle API und untersagt externe Trading-Bots laut:
https://www.degiro.ch/helpdesk/de/handelsplattform/bietet-degiro-eine-api
https://www.degiro.ch/helpdesk/de/handelsplattform/verwendung-der-handelsplattform/kann-ich-mit-degiro-automatisierte-trades-oder

Die vorhandene SnapTrade-Personal-DEGIRO-Verbindung ist nur lesend. Andere Broker könnten Trading unterstützen, wenn Anbieter, Konto und Produkt es ausdrücklich zulassen; dies ist kein DEGIRO-Handelsnachweis.

## 4. Echtgeldposition beobachten

Die bestehenden real_trade_journal.py, trade_workflow.py und trade_auto_monitor.py erfassen nachweislich bereits ausgeführte Kauf-/Verkaufsbelege und prüfen eindeutige Identität. Ohne echten Beleg keine fingierten Fills, Ausführungskurse oder Positionen. Stop-/Zielhinweise dienen der Überwachung und lösen keine automatische DEGIRO-Order aus.

## Integration

broker_bridge.prepare_order_review liefert den reinen Prüfbaustein, broker_bridge.status enthält fourStageReadiness. Die vorhandene authentifizierte Forschungsansicht zeigt vier Stufen und die weiterhin ausgeschaltete automatische Echtgeld-Ausführung. Keine neuen Hintergrundworker, Secrets oder Datenbankmigrationen.

Tests: python -m unittest test_trade_execution_readiness test_broker_bridge test_real_trade_journal test_trade_auto_monitor

Bestehende Schutzpunkte 2, 3, 5, 6, 7 und die unabhängigen Geräte-/Brokervorgaben bleiben wirksam. Eine grüne CI belegt den Code, nicht die Handelbarkeit oder einen erfolgten Trade.

## Manuelle DEGIRO-Handelsübergabe (8.11.2026)

Für die vom Besitzer gewünschte Reihenfolge **Kauf → Stop nachziehen → Verkauf → Ausführung kontrollieren** gibt es eine lokale, ausdrücklich nicht handelnde Übergabe:

- Bob Handy: **DEGIRO für manuelle Order öffnen** öffnet die installierte DEGIRO-App ausschließlich durch einen Nutzertipp. Es werden keine Kauf-/Verkaufsschaltflächen, Orderdaten oder Bestätigungen automatisch bedient.
- Bob Web → **Mein Trade**: Kaufentwurf aus dem bereits sichtbaren Produktformular anzeigen (als ungeprüft gekennzeichnet); nach einem belegten Kauf ISIN und tatsächliche gehaltene Stückzahl kopieren, den berechneten Produktstopp anzeigen und Hinweise zum manuellen Stopp-Nachziehen sowie vollständigen/teilweisen Verkauf abrufen.
- Die bereits vorhandene E-Mail-/Ausführungsbeleg-Übernahme und der Servermonitor übernehmen ausschließlich **tatsächlich bestätigte** Transaktionen. Ein manueller Auftrag, ein Modellkurs oder ein Klick auf Bob ist kein Nachweis für einen Fill.
- Das Backendmodul **degiro_manual_trade_handoff.py** ergänzt dafür reine Funktionen: `buy_handoff` erfordert eine aktuell noch gültige konservative Ordervorprüfung; `stop_update_handoff` erfordert bestätigten Bestand, belegten existierenden Broker-Stopp sowie aktuellen datierten Produkt-Geldkurs und darf den Stopp nicht lockern; `sell_handoff` erfordert bestätigten Bestand, passende ISIN, ganze Stückzahl und aktuelle belegte EUR-Geldkursquelle. Alle Ausgaben tragen `manualOnly=true`, `orderSubmitted=false` und `executionConfirmed=false`.
- Der bisherige Broker-Vertrag erhält nur die entsprechenden schreibgeschützten Übergabefunktionen und ehrliche Statusfelder; keine Anmeldedaten, Orders oder Änderungen am DEGIRO-Konto.

**Nicht umgesetzt und nicht erlaubt:** automatische Android-Klicks zur tatsächlichen DEGIRO-Kauf-/Verkaufsmaske, zum Setzen/Ändern von Stop-Orders oder zur verbindlichen Orderbestätigung. Laut offizieller DEGIRO-Hilfe verstößt die Verwendung externer Automatisierungstools gegen deren Bedingungen. Ein entsprechender Echtgeldautomat benötigt später einen Broker mit ausdrücklich erlaubter Handels-API und eine eigenständige technisch verifizierte Live-Freigabe.

Prüfung: `python -m unittest test_degiro_manual_trade_handoff test_trade_execution_readiness test_broker_bridge test_real_trade_journal test_trade_auto_monitor` sowie `node test_manual_degiro_handoff.js`, bestehende GitHub-/Android-Tests und Render-Verifikation. Die Prüfung mit synthetischen Daten bestätigt keine handelbaren realen Preise.
