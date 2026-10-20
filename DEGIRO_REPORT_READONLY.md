# DEGIRO-Berichte in Bob lesen – ohne Konto-API

DEGIRO Schweiz gibt derzeit keine offizielle API für andere Anwendungen frei:
https://www.degiro.ch/helpdesk/de/handelsplattform/bietet-degiro-eine-api

## Implementierung (Mehr → DEGIRO)

- In der DEGIRO-App: Portfolio → Export → CSV, oder Inbox → Transaktionen → Export → CSV.
- In Bob unter **Mehr → DEGIRO** den CSV-Export auswählen. Der Parser läuft nur im Browser.
- Erkennt CSV mit Komma, Semikolon oder Tab, zitierte Felder, UTF-8-BOM, deutsch/englische Spaltenbezeichnungen, ISIN-Prüfziffer und Mengen.
- Zeigt ISIN, Produkt, Stückzahl, Währung, Schlusskurs, Wert und die Zahl übersprungener Zeilen.
- Das Produkt-Tab besitzt eine eigene, getrennte Depotliste mit allen importierten Positionen. Karten werden in Gruppen von 30 geladen, damit auch große Berichte auf dem Handy bedienbar bleiben. Die ISINs werden geprüft; Faktorprodukte sind markiert, unklare Instrumente erhalten keine Freigabe.
- **Ab 20.10.2026:** Ein gültiger Portfolio-CSV-Import speichert **alle erkannten Depotpositionen und Bargeldzeilen** als eine vollständige Momentaufnahme in `localStorage` auf dem aktuellen Gerät. Die Liste wird zusätzlich unter **Produkte → DEGIRO-Depotprodukte (CSV)** angezeigt und nach einem Neustart wiederhergestellt. Sie gelangt **nicht** in Bobs Screenshot-Gold-Hebelproduktliste oder deren Ranking.
- Ein neuer gültiger Portfolio-CSV-Import **ersetzt** alle bisherigen Depotpositionen; eine reine Transaktions-CSV überschreibt keine Depotbestände. Der Button „Eingelesene Daten entfernen“ löscht den lokal gespeicherten Depotstand. Bleibt das Speichern aus (Browser-/Speicherfehler), zeigt Bob dies ausdrücklich.
- Keine Speicherung auf Bobs Server, keine Übertragung ins ChatGPT-Konto und keine Synchronisierung zwischen Geräten. Wer den Browser-Speicher löscht oder das Gerät wechselt, muss die CSV erneut importieren.
- Bewusst keine automatische Positionsübernahme in MyTrade, kein Markt-/Produktfreigabe-Effekt, keine Broker-Abgleichbehauptung.
- Datei: maximal 2 MB und 10.000 Zeilen. Speicherung bis 10.000 eindeutige ISINs; Browser-Speicherlimit kann den Import begrenzen, was angezeigt wird. In der direkten Importansicht werden zunächst die ersten 250 Produkte gezeigt, in der Depotliste alle Produkte bei Bedarf nachladbar.

## Sicherheit und Grenzen

- Keine Broker-Zugangsdaten, Passwörter, TOTP-Seeds oder Cookies.
- Kein Konto-HTTP, keine versteckten APIs, keine Browserautomatisierung, keine Ordermethoden.
- Ein CSV-Bericht ist eine historische Momentaufnahme. Portfolioübersichten bei DEGIRO verwenden Schlusskurse, nicht ausführbare Broker-Livekurse. Die Importzeit ist **keine** Originalkurszeit; das Exportdatum wird nicht erfunden.
- Gehaltene Faktorprodukte, inklusive Gold-Future-Faktorprodukte, bleiben in der Depotliste sichtbar, aber sind ausdrücklich **keine Kandidaten** für Bobs Knock-out-Top-3. Auch andere Depotprodukte werden aus dem CSV heraus nicht automatisch freigegeben.
- Bestandsdaten sind sensible Finanzinformationen. Deshalb werden sie ausschließlich auf dem jeweiligen Gerät gespeichert und können auf Knopfdruck gelöscht werden; es gibt keine automatische Übernahme in MyTrade oder Echtgeldfunktionen.
- Die bestehende **optionale** `degiro_readonly.py`-Anmeldeprobe ist unverändert, verwendet eine inoffizielle SDK und ist **kein** genehmigter/verbindlicher Kontozugriff. Keine automatische Einrichtung oder Hintergrund-Logins.
- Zum direkten Kontosync ist eine von DEGIRO autorisierte Schnittstelle/Einwilligung erforderlich. Alternativen ohne Kontoschnittstelle bleiben explizit manuelle Exporte.
- Spaltenlayout anderer Lokalisierungen kann variieren; unbekannte Formate werden nicht erraten.

## Validierung

`node test_degiro_report_import.js`, `node test_degiro_portfolio_store.js`, `node --check degiro_portfolio_store.js`, `python -m py_compile server.py`, plus `browser_degiro_export_mobile.cjs` mit simuliertem Android-Browser in CI. Die CI führt alle `test_*.js` aus. Ein GitHub-Test ist kein Echtgeld- oder DEGIRO-Kontotest.
