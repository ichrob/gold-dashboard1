# Produktranking nach Kosten und Risiko – Version 2 – Spread ohne Gewichtung

Die technische Marktanalyse ist weiterhin eine Zulassungsbedingung. NEUTRAL,
widersprüchliche Analyse, unvollständige Produktbedingungen und unzureichend
aktuelle Daten erzeugen keine Produktempfehlung. Der bestehende Hauptablauf
prüft ISIN, Richtung, Basiswert/Kontrakt, Ratio, Basispreis, Laufzeit, Währung,
Quanto, Barriere und datierte Geld-/Briefkurse vor der Rangfolge. Faktorprodukte
bleiben ausgeschlossen. Spot und unterschiedliche Futures werden getrennt.

Der frühere Score mischte technische Signale und grobe Risikostufen. Spread
wurde in Version 1 gewichtet. Auf ausdrücklichen Nutzerwunsch vom 03.10.2026
ist er jetzt wieder reine Information: keine Punkte, keine Spread-Sperre und
kein Einfluss auf die 5%-Kostengrenze. Jetzt verwenden Live-, Screenshot- und
bedingte Vergleiche dieselbe Kosten-Risiko-Bewertung. Der Score ist eine
konservative Auswahlregel, keine kalibrierte Gewinn- oder Verlustwahrscheinlichkeit.

## Vergleichsbasis

1.000 EUR **Produkteinsatz**, 1 Kalendertag Haltedauer. Dies ist ein einheitliches
Vergleichsszenario, keine Einsatzempfehlung und keine Prognose tatsächlicher
Kosten einer anderen Ordergröße oder Haltedauer. Quelle und Quellenzeit werden
angezeigt. In den Produktdetails lassen sich vorhandene Kostennachweise speichern:

* Kauf- und Verkaufsgebühren zusammen in EUR, einschließlich Börsen-, Abwicklungs-
  und Währungskosten, ohne Spread.
* Finanzierung in Prozent des **Produkteinsatzes pro Tag**, einschließlich
  relevanter Emittentenaufschläge. Ein jährlicher Zinssatz auf den Basiswert darf
  nicht direkt eingesetzt werden. Positive Finanzierungsgutschriften werden
  nicht als garantierter Rangvorteil modelliert.
* Passende ISIN, benannte Quelle und eindeutige Quellenzeit mit Zeitzone.

Nachweise älter als 30 Tage, zukünftige/unklare Zeiten oder Nachweise für andere
ISINs/Einsätze/Haltedauern zählen als unbekannt. Ein ausdrücklich belegter
Nullbetrag ist zulässig; leere Werte bleiben `null`. Kosten werden pro ISIN
lokal gespeichert und nicht durch einen frischen Kurs oder Screenshot erneuert.
Ein automatischer vollständiger DEGIRO-Gebührenabruf wird nicht behauptet.

## Punktregel

Start 100 Punkte; folgende Abzüge werden addiert (Rundung auf 0,1 Punkte):

| Bestandteil | Abzug |
| --- | --- |
| Spread | 0 Punkte, unabhängig von Höhe oder fehlender Spread-Angabe; nur Information |
| Handelskosten | `min(10, 5 × Kosten%)`; Kosten% = 100 × Gebühren EUR / 1.000 EUR |
| Finanzierung | `min(10, 5 × Finanzierung%)` für den Vergleichstag |
| Unbekannte Kosten | jeweils volle 10 Punkte für Handel / Finanzierung |
| KO | `min(25, max(0, (5 − Abstand%) × 5) + max(0, (3 − ATR-Abstand) × 5))` |
| Hebel | `min(15, max(0, Hebel − 5))`; höherer Hebel bringt niemals Zusatzpunkte |
| Daten | zusammen maximal 20: ATR unbekannt 5; Schätzung 5; unbestätigte Schätzgenauigkeit weitere 5; unklare/veraltete Kurszeit 10, sonst bis 5 für Alter 0–90 s; Future-Fehleranteil bis 10 |

Unbekannte Kosten erhalten mindestens denselben Abzug wie hohe bekannte Kosten
im jeweiligen Kostenbestandteil. Sie können daher keinen scheinbaren Kostenvorteil
erzeugen. Gesamtkosten bleiben `null`, wenn eine Kostenart unbekannt ist; lediglich
die bekannte Teilsumme aus Handel und Finanzierung wird für harte Grenzen
genutzt. Der Spread ist auch dort ausgeschlossen; ausgewiesene Gesamtkosten
dürfen ihn rein informativ weiterhin enthalten. Fehlende wesentliche Produktdaten werden im Hauptablauf ausgeschlossen.

Sperren: fehlender/ungültiger Kurs, Hebel, KO oder Produktrichtung;
überschrittene KO-Barriere; bekannte Handels-/Finanzierungskosten bereits über 5%;
KO-Abstand unter 1%; KO-Puffer unter 1,5 ATR; Score unter 60. Die bereits vorhandenen
strengeren technischen Eignungs- und Aktualitätsprüfungen bleiben zusätzlich aktiv.
Die Schwellen sind nachvollziehbare Sicherheitsregeln, kein empirisch optimiertes
Handelssystem.

## Futures-Schätzung

Die bestehende eigene Kontraktanalyse und mindestens 20 geeignete Vergleiche
bleiben erforderlich. Alle Kombinationen der beobachteten Basiswert-/Produktpreis-
Fehlerspanne werden bewertet; jede muss geeignet sein. Sortiert wird nach dem
schlechtesten Score. Zusätzlich muss der zentrale KO-Abstand **größer als das
Dreifache der beobachteten Future-Abweichung** sein. Dies gilt symmetrisch für Long
und Short, selbst wenn die einfache Fehlerspanne die Barriere noch nicht berührt.
Der Fehleranteil am KO-Abstand verursacht weitere Datenabzüge.

Beobachtete Abweichungen sind keine garantierten Fehlergrenzen. Die Schätzung
wird nicht in einen bestätigten Future-Kurs umbenannt. Kein automatischer Trade.

## Ausgabe und Prüfung

Die ersten drei Erklärungen nennen Kosten samt Lücken, KO/Hebel/Fehlerpuffer und
Punkteabzüge. Bei Gleichstand dient die ISIN nur der Anzeigereihenfolge. Ohne
geeignete Kandidaten steht **ABWARTEN**, mit konkretem Sperrgrund oder der Liste
fehlender Nachweise. Weniger als drei geeignete Produkte ergeben eine kürzere Liste.

`node test_cost_ranking.js` prüft unveränderte Scores und Eignung bei variierendem
oder fehlendem Spread (auch über 3%), Gebühren, Finanzierung,
belegtes Null versus unbekannt, Quellenalter, falsche ISIN/Vergleichsbasis,
Hebelmonotonie, Volatilität, KO, Future-Unsicherheit Long/Short, NEUTRAL,
vollständige Screenshot-Auswahl, Abwarten und HTML-Escaping. Bestehende Tests
für Import, BNP-Korrektur, Zeitstempel, Produktbedingungen und Auswahl bleiben
Teil der CI. Die Regressionstests verlangen ausdrücklich, dass Spread allein weder
Rangpunkte noch einen Ausschluss bewirkt. Die bestehenden Prüfungen konsistenter,
datierter Geld-/Briefkurse bleiben als Nachweisprüfung erhalten.

Goldwert-Anzeigen, Futures-Schätzalgorithmus, Datensammlung und Sieben-Tage-Archiv
werden durch diese Änderung nicht verändert.
