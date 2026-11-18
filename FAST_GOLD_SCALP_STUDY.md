# Prospektive Gold-Schnelleinstiege nach starken 1m-Bewegungen (18.11.2026)

**Nur isolierte Forschungs-Schattenkonten, keinerlei echte Orders.** Diese Ergänzung erweitert ausschließlich `rapid_leverage_study.py`; die seit dem 10.11. laufenden vier 5m-Kohorten und sämtliche normalen Papierkonten bleiben unverändert. Bestehende JSONB-Zustände werden beim nächsten Worker-Tick um die drei neuen, leeren Kohorten ergänzt; es gibt weder Rückdatierungen noch historische Fill-Erfindungen.

## Drei unabhängige Ansätze

| Setup | Einstieg aus schon geschlossenen Originalkerzen | Ziel | Ohne Fortschritt | Max. Haltedauer |
|---|---|---|---|---|
| `fast1m-impulse` | letzte 1m-Kerze hat >0,85 ATR1 Veränderung und >0,7 ATR1 Körper, Schluss nahe dem Extrem | 1,4R | 6 Minuten | 20 Minuten |
| `fast1m-rebound` | nach lokalem 12m-Tief bzw. Hoch zwei 1m-Schlüsse in Gegenrichtung, Durchbruch über/vorheriges 1m-Hoch oder -Tief und Bewegung >=1,5 ATR1 | 1,6R | 8 Minuten | 30 Minuten |
| `fast3m-breakout` | bestätigter 3m-Schluss über/unter dem Hoch/Tief der vorherigen fünf 3m-Kerzen mit ATR3-Puffer | 1,8R | 10 Minuten | 45 Minuten |

ATR1: True Range der letzten 14 geschlossenen Original-1m-Kerzen. 3m-Kerzen ausschließlich aus derselben kohärenten Original-1m-Serie, nicht aus geschätztem Spot. LONG und SHORT jeweils spiegelbildlich. Alle drei Varianten dürfen auch bei Bobs normalem `NEUTRAL`-Signal *hypothetische* Positionen öffnen; das Hauptsignal bleibt vollständig unverändert.

## Ausgangs- und Risikoregeln

- Ein virtuelles EUR-1.000-Schattenkonto **je Setup mit sieben mathematischen Hebel-Szenarien (3×, 5×, 8×, 10×, 15×, 20×, 30×)**. Max. Kapitalbindung 65 %, rechnerisches Risiko 1 % des jeweiligen Modellkontos *bei idealer Stopausführung*. Kein Kredit. Höhere Hebel werden für den risikogleichen Vergleich kleiner dimensioniert.
- Anfangsstopp auf der jüngsten Marktstruktur mit 0,2 ATR Puffer; Abstand 0,9–2,5 ATR im schnellen Setup. Schon beim beobachteten +0,7R Einstandsstopp; nach +1,1R Nachziehen um 0,7 ATR. Ein Stopp wird nie gelockert.
- Bei beobachteter Gegenbewegung von mindestens 0,8 ATR vom besten beobachteten Kurs nach mindestens +0,7R Bewegung und zwei Minuten Haltedauer: unmittelbarer virtueller Ausstieg **zum nächsten tatsächlich beobachteten Kurs**, ebenso bei erreichtem Ziel, Stopp, Zeitlimit oder fehlendem Fortschritt.
- Drei Minuten Wiedereinstiegspause je Setup, max. 100 neue Fälle je Setup; nach 3 % rechnerischem Tagesverlust des 10×-Referenzkontos keine weiteren neuen Einstiege in diesem Setup am selben Zürcher Kalendertag.
- Frischer Original-Spot und geschlossene Original-XAU/USD-Minutenkerzen erforderlich; fehlende Minuten, unterschiedliche Instrumente, stale Quotes und Beobachtungslücken über 90 Sekunden erzeugen keinen künstlichen Gewinn. Einstiege in den vorgegebenen Handelszeiten. Eine nach der Signalkerze schon über 1,2 ATR weitergelaufene Quote führt zu `fast-quote-chased`.
- Wie in den vorhandenen Schnellhebel-Studien **nur Modell-Sensitivität**: hypothetische 0,6 % variable Rundreisekosten plus 2 EUR je Trade; keinerlei nachgewiesene DEGIRO-Brief-/Geld-, KO-, CHF/EUR-, Gebühren- oder tatsächlichen Fill-Daten. Rendite eines multiplizierten Gold-Spot-Kurses ist *nicht* die Rendite eines Knock-out-Produkts.

## Abnahme

1. `python -m unittest test_fast_gold_scalp_study.py test_rapid_leverage_study.py` und bestehende CI vollständig grün.
2. Nach Merge und erfolgreichem Render-Rollout im privaten Diagnoseschnitt `newStudiesBrief.rapid` sieben benannte Setups, neue Originalzeitstempel, beobachtete Einstiege/Ausstiege und Blockgründe nachweisen.
3. Vergleiche mindestens 20 vollständig beobachtete, nicht rückwirkend erzeugte Fälle pro Setup, dazu Verlusttage, modellierten Drawdown, Kosten und Datenabdeckung. Keine Empfehlung oder Verschiebung echter Handelsparameter allein wegen eines starken Tages.
4. Für echte KO-Nettoergebnisse separater prospektiver Nachweis von datierten Geld-/Brief-, KO- und Währungswerten. Keine automatische Echtgeld-Strategiefreigabe.

**Status dieser Datei:** Spezifikation und Implementierungsbasis. Ein GitHub-Commit beweist keine laufende Produktionssimulation; erst ein überprüftes Render-Deployment und der erste neue Originaldaten-Tick belegen den Start.
