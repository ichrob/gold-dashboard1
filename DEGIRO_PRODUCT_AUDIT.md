# Bob – Automatische Produktnachweis-Prüfung (13.10.2026)

## Umfang

Bob prüft den **aktiven** serverseitig synchronisierten DEGIRO-Listen-Screenshot (nicht eine historische Seed-Liste) während der Handelszeit bei jedem Hintergrundzyklus. Die bestehende Produktanbindung `product_quotes.get_quote` beschafft Daten unter Beibehaltung ihrer Quellengrenzen, Fehlerbehandlung und Backups; die bestehende Paper-Quote-Cache-Aktualisierung läuft getrennt (derzeit höchstens einmal je 60 Sekunden pro ISIN). Die Prüfung selbst benötigt keinen Browser und darf keine zusätzlichen direkten DEGIRO-Verbindungen, Logins oder Orders auslösen.

Das Modul `degiro_product_audit.py` bewertet je Produkt:

- korrekt bestätigte ISIN, Richtung, Spot-Gold statt Futures/Faktor, Status und EUR;
- Emittenten-Geld-/Briefkurs mit **separaten Originalzeiten** und maximal 90 Sekunden Alter;
- Emittentenhebel mit **eigenem Originalzeitstempel oder eindeutig zugeordnetem gemeinsamen SG-Beobachtungszeitbezug** (gemeinsame Beobachtung wird als solche gekennzeichnet, nicht als separate Original-Hebelzeit; kein berechneter Hebel als Ersatz);
- Basispreis, Bezugsverhältnis, KO-Barriere, fixen Vertrag oder belegte Gültigkeit der KO-Barriere mit 8-Stunden-Nachprüfung;
- Laufzeit oder ausdrücklich offene Laufzeit sowie Marktstatus.

Bei jedem fehlenden Nachweis bleibt der Status `incomplete`. Ein neues Abrufdatum oder eine Chartbeobachtung genügt **nie**, um einen Originalzeitstempel nachzutragen. Im Bericht gibt es unabhängig von der Vollständigkeit der Emittentenwerte **keine** DEGIRO-Ausführungs- oder Kontohandelsfreigabe. Die vorhandenen Handelsregeln und Simulationsstopps bleiben unverändert.

## Handelsplatz / ausführbarer Kurs – neue Prüfung (13.10.2026)

Die SG-Wertpapier-ISIN `DE000FG8NHQ3` ist als **CHF-Knock-out-Warrant am Handelsplatz Swiss DOTS** dokumentiert:
- Produktidentität und Handelsplatz: https://www.finanzen.ch/derivate/de000fg8nhq3
- Swissquote beschreibt Swiss DOTS als exklusiven OTC-Handelsweg: https://www.swissquote.com/de-ch/private/trade/products/swiss-dots
- SG Schweiz beschreibt den Zugriff über Swissquote und PostFinance, nicht DEGIRO: https://www.sg-zertifikate.ch/SiteContent/11/1/2/652/75/SwissDOTS_QuickGuide_A4_DE_Web.pdf

Bob übernimmt deshalb den **vom bestätigten SG-Produkt gelesenen ExchangeCode** separat. Wenn für die exakt bestätigte ISIN `DE000FG8NHQ3` die SG-Quelle `CBSW/CHF` liefert, erscheint ein eigener **Handelsplatzkonflikt**. Die CHF-Chartdaten bleiben nur als Forschung sichtbar; selbst ein scheinbar frisches Geld-/Briefpaar wird **nie** in eine ausführbare DEGIRO-Quotierung umgedeutet. Ein Handelsplatzkonflikt wird nicht als reparierbare Hebelzeit- oder Kurszeitlücke an öffentliche KI-Hilfe gemeldet.

Für `DE000FG7N6Z2` bestätigt die deutsche SG-Produktseite einen EUR-Classic-Turbo auf Gold mit Ablauf am 16.10.2026: https://www.sg-zertifikate.de/product-details/fg7n6z . Das zugehörige onvista-Snapshot kann getrennte Echtzeit-Quellen von SG, Frankfurt und Stuttgart mit Geld/Brief, Uhrzeit und Stückzahl **anzeigen**: https://www.onvista.de/derivate/Knock-Outs/341942224-FG7N6Z-DE000FG7N6Z2 . Diese öffentlich sichtbaren Quote-Indikationen ersetzen weder einen unabhängigen **Emittentenhebel-Zeitstempel** noch den tatsächlichen Preis einer DEGIRO-Ausführung. Die bestehende programmatische Onvista-Sperre bleibt erhalten, solange kein zulässiger automatisierter Anbieterzugang bestätigt wurde.

**Zur tatsächlichen Ausführung:** DEGIRO bietet derzeit keine offizielle Konto-API: https://www.degiro.ch/helpdesk/de/handelsplattform/bietet-degiro-eine-api . Ein tatsächliches verbindliches RFQ ist grundsätzlich broker-/auftrags-/volumen- und zeitabhängig und kann ohne autorisierte Broker-Verbindung nicht autonom für das DEGIRO-Konto bestätigt werden. Kursanzeige, Emittentenquote, Börsenorderbuch und individuelle DEGIRO-Ausführbarkeit bleiben separate Nachweise. Bob erstellt keine Orders und entsperrt keine Echtgeldhandelsfreigabe. Bei erlaubter manueller DEGIRO-Quotierung ist ein aktueller, datierter Originalbeleg erforderlich, bevor eine konkrete Ausführungsentscheidung bewertet werden kann.

## Wiederherstellung und Eskalation

Bereits existierende Emittenten-/Ersatzquellen werden im bestehenden Quote-Cache erneut abgefragt. Nach drei aufeinanderfolgenden Prüfdurchläufen mit gleichbleibender Datenlücke erscheint eine **private KI-Hilfe-Markierung**. Sie wird nach späterem Nachweis automatisch zurückgenommen. Sie ist eine *Datenlücke*, kein selbst reparierter Codefehler.

Private Resultate werden in PostgreSQL in `bob_degiro_product_audit` hinterlegt. Bei einer neuen Screenshot-Generation verhindert die serverseitige Versionserkennung die Anzeige alter Freigabebewertungen. Berichte gelten höchstens 180 Sekunden. `push_server.py GET /product-audit` erfordert den privaten Diensttoken; `server.py GET /api/degiro/audit` erfordert Bobs Anmeldung. In den Rubriken Produkte und Problem gibt es die Werte pro ISIN und die ungelösten Nachweise. Private ISIN-/Produktlisten dürfen nicht in öffentliche GitHub-Issues oder /health-Daten gelangen.

## Grenzen / Prüfung

DEGIRO stellt keine offizielle Konto-API bereit und unterstützt keine Verbindung mit externen Automatisierungsskripten. Der gespeicherte Screenshot bleibt daher die einzige gesicherte Kontoauswahl. Anbieterdaten können recherchiert und datiert werden; die tatsächlich ausführbaren DEGIRO-Kurse und handelbare Produktverfügbarkeit können nicht unabhängig automatisch bestätigt werden.

- `python -m unittest test_degiro_product_audit.py`
- reguläre GitHub-CI für Server, Worker, JS und Datenbank.
- Nach Veröffentlichung in Bob: unter Produkte / Problem einen Bericht mit neuem Listenstand und aktueller Quellenzeit kontrollieren; unter /health nur öffentliche Worker-Gesundheit.

Die Entwicklung setzt keine neue externe Lizenz, kein neues Emittenten-Crawling und keine echten Handelsorders voraus.
