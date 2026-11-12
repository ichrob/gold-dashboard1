# Bob – Intraday-Neuausrichtung, 30 bis 300 Minuten (10.11.2026)

## Geltungsbereich und Ziel

Gold XAU/USD, LONG und SHORT, mit DEGIRO-KO/Turbo-Produktprüfung. Geplante Haltedauer ungefähr 30 Minuten bis maximal fünf Stunden; ein Stopp, bestätigter Trendwechsel oder Marktende kann einen früheren Ausstieg auslösen. **Keine automatische Echtgeldorder.** Bestehende historische Testfälle werden nicht geändert oder neu bewertet.

## Aktive, nachvollziehbare Änderung

Die gemeinsame `late_entry_guard.js` prüft weiter echte geschlossene 5m- und 15m-Kerzen, 50 Kerzen je Ebene, lückenlose jüngste Kerzen, XAU/USD-Identität, Gold-Spot-Originalquelle (maximal 60 Sekunden alt), Vergleich von Spot zu Kerzenschluss (höchstens 0,8 ATR) sowie Signalzeit. Der Standard bleibt: höchstens 1,5 ATR über EMA20, kein jüngster Impuls über 2,5 ATR bei ausgedehntem Trend, höchstens 15 Minuten seit Hauptbestätigung ohne neues Setup.

Neu: Auch bei altem Hauptsignal darf ein **eigenständiger, frischer, vollständig geschlossener 5m-Folgeimpuls** als neue Chance geprüft werden. Voraussetzungen: derselbe bereits bestätigte Haupttrend LONG/SHORT, zwei aufeinander folgende Richtungskerzen und steigende/fallende Schlusskurse, Schluss *jenseits* des vorigen Hochs/Tiefs statt bloßem Docht, Mindestfortschritt 0,15 ATR, gültiger Schlusszeitpunkt höchstens 90 Sekunden alt, positiver richtungskonformer EMA-Abstand bis maximal **2,0 ATR**, kein überzogener jüngster 3×5m-Impuls über 2,5 ATR. Alle bisherigen Daten- und Qualitätsprüfungen bleiben bindend. Der Zeitstempel der alten 15m-Bestätigung wird **nicht** überschrieben. Bei einem frischen Folgeimpuls meldet `entryPlanState.code=FRESH_5M_CONTINUATION` den konkreten Grund.

Die Änderung betrifft die technische Vorprüfung eines **neuen** Einstiegskandidaten und die Produkt-Auswahlansicht. Sie erteilt **keine** Broker-, Preis-, KO- oder Positionsfreigabe; Stop-/Zielberechnung und Marktzeitprüfung laufen unverändert. Vorhandene Trades und Stopps sind unberührt.

## Isolierte, zusätzliche Vorwärtsvergleiche

Der bestehende `intraday_timing_study.py` sammelt bereits 3m, 5m, 7m, EMA-/MACD-Varianten, Pullbacks, Trendfolge und Zeitstopp für 30/180/300 Minuten. Neue, nach der Aktivierung getrennt beginnende Arme:

- `fast3neutral`: 3m-Ausbruch bei neutralem, aber verfügbarem 1h-Trend; entgegengesetzter oder fehlender 1h-Trend bleibt gesperrt.
- `follow5neutral`: frischer 5m-Folgeimpuls bei neutralem 1h-Trend, kein Durchbruch bei gegensätzlicher Hauptentscheidung.
- `score65` gegen `score70`: Kollektivrichtungswert LONG >=65 bzw. >=70 und SHORT <=35 bzw. <=30.
- `rr20`: erforderlicher Restzielabstand von 2,0R statt 1,5R der unveränderten Basis-Referenz.

Diese Vergleiche ändern nicht rückwirkend die Historie, nicht die vorhandenen Freigaben und sind **keine** nachgewiesenen Gewinner. Original- und vorsichtig modellierte fehlende Minuten bleiben getrennt; die Original-Zeitstempel werden nicht ersetzt. Vergleich von Nettomodellergebnis nach angenommenen Kosten, ungültigen Starts, maximal beobachteter Gegenbewegung, Verlusten und unbekannten Fällen. Produkt-Spreads, DEGIRO-Gebühren und Ausführung bleiben separat nachzuweisen.

## November-Papierkonten

Nur `trend800nov` und `normal1000nov` erhalten ein Maximum von 300 Minuten statt 240. Bestehende ältere Konten behalten ihre bisherigen vier Stunden. Für alle gilt das 21:45-Uhr-Limit (Europa/Zürich) und der bisherige Stop-/KO-/Kurslücken-/Tagesrisikoschutz. Eine Haltedauer von 30 Minuten ist keine Untergrenze: Ein Stop oder Umkehrsignal beendet früher.

## Unverhandelbare Sicherheitsregeln

- Kein Kauf ohne aktuelle Originaldaten und belegte Geld-/Briefkurse, KO- und Handelsplatznachweis, gültige Stückzahl und Risikobudget.
- Kein Stopp-Lockern, kein ignorierter Knock-out, kein Wiedereinstieg auf derselben Kerze.
- Kein veralteter 15m-Impuls als „neues“ Signal, keine wiederholte Meldung aus derselben ungeänderten Kerze.
- Keine automatischen DEGIRO-Käufe; selbst gute Goldsignalmodelle belegen noch keinen Nettogewinn eines konkreten KO-Produkts.

## Abnahme und Rollback

CI: `test_late_entry_guard.js`, `test_intraday_30_300_policy.py` und bestehende Analyse-/Paper-Tests. Nach Merge: GitHub-Commit und Render-Deploy verifizieren, frische Live-Analyse mit `entryPlanState` nachweisen; neue Papierfälle und Eingangsblocker beobachten. Bei fehlerhaften oder unvollständigen Originaldaten bleibt `ABWARTEN`. Nur anhand unveränderter Originalfälle und gleichzeitiger Risikokennzahlen spätere Parameter optimieren; bei Anstieg von Fehlstarts/Verlusten den neuen Folgeimpuls-Pfad deaktivieren, die alte 1,5-ATR/15-Minuten-Regel belassen.
