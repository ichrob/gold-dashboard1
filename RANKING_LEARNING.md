# Kontrollierte Rangoptimierung und spätere Alternativen

Bob untersucht die zum Messzeitpunkt freigegebenen Produkte der gespeicherten
Liste, höchstens zwölf. Dies ist keine Suche nach dem besten Produkt des ganzen
Marktes. Auch Alternativen außerhalb der angezeigten Top 3 werden eingefroren.

## Vergleich

Der bestehende Hintergrundlauf sammelt native Produktkurse etwa alle 30 Sekunden
während der Handelszeiten, auch bei geschlossener App. Feste Zwei-Stunden-Slots
verhindern überlappende 60-Minuten-Vergleiche. Der erste Datensatz eines Slots
bleibt unverändert. Je Währung werden damalige Kandidaten, Rangpunkte, bevorzugte
ISIN, Originalquelle und Zeitstempel gespeichert. Fehlende Einstiegsevidenz wird
nicht später durch günstigere Daten ersetzt.

Einstieg ist der ursprüngliche Briefkurs; Ausstieg der erste native Geldkurs
nach 60 Minuten, höchstens 60 Sekunden später. Identität, Quelle und Währung
müssen übereinstimmen. Einstieg und Ausstieg der verglichenen Produkte dürfen
jeweils höchstens 30 Sekunden auseinanderliegen. Kurslücken über 90 Sekunden
machen die Gruppe unvollständig. Nur vollständige Gruppen erhalten einen
Gewinner und einen Vorsprung gegenüber dem damals bevorzugten Produkt.

Renditen beziehen sich auf denselben rechnerischen Kapitaleinsatz, ohne
Stückzahlrundung, Mindestgebühren oder Portfolioallokation. Geld/Brief steckt
bereits im Ergebnis; weitere 0,1 und 0,3 Prozentpunkte sind explizite
Kostenszenarien. Es handelt sich um beobachtete Kursrenditen, nicht belegte
Ausführungen oder tatsächliche Nettogewinne. Ein nachträglicher Gewinner ist
keine rückwirkend verfügbare Handelsentscheidung.

## Automatische Übernahme

EUR und CHF haben getrennte Kampagnen. Zwei vorab festgelegte Varianten dürfen
nur bereits regulär freigegebene Spotprodukte derselben Währung und Richtung
umordnen: den zweiten oder dritten Rang vorziehen, sofern höchstens fünf
Risikopunkte Abstand zum ersten Rang bestehen. Risikowerte und alle
Pflichtprüfungen bleiben unverändert. Reine Simulationsfreigaben werden im
Alternativvergleich dokumentiert, liefern aber keine Lernbelege und werden
nicht automatisch umgeordnet. Future- und indikative Produkte sind ausgeschlossen.

1. 21 Kalendertage Auswahl: mindestens 60 vollständige Fälle an zehn Tagen,
   beide Richtungen mindestens zehnmal, mindestens 95 % planmäßige Datenabdeckung,
   keine unvollständigen Vergleichsgruppen, mindestens 10 % geänderte Entscheidungen.
2. Beste zulässige Variante einfrieren. Prüfung ausschließlich in den folgenden
   42 Tagen, mindestens 100 Fälle an zwanzig Tagen; gleiche Abdeckungsregeln.
3. Beide Kostenszenarien müssen positive mittlere Rendite und mindestens
   0,05 Prozentpunkte Verbesserung zeigen. Beobachteter maximaler Verlust und
   Drawdown dürfen nicht höher sein. Die untere 99-%-Bootstrap-Grenze der
   Verbesserung aus Tagesblöcken muss positiv sein. Diese empirische Grenze
   ist keine Garantie zukünftiger Rendite.
4. Erst dann wird die Rangfolge wirksam. Browser, Paper-Auswahl und serverseitige
   Push-Prüfung verwenden dieselbe Rangfunktion. Vom Browser eingereichte
   Lernregeln werden serverseitig durch den gespeicherten Prüfstand ersetzt.
5. Neue Sieben-Tage-Fenster müssen mindestens zwanzig Fälle an fünf Tagen,
   Datenabdeckung und Rendite-/Risikoverbesserung bestätigen. Andernfalls
   automatische Rücknahme. Ohne frischen Prüflauf verfällt die Nutzungsfreigabe;
   eine Überwachungslücke über einen Tag führt zur Rücknahme.
6. Abgelehnte Kampagnen beginnen nach sieben Tagen mit neuen zukünftigen Daten.
   Manuelles Pausieren bleibt bestehen; Fortsetzen startet ebenfalls neu.

Es werden keine Orders ausgelöst, Stops gelockert, Faktorprodukte aufgenommen
oder Spread-, Datenqualitäts- und Währungsrisiko-Strafpunkte eingeführt.

## Anzeige und Speicherung

Die Übersicht zeigt pro Währung Lernphase, eingefrorene Variante, Laufzeiten,
Vergleichszahl, Tage, Abdeckung, fehlende Gruppen, Verbesserung und Entscheidungen.
Die letzten 100 Vergleiche zeigen damalige Präferenz, beste Alternative,
Vorsprung in Prozentpunkten und jede ursprüngliche Kurs-/Quellenbeobachtung.
Fehlende Ergebnisse bleiben als fehlend gekennzeichnet. Pause/Fortsetzen ist
authentifiziert.

`bob_ranking_samples` bewahrt eingefrorene Gruppen und spätere Resultate auf;
`bob_ranking_state` hält die Kampagne, `bob_ranking_events` das Entscheidungsjournal.
Rohkurse verbleiben im bestehenden 30-Tage-Speicher; abgeschlossene Renditen
werden unabhängig davon gespeichert. Fälle werden erst nach 180 Tagen und nie
während ihrer laufenden Kampagne gelöscht. Tests prüfen Schutzgrenzen,
Datenlücken, getrennte zukünftige Prüfung, Rücknahme, Authentifizierung und
PostgreSQL-Persistenz. Sie ersetzen keine noch zu sammelnden Marktbelege.

## Erweiterung: Bobs tatsächliche Ausstiegslogik

Neue Vergleichsgruppen erhalten zusätzlich unabhängige virtuelle Fälle über
`paper_simulation.new_case` und `advance_case`: dieselbe Logik für ursprünglichen
Stop, Teilgewinn am Ziel, Stoppnachzug, Zielverlängerung, Richtungswechsel,
Gewinnschutz und KO-Schutz wie Bobs laufende Simulationen. Die maximale Laufzeit
ist vier Stunden bzw. 21:45 Zürich. Es handelt sich nicht um die tatsächlichen
Verkäufe des Nutzers und nicht um eine vollständige Portfolio-Simulation.

Pro Alternative stehen 100 EUR mit ganzen Stücken und ungenutztem Restgeld zur
Verfügung. Verglichen wird das Bruttoergebnis auf diese gesamten 100 EUR. Der
bestehende EUR-Simulationskursweg übernimmt CHF nur mit bestätigter Umrechnung;
die ursprünglichen Produktwährungen bleiben getrennte Gruppen. Gebühren und
Slippage bleiben unbekannt. Der eigenständige 60-Minuten-Vergleich bleibt bestehen.

Einstiege werden einmalig mit dem ursprünglichen Plan, der ursprünglichen
Kandidatenliste und den vorliegenden Kursen gespeichert. Sie werden anschließend
im bestehenden Hintergrundlauf mit aktuellen Markt- und Produktbeobachtungen
fortgeschrieben. Auch nach einem Listenwechsel werden offene Vergleichs-ISINs
weiter abgerufen. Kurslücken, Quellenwechsel, fehlender KO-Nachweis oder ungeklärte
Abrechnungen verhindern eine Gewinnerbehauptung. Eine spätere Kurserholung darf
einen unklaren Ausstieg nicht nachträglich verbessern. Die Daten liegen getrennt
in `bob_ranking_lifecycles`; vorhandene Simulationskonten bleiben unverändert.

Diese neue Auswertung ist zunächst beschreibend und wird nicht nachträglich zum
Optimierungsziel einer bereits begonnenen Lernkampagne. Die Anzeige enthält
Ausstiegsgründe, Teilverkäufe, Stop-/Zieländerungen, Stückzahl und Ergebnis.

## Erweiterung: frühere Rücknahme

Zusätzlich zur Sieben-Tage-Prüfung erfolgt höchstens einmal pro abgeschlossenem
Zürcher Kalendertag ein fest definierter Schutzcheck der letzten drei abgeschlossenen
Handelstage seit Übernahme. Rücknahme nur, wenn alle Bedingungen vorliegen:

- Mindestens zwölf vollständige und zwölf durch die Variante geänderte Vergleiche,
  an jedem der drei Tage mindestens drei vollständige Vergleiche.
- Mindestens 95 % planmäßige Datenabdeckung und keine unvollständigen Gruppen.
- In beiden Kostenszenarien an jedem Tag mindestens 0,1 Prozentpunkte schlechter
  und im Gesamtmittel mindestens 0,2 Prozentpunkte schlechter als die Grundrangfolge.
- Zusätzlich höherer beobachteter Drawdown oder schlechterer beobachteter Maximalverlust.

Dies ist eine konservative, vorab festgelegte Rücknahmeregel, kein neuer
99-%-Signifikanznachweis. Ein einzelner Verlust, ein noch laufender Tag oder
fehlende Daten lösen damit keine behauptete Renditeverschlechterung aus.
Bestehende kurze Nutzungsfreigaben und die wöchentliche Prüfung bleiben aktiv.
Grund, Zeitraum und Evidenz einer frühen Rücknahme werden dauerhaft protokolliert.

## Erweiterung: Marktphasen beim Einstieg

ADX und ATR/Gold aus dem vorhandenen technischen Kontext werden einmalig beim
Start gespeichert: ADX unter 20 = Seitwärtsphase, 20 bis unter 25 = Übergang,
ab 25 = starker Trend. ATR/Gold unter 0,1 % = niedrige, 0,1 bis unter 0,3 % =
normale, ab 0,3 % = hohe Volatilität. Dies sind feste beschreibende Kategorien,
keine optimierten Schwellen oder zusätzlichen Freigaben. Fehlende bzw. veraltete
Analysedaten ergeben „nicht bestimmbar“.

Die jüngsten 100 Gruppen werden nach Produktwährung und beiden Kategorien
aufgeteilt, jeweils mit erfassten/vollständigen Gruppen sowie mittlerer Rendite
der damaligen Präferenz und des erst rückblickend bekannten besten Produkts.
60-Minuten-Ergebnis und Bob-Ausstieg bleiben getrennt; CHF-Bob-Ausstiege sind
EUR-Simulationsergebnisse. Alte Gruppen ohne Phasenlabel werden nicht nachträglich
umetikettiert. Daraus entstehen keine eigenständigen Regeln je Marktphase.

Die mobile Anzeige enthält höchstens 100 Ausstiegsgruppen, Einzeldetails der
jüngsten 20 Gruppen und jeweils die letzten 20 Ereignisse. Kürzungen sind
gekennzeichnet; die gespeicherte vollständige Ereignisfolge bleibt erhalten.
