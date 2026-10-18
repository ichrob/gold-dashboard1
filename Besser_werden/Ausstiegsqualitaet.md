# Ausstiegsqualität – Prüfkonzept

Protokoll exit-quality-v1-20261019, festgelegt vor der Erfassung am 19. Oktober 2026 um 08:00 Schweizer Zeit.

Ein Fall je aktivem Trade beginnt am ersten geeigneten Original-Geld-/Briefkurs. ISIN, native EUR-/CHF-Währung, Quelle, Modellbasis, Originalzeit und damalige FX-Basis bleiben fest zugeordnet. Bereits vergangene Käufe werden nicht als neue Einstiege rekonstruiert. Ein fehlender oder unpassender Stopp-/Zielplan erzeugt keinen erfundenen Testfall.

## Vorab festgelegter Vergleich

Der aktuelle Goldplan wird mit der zeitgleichen Produktmodell-/FX-Basis in Produkt-Stopp und Produkt-Ziel umgerechnet. Das sind berechnete Vorschläge, keine bestätigten Brokerorders.

- Basis: fester Stopp und festes Ziel.
- Variante: gleiches Ziel, nach einem Gewinn von 1R einen Stopp mit Abstand 1R zum bis dahin beobachteten Hoch nachziehen. R ist Briefkurs am Teststart minus Anfangsstopp. Ein Stopp wird nie gelockert.
- Beobachtung: 60 Minuten, Original-Geldkurse etwa alle 30 Sekunden.
- Hypothetischer Einstieg: ursprünglicher Briefkurs. Ausstiegsreferenz: erster beobachteter Geldkurs nach Stopp-/Zielberührung, sonst Geldkurs am Endpunkt. Keine Annahme einer Ausführung genau am Stopplevel.
- Zusätzliche Kostenannahmen: 0,10 und 0,30 Prozent. Geld-/Briefunterschied ist bereits durch die verwendeten Kursseiten enthalten. Tatsächliche Gebühren und Slippage werden damit nicht bestätigt.

## Befunde und Grenzen

Angezeigt werden beobachtete Erholung nach Stoppberührung, Rücklauf nach Zielberührung und Rückgabe vom beobachteten Hoch bis zum Endpunkt. Eine Erholung beweist nicht, dass ein Stopp falsch war.

Ein Kostenvergleich braucht mindestens 95 Prozent Abdeckung der 30-Sekunden-Quellenzeitfenster, keine Lücke über 90 Sekunden, einen Endkurs innerhalb von 90 Sekunden nach Ablauf und keine widersprüchliche Quelle/Modellbasis. Sonst bleibt er offen. Auch bei ausreichender Abdeckung sind Intrabar-Bewegungen und tatsächliche Ausführungen nicht belegt.

Die vorhandene Hintergrundversorgung wird genutzt; keine zusätzlichen Kursabfragen. Wird der echte Trade vorzeitig geschlossen oder fehlt die Kursversorgung, bleiben die fehlenden Folgepunkte offen. Es werden keine Originalkurse erfunden. Maximal 123 Stichproben pro Fall; die Übersicht zeigt die letzten 30 Fälle, gespeicherte Fälle bleiben erhalten.

Aktive Stopps, Ziele, Risiko-/KO-Regeln, Orders und Benachrichtigungen werden nicht verändert. Einzelfälle sind beschreibende Forschung; eine automatische Strategieübernahme findet nicht statt.
