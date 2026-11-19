# Prospektive Gold-Kurzstudie: 1m-Impuls nur mit vorheriger Richtungsbestätigung

**Start:** erst beim ersten tatsächlichen Produktions-Worker-Tick nach vollständiger CI und Render-Rollout. Keine rückdatierten Fills, keine echten Orders.

## Ausgangslage und auswertbare Erkenntnisse

Beim letzten privaten Bob-Read-only-Stand am 19.11.2026 wurden `fast1m-impulse` nach 7 Modellabschlüssen mit −6,893 % beim 10×-Spot-Proxy, `fast1m-rebound` nach 6 Abschlüssen mit −6,896 % und `fast3m-breakout` nach 9 Abschlüssen mit −6,656 % gemeldet. Die drei schnelleren Ausstiegsarme blieben ebenfalls unter null. Bei `fast1m-impulse-exit10` entfielen 4 von 10 Abschlüssen auf `no-progress`, 4 auf `stop-observed`, 2 auf `target-observed`. Das ist **nur Hypothesengenerierung**, kein Nachweis, dass ein bestimmter Filter die Verluste künftig verhindern wird. Alle Rapid-Erträge sind Spothebel-Proxys mit unterstellten Kosten.

Die 3.000-€-EMA- und 5.000-€-ohne-EMA-Eurokonten haben erst sehr wenige vollständig auswertbare Modelle und liefern keine robuste Bestätigung. Deshalb werden sie **nicht** verändert oder neu gestartet. Die laufenden Frühwarn- und Zwei-5m-Eurokonten werden weiter beobachtet, nicht zurückgesetzt.

## Neue unabhängige Forschungsvariante

**`fast1m-impulse-prev1m`** ist ein neues, separates virtuelles 1.000-€-Schattenkonto mit den bereits genutzten sieben mathematischen Hebelsensitivitäten 3×, 5×, 8×, 10×, 15×, 20×, 30×. Das bisherige `fast1m-impulse`-Setup ist die Vergleichsbasis.

- Zuerst muss das bereits bestehende 1m-Impulssignal (geschlossen, kohärent und original) vorliegen.
- Die **unmittelbar vorherige, bereits geschlossene Original-1m-Kerze** muss dieselbe LONG-/SHORT-Richtung haben, einen Kerzenkörper von mindestens **0,35 ATR1** aufweisen und gegenüber dem vorherigen Schluss bereits einen Richtungsfortschritt machen.
- Falls die zusätzliche Bestätigung fehlt, lautet der neue Blockgrund `no-prior-1m-confirmation`; nur dieses eine neue Schattenkonto bleibt ohne Einstieg.
- Bei vorhandenem Signal erfolgen Berechnung des Einstiegs aus der **jetzt tatsächlich beobachteten frischen Spotquote**, derselbe anfängliche Stopp, dieselbe Struktur, dasselbe 1,4R-Ziel, dasselbe Sechs-Minuten-No-Progress-Limit und dieselbe 20-Minuten-Maximalhaltezeit wie beim ursprünglichen Impuls-Kontrollarm.
- Alle bisherigen Schutzmechanismen bleiben: maximal 65 % modellierte Kapitalbindung, rechnerisch 1 % anfängliches Risiko pro Trade bei idealer Stopausführung, 3 % Tagesverlustgrenze für neue Einstiege, 3 Minuten Wiedereinstiegspause, Originaldaten-/Quellenzeitprüfung und keine rückwirkende Ausführung. Beide Varianten haben dieselben **hypothetischen** Rundreisekosten von 0,6 % plus 2 €. Stopps werden nur beim nächsten tatsächlich beobachteten Kurs ausgeführt.
- Alle zehn bisherigen Studienarme und 15 klassischen EUR-Papierkonten behalten ihren Zustand. Durch `setdefault` kommt die neue Variante mit leerer Historie dazu, insgesamt **11 unabhängige Schnellstudienarme bzw. 77 Leverage-Sensitivitäten**.

## Auswertung und Abnahme

1. GitHub CI einschließlich der 4.000+ Regressionstests, Risiko/Sicherheit prüfen und erst bei grün nach `main` mergen; beide Render-Dienste müssen den Merge-Commit als `live` melden.
2. `newStudiesBrief.rapid` zeigt 11 Setups / 77 Hebelsensitivitäten, neue `pairedControl`- und `entryFilter`-Kennung, jeweils Quellenzeit, Start-/Abschlusszähler, beobachteten Ausstiegsgrund, mittlere beobachtete R und mathematischen 10×-Renditestand.
3. Nur Prospektivfälle gegen dieselben ursprünglichen Signalkerzen vergleichen, bei denen **tatsächlich beide unabhängigen Kohorten** zur gleichen Zeit einsteigen konnten. Nicht vergleichbare Fälle (Kontrollarm bereits offen, Cooldown, Tageslimit, fehlende Quelle) separat melden; kein scheinbarer Paarvergleich.
4. Erst nach mindestens **20 vollständigen, tatsächlich vergleichbaren Originalfällen** und einem separaten späteren Validierungsfenster Netto-Modellerwartung, Stop-Häufigkeit, Max-Drawdown, fehlende Nachweise und Kostenrobustheit bewerten. Keine Strategieübernahme, Echtgeldorder oder Knock-out-Nettoertragsbehauptung aus simulierten Spot-Proxys.

**Betrieb:** Kein neuer kostenpflichtiger Dienst, keine neue Datenquelle, kein zusätzliches periodisches Modell – Auswertung im bestehenden Paper-Study-Worker. Kein Autotrading.
