# Bob · Zukunft: Vorbereitung Schritt 1–3 (11.–16. Oktober 2026)

**Modus:** PAPER / Research only. Keine Broker-Anbindung, keine Echtgeldorder,
kein eigenständiges Umschalten produktiver Handelsregeln.

## Schritt 1 · Montag ab 12.10.2026, 08:00 Europe/Zurich

- Vorhanden: vier unabhängige virtuelle Konten **100/100/100/800 EUR**;
  Planung startet am Montag um 08:00 Schweizer Zeit. Bisheriger manueller
  800-EUR-Test bleibt getrennt.
- Vorhanden: Hintergrund-Beobachtung während Bobs Handelszeitfenster, 
  Börsen-/Emittentenhandelbarkeit muss **zusätzlich** nachgewiesen werden.
- Vorhanden: GitHub-Monitoring `bob-market-reopen.yml`,
  `bob-collection-health.yml` und Python-Regression
  `test_monday_paper_live.py`.
- Neu: `zukunft_capture.py` protokolliert je bestätigt ausgewähltem
  XAU/USD-Knock-out-Produkt **höchstens einen 5-Minuten-Zustand** in eigener
  PostgreSQL-Tabelle. Gespeichert werden tatsächlich beobachteter
  EUR-Geld-/Briefkurs, Quellenzeit, Marktrichtung, Marktscore,
  beobachteter Gold-Spot, Historienkerzenzeit und geprüfte KO-Information.
  Nur zulässige ausgewählte Produkte; Futures, indikative oder geschätzte
  Produkte erzeugen keine Freigabe.
- Keine erfundenen Werte: bei fehlender Quelle oder nicht datierter KO-Referenz
  bleibt der Datensatz **nicht freigegeben**; ohne echte Quote wird gar kein
  Beobachtungspunkt gespeichert.
- Aufbewahrung Forschungsproben: 45 Tage, Kontenprotokoll separat.
- Überprüfen: `/health`, `/health/background`, Zukunft-Karte
  `Aktuelle Paper-Konten prüfen` sowie
  `Forschungsdaten und Walk-forward prüfen`.
- Gegenprüfung: gleicher ISIN-/Quellenzeitbezug, keine rückwirkende Füllung,
  kein simuliert ausgeführter Stop bei Datenlücke.
- **Kein Nachweis vor Öffnung:** geplantes Zeitfenster ist kein Beleg, dass
  Server, Emittent und Produktkurse tatsächlich verfügbar sein werden.

## Schritt 2 · Strategievergleich, nachdem Beobachtungen vorhanden sind

- Neu: `zukunft_research.py` prüft einen **einzigen** EUR-Produktkurs-
  Datenstrom mit bestätigter ISIN, Richtung, vollständigem Bid/Ask, 
  Quellenalter, KO-Distanz und 5-Minuten-Zeitfolge.
- Vier klar getrennte Modelle: Bob-Basisschwelle, strengere
  Trendbestätigung, Ausbruch, Rücksetzer. Einstiegssignal entsteht aus der
  **vorherigen abgeschlossenen** Signalbeobachtung; hypothetischer Kauf
  zum erst nachher beobachteten Briefkurs. Ausstieg zum beobachteten Geldkurs,
  Stop vor Ziel und Trailing-Stop nur vorwärts.
- Datenlücke bei offener Position wird als **unbestimmter Ausgang** markiert.
  Keine geschätzten Fills. Nur abgeschlossene auswertbare Paper-Trades zählen.
- Finanzmodell: Einstand, Spread über Bid/Ask, Slippage und Gebühren,
  KO-/Positionslimit, Finanzierung als eigener Kostenparameter.
- Online-Forschung zunächst mit **offen ausgewiesenen, nicht verifizierten**
  Modellkosten: 1 EUR pro Seite, 20 Basispunkte Slippage,
  0 EUR/Tag Finanzierung. Daraus folgt **kein belegter Nettogewinn**.
  Vor einer Freigabe reale produkt- und brokerabhängige Kosten nachtragen.
- Keine Aufwertung eines Produkts aufgrund des Spreads im bestehenden Ranking;
  der Spread wird hier ausschließlich als Ausführungskostenfaktor gerechnet.

## Schritt 3 · Walk-forward / Schattenmodell

- Rollierende **Trainingsfenster 180 Messpunkte**, **fünf Punkte Sperrzone**
  und **60 nachfolgende, sich nicht überschneidende Testpunkte**.
- Schwellenoptimierung nur im Trainingsfenster; Ergebnisse werden erst danach
  in der neuen Testperiode gemessen. Keine zufällige Zeitreihenmischung.
- Zusätzlich ein experimenteller **ML-Schattenfilter** (logistische
  Regression ohne Drittanbieter-ML-Dienst), trainiert ausschließlich mit
  abgeschlossenen Trainingsdaten und mit Purging von Labels, deren Zukunft
  über die Trainingsgrenze reicht. Er darf weder Bob-Regeln ändern noch
  Orders auslösen.
- Start-Forschungsschwelle: mindestens drei vollständige OOS-Fenster
  und 30 bewertbare Abschlüsse je Strategie. Langfristige Strategieaussagen
  benötigen weitere Marktphasen und deutlich mehr Daten.
- Getrennte 30-Handelstage/100-Trades-Schwelle der **vier Paper-Konten**
  bleibt eine erste Beobachtungsschwelle, kein Erfolgsgarant.
- Datenlage oder Testschwellen ungenügend: Anzeige `insufficient` oder
  `blocked`; niemals automatische Live-Handelsfreigabe.

## Ausführung / automatische Sichtbarkeit

Die bestehende Anmeldung genügt. Unter **Zukunft** gibt es den Button
`Forschungsdaten und Walk-forward prüfen`. Er liest über den
**authentifizierten** Endpunkt `/api/audit/read` mit 
`{"mode":"zukunft-research"}` die bisher protokollierten Messpunkte
und startet bei geeigneten Daten den **lesenden** Forschungsvergleich.
Es gibt **keinen** separaten Echtgeld-, Broker- oder API-Orderendpunkt.

Für eine reproduzierbare Offline-Studie mit einem selbst bereitgestellten
JSON-Beobachtungsarchiv: `python zukunft_research.py observed.json report.json`.
Das Importformat lautet `bob-zukunft-observed-v1`; `costs` sind explizit
anzugeben, und jeder Messpunkt trägt datierte EUR Bid/Ask- und Spotpreise.
Keine Aktien-/ETF- oder Fremdwährungspositionen in diesem Modell.

## Stopkriterien

1. Fehlende Emittentenpreise oder nicht bestätigte KO-Bedingungen.
2. Kurslücken, veraltete Daten oder fehlende Zeitstempel.
3. Wiederkehrende Render-Unterbrechungen, Serverstart ohne Kursbestätigung.
4. Zu kurze Zeitreihe, nur künstliche Tests, zu wenige abgeschlossene OOS-Trades.
5. Unbestätigte Finanzierung/Gebühren, zu großer Drawdown oder Regimewechsel.
6. Broker-Anbindung und Echtgeldhandel bleiben für diese Stufe **gesperrt**.

Tests lokal und in CI:
`python -m unittest -v test_zukunft_research.py test_zukunft_capture.py test_monday_paper_live.py`
sowie `node test_future_lab.js`.
Die vorhandene GitHub-CI erkennt `test_*.py` automatisch.
