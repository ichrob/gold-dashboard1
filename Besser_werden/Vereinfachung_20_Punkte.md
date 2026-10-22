# Bob vereinfachen: Umsetzungsstand und Sicherheitsgrenzen (22.10.2026)

Diese Checkliste trennt **tatsächlich implementierte Funktionen** von noch offener
Integration und von Arbeiten, für die ein externer Zugang / ein gesondert
abgesichertes Release nötig ist. Eine neue Datei oder ein bestandener Unit-Test
ist **kein** Nachweis, dass die Produktions-Web-App den Stand schon ausliefert.
Die bestehende DEGIRO-Produktfreigabe, Knock-out-Regeln und Echtgeldorder-Sperre
bleiben unverändert.

## 20 Schritte

| Nr. | Ziel | Aktueller Stand | Noch notwendiger Nachweis / Arbeit |
| --- | --- | --- | --- |
| 1 | Zentrale Startseite | Neue kompakte Arbeitsübersicht `bob_unified_workspace.js` auf Entwicklungsbranch; bestehende Bereiche bleiben unverändert | Android-Browserprüfung nach sicherem Release |
| 2 | Ein-Klick-Vorbereitung | Ein user-initiiertes `loadData(true)`, gefolgt vom bestehenden Produktquellenabruf bei vorhandenen Identitäten | Ausfall-, Laufzeit- und Quotenprüfung am Render-Dienst |
| 3 | Einheitliche Produktkarte | `degiro_all_products.js` vereinigt bereits vorhandene Daten; neue Übersicht bietet Produktauswahl | Vollständige einheitliche Detaildarstellung der Evidenz ohne neue Handelsfreigabe |
| 4 | Einheitliche Status-Haken | Vorhandene Produkttests und Gesamtprüfung bleiben erhalten | Alle Ansichten auf exakt dieselbe Prüflogik umstellen und Regressionstests ergänzen |
| 5 | Menüs vereinfachen | Bestehende mobile Navigation gruppiert; neue Querverweise bündeln Kernwege | Auf echtem Android auf Lesbarkeit, Scrollen und Doppeleinträge prüfen |
| 6 | Screenshot-Teilen | Android Companion enthält lokale Share- und OCR-Funktionen | APK-Version auf Gerät installieren, OCR-Serien und fehlende ISIN prüfen |
| 7 | DEGIRO-Liste weiterverwenden | IndexedDB-Archiv mit atomarem Austausch vorhanden; neuer optionaler Vergleich sichtbarer ISIN-Identitäten seit letztem manuellen Prüfknopf, ohne die Listenfreigabe zu verändern | Vollständiger Tagesvergleich des echten Screenshot-Produktbestands (nicht bloß der sichtbaren Teilmenge) bleibt offen |
| 8 | Gemeinsame Kurszeiten | `liveBundleCache` wird vom vorhandenen Analyseweg verwendet; neue Anzeige kontrolliert unveränderte Spot-Originalzeit | Offenen Zeitstempel-Randfall #677 prüfen, 60-s-Grenze nicht aufweichen |
| 9 | Automatische Quellen-Nachforschung | Bestehende Emittenten-/Ersatzquellen, Reparaturpfade vorhanden | Einheitliche Prioritätskette und verbindliche Zustandsmetadaten je Feld |
| 10 | SnapTrade + CSV | Schreibt nur lesbare/verifizierte Depotpositionen; vorhandene Identitätsprüfung | Exportstände und laufende Depotänderungen mit Konfliktregeln gemeinsam darstellen |
| 11 | Orderentwürfe | Neuer Direktweg vom ausgewählten Produkt zur bestehenden manuellen Eingabemaske | Auf Mobilgerät prüfen; DEGIRO-Order muss weiterhin manuell erfolgen |
| 12 | Verkäufe auswerten | SnapTrade-Journal und echte Trade-Erfassung vorhanden | Eindeutige Fill-/Gebühren-/Währungszuordnung; keine erfundene Netto-P/L |
| 13 | Simulations-Cockpit | Simulation, Lernen und Diagramme existieren; neue Direktnavigation | Gemeinsame Statusübersicht statt getrennter Berichte |
| 14 | Varianten automatisiert prüfen | Getrennte Paper- und Strategie-Vorwärtstests vorhanden | Vergleichsmetriken/Kosten und belastbare Out-of-sample-Freigabe; keine automatische Regeländerung |
| 15 | MCO-Videos | Kanalfilter, Untertitel und begrenzte Bild-Analyse vorhanden | Belegbare Transkripte und Filmframes ohne Authentifizierungsumgehung |
| 16 | Problemzentrale | Bestehender unabhängiger Watchdog, Issues und idempotente Neustarts | Diagnose-/Reparaturstatus zentral vereinheitlichen; kein automatischer Chat-Zugriff |
| 17 | Hintergrundjobs koordinieren | Separate Worker bleiben unverändert. Die CI unterbricht auf dem PR-Zweig nun veraltete PR-Läufe, ohne Hauptzweig-Prüfungen abzubrechen | Last/Quoten der eigentlichen Markt-/Forschungsjobs analysieren, Abrufe deduplizieren, Worker nicht ungetestet zusammenlegen |
| 18 | Sichere Veröffentlichungen | CI, Smoke, Health Workflows vorhanden; Render deployt bei `main`-Commit | Echtes CI-vor-Deploy-Gate benötigt koordinierte Render-/GitHub-Konfiguration. Nicht blind abschalten |
| 19 | Monolith zerlegen | Neue Funktionen erstmals als eigenständiges Modul mit eigenen Tests | `Bob.html`/`degiro_assistant.js` schrittweise nach Golden-Master-Tests refaktorieren |
| 20 | Sicherung | Neue **freiwillige lokale** Export-/Importfunktion für ausschließlich heutige Orderentwürfe; strenge JSON-/ISIN-/Betragsvalidierung, kein Überschreiben aktueller Entwürfe | Browserprüfung und gesondertes Datenschutz-/Speicherkonzept für Originalbilder/weitere Daten |

## Akzeptanzkriterien für die aktuelle Umsetzung

- Der bestehende Markt-/Analyse-/Produkt-/Trade-Code bleibt unverändert; das neue
  `bob_unified_workspace.js` ist **nur** UI-Orchestrierung mit einem bereits existierenden
  Abrufpfad und einer freiwilligen lokalen Dateisicherung.
- Spot-Originalzeit wird weder erzeugt noch überschrieben. Mehr als 60 Sekunden
  alte Spot-Zeiten dürfen keine grüne Marktbestätigung ergeben.
- Reine Produktidentitäten sind ausdrücklich **keine** aktuelle Handelbarkeit.
  Selektierte ISINs dürfen nur in die manuelle Ordermaske übertragen werden.
- Keine SnapTrade-Schreiboperationen, DEGIRO-Botsteuerung, Echtgeldorders,
  Änderungen von Hebel-/KO-/Stopp-/Risikoregeln oder automatische Anwendung
  experimenteller Strategien.
- Auf dem Entwicklungsbranch zunächst `node test_bob_unified_workspace.js`,
  `node test_degiro_handoff.js`, die komplette Bob CI und der Browser-Smoke.
  Erst bei bestandenem CI, passendem Deployment und eigenständiger mobiler
  Prüfung als live ausgeben.

## Rollout und weitere Bearbeitung

1. Pull Request prüfen und CI abwarten. Andere offene Android-/Produkt-PRs nicht
   gleichzeitig blind zusammenführen; neue Branchbasis erneut prüfen.
2. Kein Produktions-Deployment allein aufgrund eines neuen Feature-Commits.
   Bei `autoDeployTrigger: commit` erst Release-Gate konfigurieren, bevor das
   automatische Deploy-Verhalten verändert wird.
3. Nach dem Release Android-Klickweg, Screenshot-Upload und Backup-Wiederherstellung
   auf dem Nutzergerät validieren.
4. Offene Punkte 3–20 in getrennten, testbaren Folgeänderungen umsetzen; diese
   Statusmatrix ausdrücklich nicht als vollständige Erledigung interpretieren.
