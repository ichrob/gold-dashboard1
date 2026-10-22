# Bob – 100-Punkte-Audit des erweiterten Lesezugriffs

Stand 22.10.2026. Diese Datei bildet **alle 100 angefragten Punkte** ab. Keiner gilt allein wegen einer vorhandenen Codedatei als vollständig umgesetzt.

Status-Legende: `partial` = thematische Codebasis vorhanden, Ende-zu-Ende noch nicht bewiesen; `planned` = eigene Entwicklung/Prüfung offen; `blocked-client` = vorhandene Bob-API, ChatGPT-Tool-Discovery nicht aktualisiert; `requires-device` = nur mit freiwilliger Samsung-Diagnose testbar.

**Vollständiger Nachweis pro Punkt verlangt:** fest definierte Eingabe, Originalzeit, sichere Projektion ohne Geheimnisse, Regressionstest, CI-Erfolg, verwendete GitHub-Commit-ID und anschließende Live-Prüfung. Heute sind 0/100 nach diesem strengen Kriterium abgeschlossen.

**Regeln:** Kein versteckter Android-Zugriff, keine Echtgeldorders, keine Handelsfreigaben, keine automatische Änderung an KO-/Stop-/Risiko-/Strategieregeln. Die Reihenfolge ist technischer Diagnoseausbau, keine Renditegarantie.

## Arbeitsliste
### Diagnosezentrale

| Nr. | Prüfziel | Status | Code-Anknüpfung |
|---:|---|---|---|
| 1 | ChatGPT-Werkzeugbeschreibung aktualisieren | blocked-client | `bob_diagnostics.py` |
| 2 | Neue Bob-Module erkennen | partial | `bob_diagnostics.py` |
| 3 | Modul-/Abhängigkeitsverzeichnis | planned | `bob_diagnostics.py` |
| 4 | Gesundheit jedes Moduls | partial | `bob_diagnostics.py` |
| 5 | Original-/Abruf-/Prüfzeit getrennt | partial | `bob_diagnostics.py` |
| 6 | Gezielte Einzelabfragen | partial | `bob_diagnostics.py` |
| 7 | Historische Diagnosefenster | partial | `bob_diagnostics.py` |
| 8 | Vergleich früherer Zustände | planned | `bob_diagnostics.py` |
| 9 | Fehlerursachen korrelieren | partial | `bob_diagnostics.py` |
| 10 | Gesamtstatus mit Nachweisen | partial | `bob_diagnostics.py` |

### Render und Hintergrundjobs

| Nr. | Prüfziel | Status | Code-Anknüpfung |
|---:|---|---|---|
| 11 | Workerzyklen und Fälligkeit | partial | `bob_self_healing.py` |
| 12 | Verpasste 30-Sekunden-Takte | partial | `bob_self_healing.py` |
| 13 | CPU-/RAM-Auslastung | partial | `bob_self_healing.py` |
| 14 | Serverneustarts und Crashursachen | partial | `bob_self_healing.py` |
| 15 | HTTP-Fehler je Endpunkt | partial | `bob_self_healing.py` |
| 16 | Datenbanksperren/Timeouts | partial | `bob_self_healing.py` |
| 17 | Warteschlangen und Verluste | partial | `bob_self_healing.py` |
| 18 | Gleiche Build-Version auf Diensten | partial | `bob_self_healing.py` |
| 19 | Deployment-Regressionsvergleich | planned | `bob_self_healing.py` |
| 20 | Wirkung von Neustarts | partial | `bob_self_healing.py` |

### Goldmarkt und Kursdaten

| Nr. | Prüfziel | Status | Code-Anknüpfung |
|---:|---|---|---|
| 21 | Spot-Originalkurse | partial | `candle_reliability.py` |
| 22 | CFD-Herkunft und Abweichung | partial | `candle_reliability.py` |
| 23 | Future-Kontrakt und Verzögerung | partial | `candle_reliability.py` |
| 24 | FX-Werte mit Zeitbezug | partial | `candle_reliability.py` |
| 25 | Qualität jeder Kursquelle | partial | `candle_reliability.py` |
| 26 | Quellenwechsel dokumentieren | partial | `candle_reliability.py` |
| 27 | Lücken/Fehler in Kerzen | partial | `candle_reliability.py` |
| 28 | Historisches EMA200-Backfill | partial | `candle_reliability.py` |
| 29 | Quellen je Zeitfenster | partial | `candle_reliability.py` |
| 30 | Gemeinsame Eingangsdatensätze | partial | `candle_reliability.py` |

### Goldprodukte und DEGIRO

| Nr. | Prüfziel | Status | Code-Anknüpfung |
|---:|---|---|---|
| 31 | DEGIRO-Listenstände archivieren | partial | `degiro_product_audit.py` |
| 32 | Neue/entfallene ISINs vergleichen | partial | `degiro_product_audit.py` |
| 33 | Screenshot-Serien richtig zuordnen | partial | `degiro_product_audit.py` |
| 34 | OCR-Felder getrennt prüfen | partial | `degiro_product_audit.py` |
| 35 | Herkunft jedes Produktwertes | partial | `degiro_product_audit.py` |
| 36 | SG/BNP/comdirect-Quellen prüfen | partial | `degiro_product_audit.py` |
| 37 | Geld-/Briefkursnachweise | partial | `degiro_product_audit.py` |
| 38 | Original- und berechneten Hebel trennen | partial | `degiro_product_audit.py` |
| 39 | KO/Basis/Ratio/Laufzeit prüfen | partial | `degiro_product_audit.py` |
| 40 | Produktidentität und Handelsplatz belegen | partial | `degiro_product_audit.py` |

### Ranking und Signale

| Nr. | Prüfziel | Status | Code-Anknüpfung |
|---:|---|---|---|
| 41 | Haken/Kreuz pro ISIN erklären | partial | `decision_audit.py` |
| 42 | Top-3-Rangfolge reproduzieren | partial | `decision_audit.py` |
| 43 | Ausschlussgründe ausgeben | partial | `decision_audit.py` |
| 44 | LONG/SHORT/ABWARTEN erklären | partial | `decision_audit.py` |
| 45 | Indikatoren mit Daten belegen | partial | `decision_audit.py` |
| 46 | MTF-Widersprüche erkennen | partial | `decision_audit.py` |
| 47 | Verpasste/unterdrückte Signale | partial | `decision_audit.py` |
| 48 | Einstiegsschutzgründe | partial | `decision_audit.py` |
| 49 | Frühwarnung und Trendkontext | partial | `decision_audit.py` |
| 50 | Entscheidung und späteres Ergebnis verbinden | partial | `decision_audit.py` |

### SnapTrade und Broker

| Nr. | Prüfziel | Status | Code-Anknüpfung |
|---:|---|---|---|
| 51 | SnapTrade vs. DEGIRO getrennt | partial | `snaptrade_bridge.py` |
| 52 | Maskierte Depotbestände | partial | `snaptrade_bridge.py` |
| 53 | Bestandsänderungen | partial | `snaptrade_bridge.py` |
| 54 | Käufe/Verkäufe/Gebühren/FX | partial | `snaptrade_bridge.py` |
| 55 | CSV-ISIN-Zuordnung | partial | `snaptrade_bridge.py` |
| 56 | Doppelte Transaktionen | partial | `snaptrade_bridge.py` |
| 57 | FIFO-Lücken | partial | `snaptrade_bridge.py` |
| 58 | Broker- vs. Emittentenkurse | partial | `snaptrade_bridge.py` |
| 59 | Handelbarkeit je Broker | partial | `snaptrade_bridge.py` |
| 60 | Login-/Synchronisierungsfehler | partial | `snaptrade_bridge.py` |

### Mein Trade und Gewinnschutz

| Nr. | Prüfziel | Status | Code-Anknüpfung |
|---:|---|---|---|
| 61 | Manuelle Trades zuordnen | partial | `trade_stop_review.py` |
| 62 | Einstiegswerte prüfen | partial | `trade_stop_review.py` |
| 63 | Produktkurven vergleichen | partial | `trade_stop_review.py` |
| 64 | Stop/Ziel-Ursprung | partial | `trade_stop_review.py` |
| 65 | Stopp-Nachziehen rechtzeitig | partial | `trade_stop_review.py` |
| 66 | KO-Warnungen verifizieren | partial | `trade_stop_review.py` |
| 67 | Gewinnschutz/Zielketten | partial | `trade_stop_review.py` |
| 68 | FX-Abrechnung pro Trade | partial | `trade_stop_review.py` |
| 69 | Push-Versuch vs. Zustellung | partial | `trade_stop_review.py` |
| 70 | Echte Trade-Ergebnisse evaluieren | partial | `trade_stop_review.py` |

### Simulation und Lernen

| Nr. | Prüfziel | Status | Code-Anknüpfung |
|---:|---|---|---|
| 71 | Fünf Simulationskonten | partial | `paper_simulation.py` |
| 72 | Handelszeit-Durchlauf | partial | `paper_simulation.py` |
| 73 | Virtuelle Ein-/Ausstiege | partial | `paper_simulation.py` |
| 74 | Kosten in Kontoständen | partial | `paper_simulation.py` |
| 75 | Sim-/Originalkurse abgleichen | partial | `paper_simulation.py` |
| 76 | Unklare Simulationsausgänge | partial | `paper_simulation.py` |
| 77 | Simulation-Pausen begründen | partial | `paper_simulation.py` |
| 78 | Strategien identisch vergleichen | partial | `paper_simulation.py` |
| 79 | Lernversuche dokumentieren | partial | `paper_simulation.py` |
| 80 | Unabhängige Vorwärtsprüfung | partial | `paper_simulation.py` |

### Forschung und Selbstkritik

| Nr. | Prüfziel | Status | Code-Anknüpfung |
|---:|---|---|---|
| 81 | Neue MCO/NCO-Videos | partial | `research_learning.py` |
| 82 | Video-Veröffentlichungsdaten | partial | `research_learning.py` |
| 83 | Untertitel-Fehler | partial | `research_learning.py` |
| 84 | Frames und Zeitstempel | partial | `research_learning.py` |
| 85 | Browserless-Kontingent | partial | `research_learning.py` |
| 86 | MCO-vs.-Bob-Kursvergleich | partial | `research_learning.py` |
| 87 | Selbstkritik aus gespeichertem Lauf | partial | `research_learning.py` |
| 88 | Lernfortschritt | partial | `research_learning.py` |
| 89 | Überanpassung erkennen | partial | `research_learning.py` |
| 90 | Experimentelle vs. Live-Regeln | partial | `research_learning.py` |

### Samsung und Reparaturnachweis

| Nr. | Prüfziel | Status | Code-Anknüpfung |
|---:|---|---|---|
| 91 | Installierte Android-Version | requires-device | `android_companion/README.md` |
| 92 | Spracherkennungsdiagnose | requires-device | `android_companion/README.md` |
| 93 | Handy-Freigaben/STOPP | requires-device | `android_companion/README.md` |
| 94 | OCR-Teilen auf Gerät | requires-device | `android_companion/README.md` |
| 95 | Mobile Navigation/Scrollen | requires-device | `android_companion/README.md` |
| 96 | Fehler mit GitHub-Issue verbinden | partial | `android_companion/README.md` |
| 97 | Wiederkehrende Probleme | partial | `android_companion/README.md` |
| 98 | Vorher/Nachher-Reparaturprüfung | partial | `android_companion/README.md` |
| 99 | Security-Prüfung und Rollback | partial | `android_companion/README.md` |
| 100 | Reparatur-Ende-zu-Ende | partial | `android_companion/README.md` |

## Nächste messbare Arbeiten

1. CodeQL ohne Codex-Security-Verbindung testen und gemeldete Schwachstellen nachvollziehbar triagieren.
2. Alle neun `focus`-Diagnoseansichten nach Client-Neuentdeckung testen; fehlende oder verkürzte Daten ehrlich kennzeichnen.
3. Produktnachweise, veraltete Quellen und unklare Simulationsfälle reproduzierbar machen.
4. Originalzeit-/Quellen-Tabelle und Entscheidungs-/Reparaturkorrelation ergänzen.
5. Freiwillige Samsung-APK-Diagnose auf dem echten Gerät testen; niemals ohne Nutzeraktion übertragen.
