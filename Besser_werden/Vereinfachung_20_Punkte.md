# Bob vereinfachen und automatisieren – 20-Punkte-Iststand

**Stand:** 22. Oktober 2026 · **Ziel:** einfache Samsung-Bedienung, weitgehend automatische Analyse, Produkt- und Problempflege, dauerhaft getestete Paper-Simulation. **Keine Echtgeldorders.**

**Was diese Liste bedeutet:** `Live` heißt nur, dass Code im produktiven GitHub-/Render-Stand nachweisbar ist – nicht, dass jede Funktion auf dem konkreten Samsung-Telefon bereits erfolgreich bedient wurde. `Teilweise` heißt tatsächlich programmierte Bausteine, aber noch offene Akzeptanzkriterien. `Offen` wird nicht als erledigt gezählt.

## Nachprüfbarer Stand je Ziel

| Nr. | Ziel | Nachgewiesener Teilstand | Was fehlt, damit der Punkt wirklich fertig ist |
| --- | --- | --- | --- |
| 1 | Zentrale Startseite | **Teilweise / live:** `bob_unified_workspace.js` bündelt Prüfung, Signal, Navigation und Produktwahl; Samsung-Screenshot bestätigt Ansicht | **Blocker:** alle Gold-ISINs und Zustände direkt auf Samsung sichtbar. PR #758: Startbanner, Einzel-ISIN-Liste, Audit-Fallback. Neues CI und neues Render-Deployment erforderlich |
| 2 | Alles mit einem Klick vorbereiten | **Teilweise / live:** expliziter Knopf nutzt bestehendes `loadData(true)`, begrenzten Emittentenabruf und Original-Spotzeit | Geschlossene/mangelhafte Quellen, Quoten, Wiederholungsstrategie, tatsächliche 30-s-Gültigkeit am Handy nachweisen |
| 3 | Einheitliche Produktkarte | **Teilweise / live:** `product_evidence_contract.js`, gemeinsame Quellenlabels, Geld/Brief, Richtung, KO/Hebel soweit original belegt | Vertrag, Laufzeit, Emittent, Börsen-/DEGIRO-Ausführungsnachweis und Produktfeldstatus über alle Anzeigen vereinheitlichen |
| 4 | Einheitliche Haken/Kreuze | **Teilweise:** getrennte Statusanzeigen und zentrale Diagnoseschilder vorhanden | Pro ISIN in jeder Produktansicht dieselben Haken/Kreuz/Ursachencodes, Gesamthaken nur bei allen Freigaben; Android-Regression |
| 5 | Menüs und Wege vereinfachen | **Teilweise / live:** direkter Weg zu Produkten, Mein Trade, Simulation, Problemen, Orderentwurf | Doppelansichten systematisch entfernen, Scrollen und Navigation auf echtem Samsung validieren |
| 6 | Screenshot-Import automatisieren | **Teilweise:** Android Companion Share/OCR und Serien-Kontext existieren | Echte Samsung-Freigabe, Serien-ISIN-Zuordnung, Dubletten/0-O-9, fehlerhafte Quellnachweise in sämtlichen Varianten prüfen |
| 7 | DEGIRO-Liste speichern und vergleichen | **Teilweise:** lokale Archivierung, persistierte ISINs und Generations-Differenz ohne Delisting-Behauptung | Belastbarer mehrgeräte-/serverseitiger vollständiger Generationenvergleich, ohne alte Screenshots als frische Handelbarkeit zu behandeln |
| 8 | Einheitlicher Kurs/Originalzeitpunkt | **Teilweise:** gemeinsame Spotquelle für Analyse, konservative Originalzeiten, Quellenfrischegates | Source-Drift und Randfall #677 (60s) belastbar schließen; alle UI-/Push-/Worker-Werte derselben Messgeneration zuordnen |
| 9 | Automatische Datenquellen und Ersatzwege | **Teilweise:** komdirect/Emittent/Swissquote sowie Quellreparatur und Backoff vorhanden | Per Feld verbindliche Quellenpriorität, Konflikte, Beleg-/Hebelzeit, kostenloses Quotenbudget, vollständige Failure-Tests |
| 10 | SnapTrade und CSV zusammenfassen | **Teilweise:** reine Lese-/CSV-Strecken und ISIN-Abgleich vorhanden | Depotänderungen/Fills/FX und Exportstände mit Identitäts-/Konfliktregeln konsistent gegenüberstellen |
| 11 | Sichere Orderentwürfe | **Teilweise / live:** ISIN-Handoff in manuelle Entwurfsmaske, keine automatische Brokerorder | Mobiler End-to-end-Test für DEGIRO-Ausführungskurs, Handelsplatz, Stückzahl, Ziel/Stopp und Benutzerbestätigung |
| 12 | Echte Trades und Verkäufe auswerten | **Teilweise:** `Mein Trade`, Trade-/Journal-Verarbeitung existieren | Broker-Fill, Teilverkauf, Gebühren/Steuern/FX, Netto-P/L und Identitätskonflikte nachprüfbar zusammenführen |
| 13 | Ein einziges Simulations-Cockpit | **Teilweise:** Paper-Simulator, fünf Profilkonten, Lernen/Diagramme vorhanden | Alle fünf Konten, originaldatierte Trades, Kosten, Pausen und P/L in einem gemeinsamen klaren Live-Cockpit |
| 14 | Varianten automatisch vergleichen und lernen | **Teilweise:** getrennte Paper- und Lern-/Vorwärtstests | Harte Out-of-sample-/Walk-forward-Metriken, realistische Kosten/KO und unabhängige Validierung vor jeder Strategieänderung |
| 15 | MCO/NCO-Goldvideos verarbeiten | **Teilweise:** Kanal-/Untertitel-/Bildhilfen, recherchierte Quellen und Browsertests existieren | Gesicherte datierte Transkripte, originale Frames und MCO-vs.-Bob-Vergleich ohne erfundene Zeit-/Preisdaten |
| 16 | Problemzentrale und Selbstreparatur | **Teilweise:** Problemzähler, unabhängiger Watchdog, begrenzte Worker-Neustarts, GitHub-Eskalation | Einheitlicher privater/öffentlicher Diagnosestatus, vollständige KI-Hilfefälle, sichere automatische Reparatur-Nachweise |
| 17 | Hintergrundprogramme vereinfachen | **Teilweise / live:** nur fehlende CFD-/Spot-/Vergleichs-Worker starten, begrenzte Quote-Runtime; **neuer PR:** drei UI-Ansichten teilen einen authentifizierten Produktbericht in-flight/3-s-Cache, keine neuen Trading-Loops | Neue Bericht-Deduplikation nach PR-CI und Render-Deploy prüfen; weitere serverseitige Abruf-Deduplikation, 30-s-Taktkontrolle, Quoten-/DB-Last, Ausfall-/Restart-Tests |
| 18 | CI-geschützte Veröffentlichungen | **In Betrieb:** beide Render-Dienste per Connector als `checksPass` bestätigt; `Bob release gate` wartet auf `Validate Bob`; produktive Deployments wurden gemessen | Offene PR-CI-/Browser-Installations-Probleme schließen; GitHub-Branch-Schutz und alle Release-Checknamen explizit erzwingen, manuellen Override getrennt absichern |
| 19 | Große Dateien schrittweise zerlegen | **Teilweise:** `product_evidence_contract.js`, `bob_unified_workspace.js` und weitere eigenständige Module getestet | Riesige `degiro_assistant.js`/`Bob.html` nur nach Golden-Master-Test in kleine Bausteine zerlegen; keine Big-Bang-Migration |
| 20 | Sicherung und Wiederherstellung | **Teilweise / live:** freiwilliger lokaler Export/Import *heutiger Orderentwürfe*, ISIN-Prüfziffer, keine automatische Überschreibung | Originalbilder, vollständige Produktlisten, Forschung und Paper-Historie datenschutzgerecht sichern, Rückspieltests und Gerätewechsel gewährleisten |

## Tatsächlich kontrolliert

- **Render:** `bob-private-scanner` und `bob-push-service` stehen auf `autoDeployTrigger=checksPass`; zuletzt live geprüfter Commit separat über Render nachweisen.
- **Bob-Diagnose (22.10.2026, 17:22 UTC):** Produktprüfung `ok`, 10 Produktidentitäten, 0 fehlende Prüfberichtwerte, 4 vom Emittenten als beendet gemeldet; keine `tradeApproved`-Zusage. Marktcache und Hintergrundstatus beobachtet, Forschungs-Selbstreview noch `unavailable`; Teilbereiche der kurzen XAUS-Zeithistorie veraltet und einige Simulationsfälle inkonklusiv. **Kein allgemeiner Erfolgsnachweis für alle 20 Funktionen.**
- **Mobile Gold-ISIN-Anzeige:** PR #758 hat noch keine erfolgreiche vollständige CI/kein bestätigtes Produktionsrelease. Nicht als erledigt markieren.
- **CI-Stabilisierung:** PR #755 mit Browse-Cache ohne `playwright install --with-deps` wurde nach grüner PR-CI in `main` zusammengeführt. CI auf weiterentwickelten Ständen und das Release-Gate bleiben zu kontrollieren.
- **Nicht erlaubt:** automatische DEGIRO-Orders, Handel ohne aktuellen echten Brokerkurs, Aufweichen von Knock-out-, Stop-, Freigabe-, Datenfrische- oder Risikoregeln; keine E-Mails ohne Benutzerfreigabe.

## Nächste testbare Lieferung

1. **Zuerst:** Produktübersicht PR #758 (inkl. Einzel-ISINs) gegen neuestes `main` mit allen 13 Browsertests prüfen; CI-Abhängigkeiten aus PR #755 verwenden. Danach `main`-Release-Gate, Render-Deploy-SHA und Sichtkontrolle auf echtem Samsung. Damit den aktuell gemeldeten Fehler beheben.
2. **Danach:** gemeinsame Pflichtdaten-/Hakenlogik (Punkte 3–4, 9) hinter einer klaren reinen Lese-Schnittstelle, mit Identitäts- und Frischetests.
3. **Parallel begrenzt:** Kennzahlen für Daten-/Worker-Abrufe und Ausfälle (8, 17), Simulations-P/L und Ursachen (13–14), private Fehlerzustände (16) instrumentieren, ohne die bestehenden Signale oder Strategien automatisch zu ändern.
4. **Anschließend:** mobile Bildserien-Tests, SnapTrade-/Broker-Abgleich, vollständige Forschungsnachweise, reproduzierbare Sicherungen, schrittweise Modulmigration und Android-Abnahme (5–7, 10–12, 15, 19–20).

**Gesamturteil: Bob ist messbar ausgebaut und teilweise automatisiert. Keinesfalls sind alle 20 Punkte vollständig abgenommen.** Jede Zeile bleibt offen, bis ihre letzten Akzeptanzkriterien nachweislich erfüllt sind.

## Weitere Umsetzung: gemeinsamer Produktprüfbericht (22.10.2026)

- Neuer Stand auf einem **gesonderten Entwicklungszweig**:
  `bob_audit_read_pool.js` dedupliziert gleiche `GET /api/degiro/audit`-Anfragen
  der Startübersicht, Produktliste und Prüfpanel innerhalb derselben Browserseite.
- Ein laufender Abruf wird geteilt; erfolgreiche Antworten werden für höchstens
  drei Sekunden lokal im Speicher gehalten. Quellzeit und Reportinhalt bleiben
  erhalten, jeder Empfänger bekommt eine unabhängige Kopie. Kein Server-
  Datenbank-Schema, keine Produktkurse, KO-/Risikoänderungen oder Echtgeldorder.
- HTTP-/Authentifizierungsfehler oder ungültige Originalzeiten müssen weiterhin
  scheitern. Ein fehlender Bericht wird nicht in einen grünen Haken umgewandelt.
- Dieser Schritt ist **teilweise Umsetzung** der Punkte 8, 9 und 17. Nicht als
  Fertigstellung aller 20 Punkte oder als produktives Release ausgeben.
