# Gold Intraday: vier neue Forschungsfamilien und festgelegte Grenzvergleiche

**19. November 2026 · ausschließlich virtuelle Studien, niemals Echtgeldorders**

## Ziel und bestehende Daten

Der Eigentümer möchte Gold-Turbo-Kurztrades optimieren, mit Haltedauern zwischen 10 und 120 Minuten (einzelne Bob-Altstudien bis 300 Minuten). Im aktuellen Bob laufen bereits 15 Gold-EUR-Papierkonten, 11 Rapid-Spotstudien (77 Hebel-Sensitivitäten), 102 Intraday-Timingvarianten, 18 Entry/Exit-Varianten und sechs Opportunity-Varianten. Ein Teil der Rapid-Studien weist negative modellierte Ergebnisse aus; aus wenigen Originalabschlüssen darf kein Markt- oder Produktsieger abgeleitet werden.

**Nicht duplizieren:** Schon vorhanden sind einfache Trendfolge, Rücksetzer, Follow-through, EMA-/MACD-Filter, Score 65/70, Mindest-CRV 2R, Einstandsstopp, ATR-Trail, schnelles 1m und eine älter gewordene `product-e2e`-Studie. Diese Programme werden weder überschrieben noch neu initialisiert.

## A. Neue, isolierte Original-Spot-Kurzstudie `gold-short-regime-20261119-v1`

Es sind drei von vornherein festgelegte **Setup-Familien**, keine Auto-Optimierung:

1. **`trend-reentry`**: Ein 15m/1h-DMI-bestätigter LONG-/SHORT-Trend (ADX mindestens 25 im Referenzfall) besteht, eine geschlossene 5m-Kerze korrigiert gegen den Trend, danach bestätigt eine weitere geschlossene 5m-Kerze die Fortsetzung. EMA20/EMA50-Richtung wird gesondert geprüft. Maximal 90 Minuten Haltedauer.
2. **`breakout-retest`**: Eine schon geschlossene 5m-Kerze durchbricht einen früheren Hoch-/Tiefkurs, eine weitere testet das Niveau zurück, eine dritte bestätigt eine Fortsetzung. Kein Kauf beim bloßen ersten Spike. DMI/ADX-Trendfilter und EMA-Richtung wie oben. Maximal 60 Minuten Haltedauer.
3. **`false-breakout`**: Eine schon geschlossene 5m-Kerze sticht über eine vorherige Preisspanne hinaus, die folgende schließt zurück innerhalb der Spanne, eine weitere bestätigt den Rückweg. Nur bei begrenzter 15m-ADX-Trendstärke (höchstens 25) und nicht gegen ein bereits bestätigtes gegenteiliges Hauptsignal. Maximal 45 Minuten Haltedauer. Historische Bob-`mean-revert`-Walk-Forward-Befunde sind Kontext, keine vorgetäuschte Validierung dieser neuen Regel.

Für **jede** der drei Familien bestehen sieben **einzeln verändernde**, bereits vorab fixierte Varianten:

| Name | Vergleich zur Kontrollstrategie |
|---|---|
| `control` | ADX 25; Alter der letzten bestätigten 15m-Kerze ≤15 min; Spot/Signal ≤0,8 ATR; Zielraum mindestens 1,5R; Zeitstopp nach 15 min ohne 0,25R Fortschritt; modelliertes Risikobudget 1 % |
| `adx20` | ADX-Schwelle 20 statt 25 (bei Fehlausbruch maximal 20 statt maximal 25) |
| `age25` | Letzte 15m-Signalkerze bis 25 statt 15 min alt; aktuelle 5m-Originalbestätigung bleibt zwingend |
| `drift11` | Erlaubter Spot/Signal-Schlussabstand 1,1 statt 0,8 ATR; keine falsche Quellenauffrischung |
| `rr20` | Mindestens 2,0R statt 1,5R bis zum strukturellen Ziel; keine erfundenen Zielkurse |
| `stop10` | Zeitstopp nach 10 statt 15 min ohne 0,25R Kursfortschritt |
| `risk05` | Modelliertes anfängliches Risiko 0,5 % statt 1 % pro Trade |

Insgesamt **21 vollständig isolierte 1.000-EUR-Virtual-Konten**, jedes in den mathematischen Hebel-Sensitivitäten 5×, 10× und 20×, also **63 Sensitivitäten**. Je Konto maximal 65 % eingesetzt, 3 % rechnerische Tagesverlustgrenze für neue Einstiege beim 10×-Referenzarm, 3 min Ruhezeit nach Abschluss, höchstens 100 Fallstarts. Reine Original-1m-Kerzen, daraus nur abgeschlossene 5m-Aggregate, dokumentierte Analysezeit und aktuelle genuine XAU/USD-Spotquote. Kein Echtgeld, keine künstliche Kerze, keine Zukunftsdaten. Bei beobachteter Lücke über 90s bleibt Ergebnis unentscheidbar.

Virtuelle Ein- und Ausstiege werden **erst** zum tatsächlich beobachteten neuen Gold-Spotkurs modelliert, nicht rückwirkend zum idealen Stopp. Schätzgebühren = 0,6 % des virtuellen Einsatzes plus 2 EUR Rundreise (keine verifizierte DEGIRO-Gebühr). Die mathematischen 5-/10-/20×-Spot-Proxys sind **keine echten KO-Erträge**. Erste Übersicht nach mindestens 20 vollständig beobachteten zusammenhängenden *vergleichbaren* Originalfällen je Strategie; unabhängige spätere Validierung erforderlich. Parallel getestete Regeln begründen keine automatische Siegerentscheidung.

## B. Neue verifizierte KO-Produktmodell-Kohorten `gold-ko-distance-20261119-v1`

Drei separate 1.000-EUR-Modelle mit KO-Abstand **2–3 %, 3–6 %, ab 6 %** (Bandnähe wird zusätzlich anhand der Original-Emittentenbarriere geprüft). Gleiche Marktrichtung, gleicher gültiger Stop-/Zielplan und jeweilig ein datiertes EUR-Geld-/Briefpaar aus bereits vorhandenen Produktquellen. Der tatsächliche emittentenbasierte oder nachweislich aktuelle berechnete Hebel steuert ein identisches 1-%-Risikobudget, 65 % max. Kapitalbindung und ganze Stücke, jeweils ohne Kredit. Innerhalb eines KO-Bands wird der am geringsten beobachtete Emittentenspread als **Kontrollauswahl** gewählt; Spread beeinflusst **nicht** Bobs bestehendes Produkt-Ranking.

Nur Emittenten-KO-Datum des aktuellen Handelstags, identische ISIN, Richtung, Basiswert Spot, Anbieterstatus und aktuelle Kurszeit lassen einen virtuellen Modelleinstieg zu. Die eigene verifizierte `paper_ko_guard`-Logik wird wiederverwendet. Fehlendes CHF/EUR, veraltete KO-Schwelle, unvollständiges Geld/Brief oder nicht bestätigter Hebel bedeuten **kein** Produktmodell. Keine neuen Provider-Anfragen, keine DEGIRO-Kontoautorisierung.

Ausstiege erfordern später einen neuen, überprüften **Geldkurs** desselben Produkts nach dem beobachteten Stop-/Ziel-/Zeitsignal (maximal 120 Minuten); angenommen werden 1 € Gebühr je Kauf/Verkauf plus 0,05 % Slippage je Seite. Wird das Produkt ausgeknockt oder fehlt der spätere Geldkurs, bleibt die Bewertung unbekannt; kein garantiertes Stop-Fill. Das Modell nennt **keine** ausführbare DEGIRO-Handelsfreigabe. Ein Ergebnis darf erst als beobachteter *Emittentenkurs-basierten Modellwert* bezeichnet werden, nicht als verifizierter Broker-Nettoertrag.

## C. Bestehende Referenzstudien bewahren

15 historische und laufende Papierkonten, darunter die 3.000-€-EMA- und 5.000-€-ohne-EMA-Konten, sowie bestehende Rapid- und Intraday-Varianten bleiben unverändert. Die neue Simulation wird als zwei separate begrenzte PostgreSQL-Kontrollzeilen innerhalb des vorhandenen Paper-Workers angelegt. Kein zusätzlicher Server, keine Abos, keine Orders, keine Änderungen an Live-Signal-/Push-/DEGIRO-Routinen.

## Abnahme

1. Gesamte PR-CI, Risiko- und Security-Prüfungen ohne Umgehung.
2. Nach grünem Main-SHA beide Render-Dienste `live` und derselbe Code-Commit.
3. `newStudiesBrief.shortRegime`: 21 neue, datensparsam berichtete Szenarien, 63 Mathematik-Modelle, jeweils neue Start-/Abschlusszähler und 10×-Kontowert. `newStudiesBrief.koDistance`: 3 evidenzgesperrte Originalprodukt-Kohorten, bei fehlender Emittentenquote ausdrücklich `no-timestamped-issuer-ko-pair`.
4. 15/15 bisherige Papierkonten weiter geprüft. Keiner der alten Kontostände oder Fälle zurückgesetzt.
5. Keine Gewinnbehauptung vor vollständig beobachteten Abschlüssen; keine Strategieauswahl aus historischen Backtest- oder einzelnen Modellgewinnen. Fehlende Originalquellen sind kein zulässiger Grund, Konto-/Produktnachweise zu erfinden.

**Nicht behaupten:** Die neuen Setups sind nicht identisch mit historischen früheren Tests; ihre erwartete Profitabilität ist unbekannt. Das mathematische 1-%-Stop-Risiko ist weder in Gap- noch in KO-Situationen eine Verlustgarantie.
