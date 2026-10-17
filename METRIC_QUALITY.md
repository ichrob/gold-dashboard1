# Kennzahlenprüfung in Bob

Die Prüfung läuft mit dem vorhandenen Hintergrundlauf auch ohne geöffnete App.
Sie unterscheidet Rechenkorrektheit, Übereinstimmung mit Originalbeobachtungen
und spätere Ergebnisqualität. Keine dieser Ebenen allein beweist profitable Signale.

| Kennzahl | Prüfung | Automatische Änderung |
| --- | --- | --- |
| Originalkurs, ISIN, Währung, Kursseite, Produktbedingungen | Bestehender Quellen- und Identitätsabgleich; originale Zeitstempel bleiben erhalten | Keine Änderung von Originaldaten |
| EMA 20/50/200, RSI, MACD, Signal, Histogramm | Unabhängige Decimal-Nachrechnung der tatsächlich verwendeten geschlossenen OHLC | Feste Definition, keine statistische Optimierung |
| ATR | Arithmetischer Mittelwert der letzten 14 True Ranges; ausdrücklich kein Wilder-ATR | Feste Definition |
| ADX, +DI, −DI | Unabhängige Wilder-Nachrechnung je tatsächlich verwendetem Zeitrahmen | Kennzahl fest; begrenzte Einstiegsfilter separat prospektiv geprüft |
| Modellkurs | Zeitgleicher nativer Geldkurs derselben ISIN, Währung und Quelle; Anker selbst ausgeschlossen | Begrenzte Kurskorrektur für die Modellanzeige nach späterer Prüfung |
| Berechneter Hebel | Unabhängige Arithmetik aus datierten Gold-, FX-, Ratio- und Briefkursdaten | Kein Manipulieren des berechneten Wertes |
| Hebel gegenüber Emittent | Nur datierter nicht geschätzter Emittentenhebel mit ausdrücklich gleicher Briefkursbasis | Ohne diese Angaben bleibt der Vergleich offen |
| Beobachtete Hebelwirkung | Spätere Geldkursbewegung / Goldbewegung, nur ab 0,05 % Goldbewegung | Diagnose; FX und Aufgeld wirken mit, nicht identisch mit Emittentenhebel |
| KO-Abstand | Unabhängige Nachrechnung, Toleranz entsprechend der Anzeige-Rundung | Keine Änderung der KO-Grenze oder Sicherheitsregeln |
| Produkt-Stop und -Ziel | Unveränderlicher Goldplan, vorab modellierte Produktniveaus; später beobachteter nativer Geldkurs beim Gold-Treffer | Keine automatische Lockerung bestehender Stops oder Verlustlimits |
| Signalrichtung und Markt-Score | Bestehende unveränderliche Entscheidungsprotokolle, 15/60/240-Minuten-Ergebnisse, getrennte Varianten und Kostenannahmen | Bestehende kontrollierte ADX-Filterkampagne; Score ist keine Wahrscheinlichkeit |
| Produktrangfolge | Gleichzeitig eingefrorene Alternativen, späterer Geldkurs gegenüber Einstiegs-Briefkurs, nur vollständige gleichwährende Gruppen | Keine Freigabe aus unvollständiger Statistik; begrenzte prospektive Rangoptimierung gemäß RANKING_LEARNING.md |
| Laufendes Ergebnis | Modell-Geldkurs und Original-Geldkurs jeweils gegen eingetragenen Kaufkurs × Stückzahl | Nur Preis-Modellanzeige kann korrigiert werden; kein behaupteter Nettogewinn |
| Realisierte Nettorendite | Bestehendes Journal: Kauf/Verkauf, Stückzahl und belegte Kosten; Simulation getrennt | Keine erfundenen Ausführungen oder fehlenden Gebühren |

## Dauerhafte Daten

`bob_metric_checks` speichert Rechenvergleich, Eingabe-Hash, Zeitrahmen,
Quellenzeit und Fehler unveränderlich je Kerze bzw. Produkt-Zeitpunkt. Neue
Messungen überschreiben alte Fehler nicht. Die Anzeige nennt Vergleichszahl,
fehlende Werte, Abweichungszahl, MAE, Maximum und letzte Messung. Veraltete
Prüfungen werden nicht als aktuelle Bestätigung dargestellt.

`bob_precision_quotes` sammelt native Produktquotierungen. In
`bob_precision_cases` liegen eingefrorene Pläne und Rangfolgen aus festen,
nicht überlappenden Zwei-Stunden-Kohorten. Ersterfassung ist endgültig, auch
wenn einzelne Alternativen später fehlen. Nach einer Stunde wird nur ein
Folgekurs innerhalb von 60 Sekunden angenommen. Pläne werden maximal vier
Stunden geprüft; eine Lücke über 90 Sekunden macht die Reihenfolge von
Stop-/Zieltreffern ungewiss. Quellen-, ISIN- oder Währungswechsel werden nicht
zusammengefügt. Die Auswertung ist keine Ausführungsbestätigung.

Die Kostenannahmen von 0,1 % und 0,3 % im Produktvergleich sind zusätzliche
Rundlauf-Szenarien; der beobachtete Geld/Brief-Unterschied steckt bereits in
der Rendite. Gebühren, Slippage und Finanzierung bleiben ohne Belege unbekannt.
Falldetails und Quotierungen werden 30 Tage aufbewahrt; Anzeigegrenzen stehen
im Bericht. Es gibt keine nachträgliche Rekonstruktion fehlender Kurse.

## Automatische Kurskorrektur

`precision_learning.py` verwendet genau einen begrenzten Kandidaten: den
Median der relativen Modellabweichung. Identität: Modellversion, ISIN,
Währung, Geldseite, Quelle, Richtung, Ratio, Strike und KO. Aktive Trades
einschließlich ihres Modellankers bleiben von Listenmodellen getrennt.

1. 30 verschiedene Minuten bilden die Auswahl, höchstens ±3 % Korrektur.
2. Kandidat einfrieren; erst danach 60 neue Minutenwerte prüfen.
3. Mindestens 10 % geringerer mittlerer absoluter Fehler, kein höherer
   Maximalfehler und positive untere 99-%-Bootstrap-Grenze der Verbesserung
   aus mindestens zwölf Fünf-Minuten-Blöcken. Dies ist ein begrenzter
   empirischer Test, keine Garantie künftiger Genauigkeit.
4. Übernahme nur für die aktuelle indikative Modellanzeige. Rohhistorie,
   Originalkurse, gespeicherte Stops/Ziele, Ranking und Orders bleiben unberührt.
5. Je 20 neue Minutenwerte prüfen; bei fehlendem Vorteil Korrektur zurücknehmen.
   Eine Datenlücke über zwei Minuten setzt die Auswahl zurück. Ohne frische
   Prüfdaten verfällt die Verwendung nach zwei Minuten.
6. Verwerfung/Rücknahme: 30 Minuten Pause, danach neue ungenutzte Daten.
   Manuelle Pause ist dauerhaft; Fortsetzen startet eine neue Auswahl.

Phasen und Entscheidungen liegen dauerhaft in `bob_precision_learning` und
`bob_precision_events`. Die Übersicht unter „Qualität aller Kennzahlen“ und
die Produktprüfung zeigen den Stand. Die Handelszeiten und der vorhandene
30-Sekunden-Hintergrundlauf bleiben maßgeblich; ohne Originalkurse gibt es
keinen Genauigkeitsnachweis und keine Freigabe einer Korrektur.

## Technische Validierung

Tests prüfen die unabhängige Referenz gegen Bobs echte JavaScript-Funktionen,
gezielte Rechenfehler, fehlende/ungültige OHLC, getrennte Auswahl und Holdout,
Verschlechterung und Rücknahme, Quellen-/Währungsisolation, Kurslücken,
Kostenannahmen, Authentifizierung und dauerhafte PostgreSQL-Speicherung.
Programmtests ersetzen keine über Handelszeiten gesammelten Marktbelege.
