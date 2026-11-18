# Gold: zusätzliche schnelle Ausstiegsvarianten und prospektiver Vergleich

**Anlass:** Am 18.11.2026 zeigen die bereits laufenden 1m/3m-Schnellversuche trotz virtueller Einstiege vorläufig Verluste. Die Beobachtungen sind noch keine statistisch aussagekräftige Grundlage für Echtgeldregeln. Der vorhandene 5.000-EUR-No-EMA-Paper-Test zeigt zugleich große Tagesschwankungen. **Kein bestehender Fall wird geändert oder rückwirkend nachgebucht.**

## Hypothesen: gleiche Einstiege, verschiedene Ausstiege

Drei neue, unabhängige Beobachtungsarme werden beim ersten produktiven Tick der Erweiterung mit **1.000 EUR Modellstartkapital je Arm** erzeugt. Sie verwenden exakt dieselben bereits geschlossenen XAU/USD-1m-Kerzen, dasselbe LONG/SHORT-Signal, denselben Original-Spot und dieselbe anfängliche 0,9–2,5-ATR-Strukturstoppschwelle wie ihre bestehenden Kontrollarme. Ein fehlendes Originalsignal verhindert sowohl den Kontroll- als auch den Varianteneinstieg.

| Neuer Studienarm | Kontrollarm | Ziel | Max. Haltedauer | Ausstieg ohne >=0,25R Fortschritt | Einstand ab | Nachziehen ab / Abstand |
|---|---|---:|---:|---:|---:|---:|
| fast1m-impulse-exit10 | fast1m-impulse | 1,0R | 10 Minuten | 3 Minuten | +0,5R | +0,8R / 0,5 ATR |
| fast1m-rebound-exit15 | fast1m-rebound | 1,2R | 15 Minuten | 5 Minuten | +0,6R | +0,9R / 0,6 ATR |
| fast3m-breakout-exit20 | fast3m-breakout | 1,4R | 20 Minuten | 6 Minuten | +0,7R | +1,0R / 0,65 ATR |

Die jeweilige beobachtete Gegenbewegung gegenüber dem bisherigen besten beobachteten Kurs führt je nach Variante ab +0,5/+0,6/+0,7R Fortschritt und 0,6/0,7/0,7 ATR Rückfall zum Exit, frühestens nach zwei Minuten. In jedem Fall gilt der **nächste echte Beobachtungskurs**, nicht der idealisierte Stopkurs. Kein Lockerungs- oder Lücken-Bypass.

Alle übrigen Eigenschaften bleiben kontrolliert gleich: sieben Hebel-Sensitivitäten (3×, 5×, 8×, 10×, 15×, 20×, 30×), maximal 65 % Kapitalbindung, hypothetisches 1 % Risikobudget je Einstieg, angenommenes 0,6 % variables Rundreisekostenmodell plus 2 EUR, 3 % rechnerische Tagesverlustgrenze beim 10×-Referenzarm und dreiminütige Pause nach einem Abschluss. Alle Beträge bleiben ausschließlich **mathematische Spot-Hebel-Proxys**, keine KO-/DEGIRO-Nettogewinne.

## Kontinuierliche Auswertung statt Gewinnbehauptung

- Die bisherigen **sieben** Setups bleiben erhalten und bilden mit drei neuen insgesamt **zehn unabhängige Forschungsarme** mit 70 mathematischen Hebelszenarien. Die 15 vorhandenen Papier-Euro-Konten laufen weiter. Kein produktiver Signal-/Ranking-/Push-/DEGIRO-Pfad wird verändert.
- Neue und alte Konten niemals vermischen; Vergleich pro Paar nur bei **identischem Signalkerzenzeitstempel, Richtung, beobachtetem Eintrittskurs und belegtem Ausstieg**. Wenn die eine Variante später wegen anderer Haltezeit nicht erneut einsteigen kann, kein scheinbar gepaarter Fall.
- Ergebnisse: abgeschlossene/noch offene/unentscheidbare Fälle, Netto-Modell-P/L nach Annahmekosten, beobachtetes durchschnittliches R, Stop-/Ziel-/Umkehr-/Zeit-Ausgangsgründe, Drawdown und Quellenabdeckung. Berechnete Kurswege niemals als DEGIRO-Kursnachweis ausgeben.
- Vor jeder Nutzungsentscheidung: mindestens **20 vollständig beobachtete, kausal passende Paare pro Variante** und eine zusätzliche zeitlich getrennte Validierungsperiode, Frischdaten-/Originalquotenquote sowie nachvollziehbare Kostenannahmen. Eine nominal bessere Hebelrendite allein ist kein Erfolg.
- **Keine Echtgeldfreigabe**: Erst datierte echte Produkt-Geld-/Briefkurse, KO-Schwellen, Bezugsverhältnis, EUR/CHF/FX, Gebühren, Slippage, Handelbarkeit und nachgewiesene Ausführungsbedingungen ermöglichen einen Produkt-Nettovergleich. Eine virtuelle 1-%-Stopplimitierung begrenzt KO- oder Gap-Verluste nicht zuverlässig.

## Abnahme

1. Tests: `python -m unittest test_rapid_paired_exit_study.py test_fast_gold_scalp_study.py test_rapid_leverage_study.py test_bob_diagnostics.py` plus gesamte GitHub-CI und Risiko-/Security-Checks.
2. Nach CI Merge und Deployment exakt die Merge-Revision auf beiden Render-Diensten prüfen.
3. Im Bob-Diagnosebericht `newStudiesBrief.rapid` **10 Setups, 70 Konfigurationen**, separate neue `started/closed/open/inconclusive`-Zähler, `pairedControl`, datensparsame Exitgrund-Zähler und Mittelwert beobachteter R erkennen; neuer Start muss bei null Fällen beginnen.
4. Nur bei ausreichend frischen geschlossenen Original-1m-Kerzen darf die Studie virtuell einsteigen. Keine Nachbuchung des 18.11.-Goldsprungs oder stilles Übertragen auf Echtgeldregeln.
