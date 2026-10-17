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
