# Bob – Automatische Produktnachweis-Prüfung (13.10.2026)

## Umfang

Bob prüft den **aktiven** serverseitig synchronisierten DEGIRO-Listen-Screenshot (nicht eine historische Seed-Liste) während der Handelszeit bei jedem Hintergrundzyklus. Die bestehende Produktanbindung `product_quotes.get_quote` beschafft Daten unter Beibehaltung ihrer Quellengrenzen, Fehlerbehandlung und Backups; die bestehende Paper-Quote-Cache-Aktualisierung läuft getrennt (derzeit höchstens einmal je 60 Sekunden pro ISIN). Die Prüfung selbst benötigt keinen Browser und darf keine zusätzlichen direkten DEGIRO-Verbindungen, Logins oder Orders auslösen.

Das Modul `degiro_product_audit.py` bewertet je Produkt:

- korrekt bestätigte ISIN, Richtung, Spot-Gold statt Futures/Faktor, Status und EUR;
- Emittenten-Geld-/Briefkurs mit **separaten Originalzeiten** und maximal 90 Sekunden Alter;
- Emittentenhebel und **unabhängigen Originalhebelzeitstempel** (kein berechneter Hebel als Ersatz);
- Basispreis, Bezugsverhältnis, KO-Barriere, fixen Vertrag oder belegte Gültigkeit der KO-Barriere mit 8-Stunden-Nachprüfung;
- Laufzeit oder ausdrücklich offene Laufzeit sowie Marktstatus.

Bei jedem fehlenden Nachweis bleibt der Status `incomplete`. Ein neues Abrufdatum oder eine Chartbeobachtung genügt **nie**, um einen Originalzeitstempel nachzutragen. Im Bericht gibt es unabhängig von der Vollständigkeit der Emittentenwerte **keine** DEGIRO-Ausführungs- oder Kontohandelsfreigabe. Die vorhandenen Handelsregeln und Simulationsstopps bleiben unverändert.

## Wiederherstellung und Eskalation

Bereits existierende Emittenten-/Ersatzquellen werden im bestehenden Quote-Cache erneut abgefragt. Nach drei aufeinanderfolgenden Prüfdurchläufen mit gleichbleibender Datenlücke erscheint eine **private KI-Hilfe-Markierung**. Sie wird nach späterem Nachweis automatisch zurückgenommen. Sie ist eine *Datenlücke*, kein selbst reparierter Codefehler.

Private Resultate werden in PostgreSQL in `bob_degiro_product_audit` hinterlegt. Bei einer neuen Screenshot-Generation verhindert die serverseitige Versionserkennung die Anzeige alter Freigabebewertungen. Berichte gelten höchstens 180 Sekunden. `push_server.py GET /product-audit` erfordert den privaten Diensttoken; `server.py GET /api/degiro/audit` erfordert Bobs Anmeldung. In den Rubriken Produkte und Problem gibt es die Werte pro ISIN und die ungelösten Nachweise. Private ISIN-/Produktlisten dürfen nicht in öffentliche GitHub-Issues oder /health-Daten gelangen.

## Grenzen / Prüfung

DEGIRO stellt keine offizielle Konto-API bereit und unterstützt keine Verbindung mit externen Automatisierungsskripten. Der gespeicherte Screenshot bleibt daher die einzige gesicherte Kontoauswahl. Anbieterdaten können recherchiert und datiert werden; die tatsächlich ausführbaren DEGIRO-Kurse und handelbare Produktverfügbarkeit können nicht unabhängig automatisch bestätigt werden.

- `python -m unittest test_degiro_product_audit.py`
- reguläre GitHub-CI für Server, Worker, JS und Datenbank.
- Nach Veröffentlichung in Bob: unter Produkte / Problem einen Bericht mit neuem Listenstand und aktueller Quellenzeit kontrollieren; unter /health nur öffentliche Worker-Gesundheit.

Die Entwicklung setzt keine neue externe Lizenz, kein neues Emittenten-Crawling und keine echten Handelsorders voraus.
