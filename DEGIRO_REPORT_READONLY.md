# DEGIRO-Berichte in Bob lesen – ohne Konto-API

DEGIRO Schweiz gibt derzeit keine offizielle API für andere Anwendungen frei:
https://www.degiro.ch/helpdesk/de/handelsplattform/bietet-degiro-eine-api

## Implementierung (Mehr → DEGIRO)

- In der DEGIRO-App: Portfolio → Export → CSV, oder Inbox → Transaktionen → Export → CSV.
- In Bob unter **Mehr → DEGIRO** den CSV-Export auswählen. Der Parser läuft nur im Browser.
- Erkennt CSV mit Komma, Semikolon oder Tab, zitierte Felder, UTF-8-BOM, deutsch/englische Spaltenbezeichnungen, ISIN-Prüfziffer und Mengen.
- Zeigt ISIN, Produkt, Stückzahl und Währung sowie die Zahl übersprungener Zeilen.
- Wird die Datei entfernt, werden die eingelesenen Daten aus der Ansicht entfernt. Keine Speicherung in Datenbank, localStorage oder Server.
- Bewusst keine automatische Positionsübernahme in MyTrade, kein Markt-/Produktfreigabe-Effekt, keine Broker-Abgleichbehauptung.
- Datei: maximal 2 MB und 10.000 Zeilen; davon werden maximal 1.000 angezeigt.

## Sicherheit und Grenzen

- Keine Broker-Zugangsdaten, Passwörter, TOTP-Seeds oder Cookies.
- Kein Konto-HTTP, keine versteckten APIs, keine Browserautomatisierung, keine Ordermethoden.
- Ein CSV-Bericht ist eine historische Momentaufnahme. Portfolioübersichten bei DEGIRO verwenden Schlusskurse, nicht ausführbare Broker-Livekurse.
- Die bestehende **optionale** `degiro_readonly.py`-Anmeldeprobe ist unverändert, verwendet eine inoffizielle SDK und ist **kein** genehmigter/verbindlicher Kontozugriff. Keine automatische Einrichtung oder Hintergrund-Logins.
- Zum direkten Kontosync ist eine von DEGIRO autorisierte Schnittstelle/Einwilligung erforderlich. Alternativen ohne Kontoschnittstelle bleiben explizit manuelle Exporte.
- Spaltenlayout anderer Lokalisierungen kann variieren; unbekannte Formate werden nicht erraten.

## Validierung

`node test_degiro_report_import.js`, `node --check degiro_report_import.js`, `python -m py_compile server.py`. Die CI führt alle `test_*.js` aus. Ein GitHub-Test ist kein Echtgeld- oder DEGIRO-Kontotest.
