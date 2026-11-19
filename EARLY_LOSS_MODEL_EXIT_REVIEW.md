# Bob: Frühwarnverluste prüfen, ohne die Referenzkonten zu verändern

## Fragestellung (19.11.2026)

Die laufenden 3.000-€-EMA- und 5.000-€-ohne-EMA-Konten zeigen bislang positive virtuelle Erträge, während die Frühwarnung (1.000 €) und der Zwei-5m-Test (1.000 €) negativ sind. Alle vier Konten bleiben **unverändert**. Die aktuellen Einstiegssperren sagen nicht automatisch, weshalb frühere Trades Verluste verursachten.

## Bestehende Datengrundlage

`paper_reflection.record` speichert beim Abschluss eines virtuellen Paper-Falls auf dem jeweiligen Kontrollkonto eine fortlaufende Zusammenfassung (`reviewed`, `evaluated`, `unpriced`, `modelLosses`, `modelNetEur`) sowie nur die letzten zwanzig bereits gespeicherten Nachbetrachtungen. Eine `reflection.costModel` verwendet **angenommene** Kosten, keine nachgewiesenen DEGIRO-Nettoausführungen. Nicht bepreiste Fälle bleiben unbekannt.

## Neue ausschließlich lesende, datensparsame Diagnose

In `push_snapshot` werden ausschließlich für `ema3000nov`, `noema5000nov`, `early1000dec` und `early5m1000nov` diese bereits gespeicherten Zähler projiziert. `paperProfitEvidence.rows[].modelExitReview` führt zusätzlich eine feldgenau bereinigte Ansicht mit:

- kumulativen Zählern der **bereits protokollierten** Modellprüfungen und Modellverluste;
- bei höchstens zwanzig vorhandenen Nachbetrachtungen: Modellverluste, Modellgewinne, unbekannte Ergebnisse, beobachtete Abschlussgründe (feste Liste: Stopp, Ziel, Zeit, Umkehr, KO-Sicherheitsausstieg usw.);
- Anzahl beobachteter Bruttogewinne, die **unter den Annahmekosten** nicht positiv geblieben sind;
- unveränderten Originalzeiten des vorliegenden Kontrollsummenstands.

Es werden **keine zusätzlichen SQL-Queries** und keine vollen Handelshistorien geladen, keine alten Fälle nachgerechnet und keine Produktidentitäten, ISINs, Kurszeiten, Einzelhandelspreise, Freitextkommentare oder Geheimnisse ausgegeben. Unvollständige, ungültige oder nicht vorhandene Nachbetrachtungen werden als solche ausgewiesen.

## Vorgehen nach dem Render-Rollout

1. Prüfen, ob beide Render-Dienste dieselbe neue Main-Revision bereitstellen und 15 von 15 Konten weiter kontrolliert werden.
2. Die vier `modelExitReview`-Summen getrennt ansehen und zwischen **beobachteten, im virtuellen Modell berechenbaren Verlusten** und unbekannten/fehlenden Fällen unterscheiden.
3. Ursachen ausschließlich aus tatsächlichen gespeicherten Ausstiegsgründen und Kosten ableiten. Keine hypothetischen Gewinner aus verpassten Einstiegssignalen erfinden. Vergleich von vier Konten ist wegen anderer Startdaten, Regeln und Stichproben **nicht** bereits kausal.
4. Nur bei hinreichendem gepaartem, datiertem Originalbeleg eigenständige neue Forschungshypothesen ableiten (z.B. früherer Schutzstopp oder Zeitlimit), niemals die bisherigen 3k-/5k-Konten still ändern.
5. Produktbezogene Nettogewinne erfordern weiterhin datierte Original-Geld-/Briefkurse, KO/FX/Gebühren und Ausführungskontext. Keine Echtgeldorders.

Die Auswertung ist Beobachtung, **kein automatischer Strategieumbau** oder Gewinnversprechen. 
