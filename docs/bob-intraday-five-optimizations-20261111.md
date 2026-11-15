# Bob: fünf Intraday-Optimierungen mit belegbarer Wirkung · 11.11.2026

## Zweck
Gold LONG/SHORT, geplante Haltedauer 30–300 Minuten. Die Optimierung darf **nicht**
aus mehr Einstiegen automatisch höhere Gewinne ableiten. Alle neuen Varianten sind
rein virtuell, vorwärtsgerichtet und wirken **nicht** auf DEGIRO-Orders, aktive Trades,
Produkt-/KO-Freigaben oder den Haupt-Stop.

## 1. Früher einsteigen, ohne alte Signale als neu auszugeben
Bereits in `#1532` umgesetzt: frischer, vollständig geschlossener 5m-Folgeimpuls
mit eigenem Zeitstempel. Als unabhängige Studienvarianten vorhanden:
`fast3`, `fast3neutral`, `follow5`, `follow5neutral`, `score65`,
`score70`, `rr20`. Keine automatische Übernahme vermeintlich „besserer“
Schwellen ohne Originaldaten- und Verlustvergleich.

## 2. Neue November-Simulationskonten tatsächlich diagnostizierbar machen
`trend800nov` und `normal1000nov` behalten ihre getrennten Kontostände,
maximal 65 % Kapitalexposition, 3-%-Tagesverlustschutz und max. 300 Minuten
Haltedauer. Der bereits in den Kontrollständen gespeicherte letzte Sperrgrund
wird in der privaten, begrenzten Papiergewinn-Sicht als **normalisierter Code**
angezeigt (kein ISIN- oder Geheimnis-Text). Die Diagnose löst keine Sperre.
Ein Konto ohne Original-Geld-/Brief, geeignete ISIN oder belegten KO-Schutz
muss weiter mit 0 Trades und explizitem Sperrgrund erscheinen. Ein fehlender
Broker-Ausführungskurs darf nicht als virtueller Gewinn ausgegeben werden.

## 3. Dynamischen Gewinnschutz gegen feste Stopps vergleichen
Neue isolierte `intraday_timing_study`-Varianten für die bestehenden
Horizonte 30/180/300 Minuten und die Original-/Modell-Kohorten:

- `breakeven5`: erst nach **beobachtetem** Gewinn von 1R wird der Stopp
  gegebenenfalls auf Einstand angehoben.
- `trailatr5`: nach beobachtetem +1R Einstand; ab +1,5R Stopp in
  Trendrichtung auf `aktueller beobachteter Spot –/+ 1 ATR` nachziehen.

Der Stopp wird niemals gelockert, nie bei ungültigem ATR gesetzt,
nicht rückwirkend zwischen Quellenbeobachtungen und nicht bei
bereits festgestelltem Exit korrigiert. Bestehende Konten/Stopps bleiben
unberührt; der Preis beim nächsten Originalbeleg bestimmt das Modell-Exit,
kein garantierter Stop-Fill.

## 4. Originaldaten und unentscheidbare Fälle sichtbar lassen
Aktive strikte Original-1m/5m-Fallbacks (inklusive `#1539`) unverändert.
Ausfälle >90 Sekunden, widersprüchliche Quellen, fehlende Ausstiege
und nicht vorhandene Produkt-Geld-/Briefseiten bleiben *unentscheidbar*.
Neue Studien zählen diese Fälle separat. Keine rückdatierte Auffüllung,
kein Überschreiben historischer Originalereignisse, keine Bewertung alter
verlorener Fälle als neue erfolgreiche Trades.

## 5. Hebel nach *modellierten Kosten und Verlusten* vergleichen
Die bestehende Schnellhebelstudie testet 3×/5×/8×/10×/15×/20×/30×
bei gleicher beobachteter Einstiegs-/Ausstiegsuhr und mit:
- 1-%-Risiko-Modellbudget / max. 65-%-Exposition,
- alternativ gleichem 65-%-Euroeinsatz als separates Risiko-Szenario,
- Modellkosten von 0,6 % variablem Rundlauf + 2 EUR je virtuellem Trade,
- beobachteter Gegenbewegung, Stopp, Drawdown und nicht bepreisten Fällen.

Neu: Eine **explorative Spot-Proxy-Führung** darf erst bei mindestens 20
vergleichbaren vollständigen Modellabschlüssen je Hebel und Setup,
identischen Fallzahlen, keiner unentscheidbaren oder ausgeschlossenen
Hebelauswertung erscheinen. Vorher: `insufficient-comparable-evidence`.
Selbst nach 20 Fällen bleibt `strategyWinnerConfirmed=false` und
`netProductVerified=false`: Das ist **keine** historische KO-Produktrendite.
Für die Netto-Euro-Abnahme der echten KO-Hebel einschließlich Brief/Geld,
Spread, Gebühren, FX und KO bleibt `#1531` zuständig.

## Abnahme
1. Isolierte Unit-/Regressionstests grün, inklusive LONG/SHORT-Symmetrie,
   fehlendem ATR, nie gelockertem Stopp und geheimnisfreiem Sperrcode.
2. Bob CI, Risiko-Checks und CodeQL auf dem PR-Head grün.
3. Nur nach dem getesteten Merge kontrollierter Deploy; beide Render-Dienste
   und gespeicherte aktuelle Revision separat prüfen.
4. Während Handelsfenstern neue **echte vorwärts aufgezeichnete** Fälle:
   Anzahl valide / unentscheidbar, Originalzeitbasis, Blockcodes,
   Einstiegsverzögerung, modellierte Netto-EUR nach Kosten,
   Drawdown und maximaler Verlust je Variante.
5. **Keine automatische Strategie-Promotion** allein durch zwei gute
   Trades, Proxy-Hebelprozente oder unbestätigte Produktpreisannahmen.

## Rücknahme
Alle neuen Stop-Varianten sind zusätzliche Forschung. Bei Regression
werden sie deaktiviert/entfernt, ohne historische Fälle umzuschreiben
oder die aktiven Hauptregeln zu lockern.
