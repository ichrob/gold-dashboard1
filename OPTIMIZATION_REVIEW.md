# Bob: sieben Optimierungen, 16. Oktober 2026

1. **Produktnachweise:** Der bestehende nicht blockierende comdirect-Cache wird bei jedem Produktzyklus auch für Stammdaten abgeholt, selbst wenn die vier Emittentenplätze belegt sind oder noch keine Emittentenantwort vorliegt. Identität, Konflikte, Währung, Quellenzeiten und Ausschlüsse prüft weiterhin `comdirect_fields`. `fieldRecovery` im privaten Audit zeigt den Parserbefund. Ersatzquellen werden nicht zu ausführbaren Brokerkursen umdeklariert. Externe Nachweislücken sind damit nicht automatisch gelöst.
2. **Verpasste Bewegungen:** Neue Hintergrundentscheidungen speichern den Entscheidungsgrund und Varianten unveränderlich. Eine spätere Spotbewegung ab 0,15 % in 15 Minuten wird bei abweichendem Signal oder dokumentierter Sperre als Prüffall gezeigt. Eine spätere protokollierte Richtungsbestätigung liefert eine beobachtete Verzögerung, keinen Beweis des tatsächlichen Bewegungsbeginns. Produkt-/Kontosperren stehen weiterhin im Tagesprotokoll des jeweiligen Paper-Kontos; der abonnementunabhängige Marktbeobachter hat keine private Produktauswahl.
3. **Früh gegen vorsichtig:** `optimization-forward-v1` friert aktuelle Regel, drei Schlusskerzen (bestehendes shadowDirection), ergänzenden bestehenden Frühimpuls und Trendvariante gleichzeitig ein. Nur gemeinsame gültige Folgekurse zählen; Stichprobenwahl erfolgt vor Ergebnisprüfung, mit mindestens 16 Minuten Abstand. Keine nachträgliche Erzeugung von Varianten für Altentscheidungen.
4. **Marktphasen:** Die Trendvariante verwendet den bereits vorhandenen 1h-/15m-Kontext. Nur intakter, passender Trend in CONTINUATION/PULLBACK erlaubt eine Richtung. RANGE/WEAKENING warten; unbekannte Phase bleibt nicht auswertbar. Ergebnisse werden nach Phase und Zeitabschnitt getrennt. Dies ist eine festgelegte Hypothese, keine aktivierte Handelsregel.
5. **Stopps/Ausstiege:** Die Tagesprüfung fasst bestehende feste/nachgezogene Lifecycle-Modelle paarweise zusammen: Ergebnis in R, Stopptreffer und beobachtete Gewinnrückgabe. Offene/lückenhafte Fälle werden ausgeschlossen. Detailslimit 100; überlappende Planversionen sind keine unabhängigen Trades. Kein gelockerter Stop und keine Änderung an aktiver Tradeführung.
6. **Kosten:** Alle fünf Paper-Konten erhalten eine zusätzliche nachträgliche Kostensensitivität für die ausgewählten Tagesdetails (maximal 100 Fälle). Nur geschlossene, vollständig bepreiste und abgerechnete Produktfälle. Geld/Brief ist bereits im Bruttoergebnis; der Spread wird nicht doppelt abgezogen und das Ranking bleibt unverändert. Beispiel: 1 EUR pro Kauf/Teilverkauf, 5 Basispunkte schlechtere Ausführung je Seite. Belastungstest: 2 EUR, 15 Basispunkte und zusätzlich 5 Basispunkte Haltekosten pro Tag auf das volle Einstiegskapital. Dies sind ausdrücklich keine verifizierten DEGIRO-Gebühren. Tatsächliche Finanzierung und Ausführungsverzögerungen bleiben unbekannt; Zusatzkosten sind ein Stressmodell. Kontokapital, Stückzahl und Einstiegsentscheidungen bleiben unverändert. Kein behaupteter Nettogewinn und kein vollständiger Netto-Kontobacktest.
7. **Übersicht:** Lernen → Statistik zeigt gemeinsamen Vergleich, Lücken, starke Bewegungen und getrennte Marktphasen. Kostendetails sind in Vollautomatisch einklappbar. Zukunft akzeptiert jetzt auch die tatsächliche Fünf-Konten-Antwort und numerische Prüfzeitstempel.

## Prüfprotokoll

Ab 26.10.2026 (Europe/Zurich) werden neue Fälle separat als spätere Prüfung ausgewiesen. Das Datum und alle Varianten sind vor Ergebnissen festgelegt. Keine automatische Auswahl oder Übernahme. Die Darstellung verwendet das bestehende begrenzte Berichtsfenster (2500, bei Datenbanklast 500 Entscheidungen), dessen Umfang sichtbar bleibt; Datenhaltung unverändert 30 Tage. Es ist kein vollständiges Langzeitexperiment. Im Spotvergleich werden rein beispielhafte 0,04 % pro Richtungstrade abgezogen; das ist keine gehebelte Produktrendite. Fehlende Daten sind nicht Gewinn 0.

Tests: `test_optimization_review.py`, `test_ki_help_source_refresh.py`, `test_future_lab.js`, `test_dashboard.js`, gesamte bestehende CI einschließlich PostgreSQL.

## Ergänzung: Marktanalyse, 16. Oktober 2026

Alle fünf vorgeschlagenen Verbesserungen werden über das bestehende Analyse- und Vergleichssystem umgesetzt:

- Die Richtungserklärung ordnet den konkreten gespeicherten Abwartegrund verständlichen Kategorien zu und nennt den nächsten Prüfschritt. Der Originalgrund bleibt sichtbar; mehrere Ursachen können gleichzeitig gelten.
- `market-review-v1` friert neue Hintergrundfälle mit 1/5/15/30-Minuten-Folgeauswertung ein. Neue Horizonte werden nur für diesen neuen Protokolltyp erhoben. Bestehende 15/60/240-Minuten-Berichte bleiben erhalten. Keine Rückfüllung alter Modellvarianten.
- Eine starke Bewegung kann entweder 0,15 % oder eine volle, vorab bekannte 5m-ATR erreichen. ATR stammt aus der bereits geprüften geschlossenen 5m-Historie, mit eigener Schlusszeit. Fehlende ATR bleibt unbekannt. Die Schwelle ist eine Diagnosehypothese, keine neue Live-Signalregel.
- Aktuelle Regel, ergänzender Frühimpuls, vorhandener Marktphasenfilter und vorhandener Einstiegsfilter werden auf denselben Fällen je Horizont verglichen, getrennt nach Marktphase und Sammlung/Prüfung. Der Einstiegsfilter prüft bereits EMA-Abstand über 1,5 ATR, Platz unter 2R und fehlendes/über 15 Minuten altes Signal. Keine automatisch gelockerten Einstiegsregeln.
- Pro Prüffall erscheinen EMA-Abstand, Platz in R und Signalalter, soweit vorab vorhanden. Beobachtete Richtungsumkehr ist ausschließlich ein Vergleich der 1-/30-Minuten-Endpunkte, kein lückenloser Verlauf oder handelbarer Rücksetzer.

Stichproben mindestens 31 Minuten auseinander, vor Ergebnisprüfung ausgewählt. 1-Minuten-Folgekurs höchstens 30 Sekunden nach Zielzeit; sonst 60 Sekunden. Fehlende Eingänge, Varianten und Folgekurse werden ausgeschlossen, nicht als Nullgewinn gewertet. Alle Varianten werden mit ausdrücklich beispielhaften 0,04 % Spotkosten verglichen; das sind keine Produktgewinne. Ergebnisse erscheinen in Lernen → Statistik im bestehenden einklappbaren Optimierungsvergleich. Der Signalvergleich ab 26.10. bleibt getrennt; keine automatische Gewinnerauswahl oder Änderung der aktiven Handelsregeln.


## Technische Entscheidungsaufnahme — 20. Oktober 2026

Neue gültige Hintergrundentscheidungen speichern zusätzlich `decision-context-v1` aus derselben bereits ausgeführten Analyse: Zeitebene/Kerzenzeit, EMA20/50/200, RSI, MACD/Signal, Histogramm, ATR, ADX, Einstiegsprüfung, Sitzungsfreigabe und DMI-Kontext. Die Momentaufnahme enthält nur freigegebene Felder, ohne Konto- oder Zugangsdaten. Identische Aufnahmen bleiben idempotent; veränderte technische Evidenz erhält eine eigene unveränderliche Revision. Fehlende Originalwerte bleiben unbekannt; alte Entscheidungen werden nicht nachgerechnet. Lernen → Tagesprüfung zeigt die damaligen Werte. Datenhaltung und bestehende Abtastung bleiben unverändert: kein Versprechen einer lückenlosen tickweisen Vollaufzeichnung. Ungültige Ausgangskurse werden weiterhin in der Datenabdeckung dokumentiert und starten keinen Signaltest.

Der bereits vorhandene `bob-rolling-shadow-v2`-Vergleich bleibt erhalten: Kandidat und Protokoll werden vor der späteren Prüfung eingefroren. Dieselben späteren geschlossenen Kerzen, Standard-/Stresskosten und Drawdown prüfen beide Referenzstrategien. Mindestens 20 unabhängige Sitzungen und 30 Trades je Variante sind erforderlich; selbst ein positiver Referenzvergleich ersetzt keine Produktkostenprüfung und aktiviert keine Live-Regel. Am 20. Oktober war im Morgenbericht kein Kandidat mit hinreichendem historischem Vorteil vorhanden. Dies ist kein fehlgeschlagener technischer Test und kein Profitabilitätsnachweis.

## Evidence alignment (27 October 2026)

- Displayed analysis, research ranking and paper selection expose the same
  `selectedPriceSnapshot` identity, value, source and original timestamp. Paper
  cases freeze this basis at entry; observed bid/ask valuation remains separate
  and may never be replaced by a calculated fill.
- Turbo estimates have a separate `turbo-forward` measurement scope. Only a
  prediction frozen strictly before receipt of a matching original (within five
  seconds of source time) enters this scope. Retrospective shadow comparisons
  remain separate. Readiness requires the existing sample count, time span and
  freshness gates; future accuracy is not guaranteed.
- Daily evidence review separates observed positions, calculated analysis and
  unpriced cases, with entry/exit sources, frozen cost assumptions and sampled
  per-position maximum drawdown. Missing historical measurements stay unknown;
  inconclusive cases never contribute a strategy profit.
- Resolved source differences remain visible as explained differences. Explicit
  unresolved fields take precedence. A stale unused backup is informational;
  failure of the selected feed remains a warning. No issue auto-closure or new
  trading permissions are introduced.
