# Einstieg/Ausstieg: vorab festgelegter Vorwärtstest v1

Auftrag 05.11.2026. Keine Echtgeldorders, keine automatische Anpassung der
Handelssignale oder Schutzgrenzen. Neue Originaldaten ab Auslieferung, kein
rückdatierter Start und keine Rekonstruktion aus dem Wochenchart.

## Festgelegte Matrix

| Einstieg | Fester Ausgang | Beweglicher Ausgang |
| --- | --- | --- |
| Gültige bestehende Frühwarnung mit unabhängigem Stop/Zielplan | eingefrorenes Ziel und Anfangsstop | Anfangsstop, danach bestätigte 5m-Swingpunkte |
| Bestehendes bestätigtes Hauptsignal mit gültigem Plan | gleich | gleich |
| Bestätigtes Hauptsignal plus Rücksetzer/Erholung | gleich | gleich |

Jede Kombination zusätzlich mit 0/30/60 Sekunden Verzögerung bei Einstieg UND
Ausstieg: 18 Varianten. Rücksetzer LONG: Schluss der vorletzten geschlossenen
5m-Kerze unter vorherigem Schluss, danach Schluss über deren Hoch; SHORT
spiegelbildlich. Nur drei lückenlose, originale, abgeschlossene XAU/USD-Kerzen.
Der letzte Schluss muss nach Episodenbeginn liegen. Dies ist eine zu prüfende
Hypothese, keine behauptete profitable Regel.

Trailing: mittlere Kerze bildet ein tieferes Tief als ihre beiden Nachbarn
(LONG) bzw. höheres Hoch (SHORT). Erst nach Abschluss der dritten Kerze wird
der Stop angehoben/abgesenkt, niemals gelockert. Der bisherige Stop wird zuerst
geprüft. Kein festes Gewinnziel in dieser Variante. Gegenrichtung, KO-Schutz,
maximal drei Stunden Haltedauer und 21:45 Zürich beenden beide Varianten.

## Fairness und Originalnachweise

- Gemeinsame Episode und Marktphase, eine Stunde Einstiegsfenster. Maximal zwei
  laufende Episoden und eine je Richtung. Kein erzwungener Einstieg.
- Je Variante unabhängiges virtuelles Budget 1.000 EUR, davon maximal 650 EUR
  je Fall, ganze Stücke. Gleiche Notionalgrenze, **nicht** gleiches Stopprisiko;
  Unterschiede in Hebel/KO-Abstand und Produktwahl müssen bei Auswertung
  berücksichtigt werden. Kein kumulatives Portfolio und kein echter Einsatz.
- Zwei Ausstiegsarten bekommen für dieselbe Einstiegsmethode/Verzögerung denselben
  validierten Kandidaten und denselben Originalkurs. Verschiedene Einstiegszeiten
  dürfen verschiedene verfügbare Produkte haben; das wird aufgezeichnet.
- Nur bestehende Produktprüfung, Original-Spot, beobachtete EUR-Emittenten-Geld/
  Briefkurse und aktuelle KO-Nachweise. Emittentenkurse sind keine bestätigten
  DEGIRO-Fills. Aktive ISINs bleiben im vorhandenen Kursmonitor.
- Nach Verzögerung muss ein neuer Kurs vorliegen. Kein rückwirkender Fill zum
  Signalpreis oder Stopniveau. Originalkurslücken über 90 s und ungeklärter KO
  bleiben nicht auswertbar, ohne Gewinn/Verlust zu erfinden.
- Spread über Brief/Geld. Beispielkosten: 1 EUR je Seite, 0,05 % Slippage je Seite.
  Finanzierungseinfluss steckt im beobachteten Produktkurs; konkrete Brokergebühren,
  Währungsumrechnung und tatsächliche Ausführung bleiben unbestätigt. Deshalb
  modellierter Nettobetrag, keine verifizierte Nettorendite. Nur EUR-Produkte in v1.
- Entscheidung, Triggerkerzen, Entry/Exit-Kurse und Originalzeiten, Stopänderungen,
  Nicht-Einstiegsgründe, beobachteter maximaler Zwischengewinn/-verlust pro Trade
  werden gespeichert. Beobachtete Extrema sind keine lückenlose Tickhistorie.

## Auswertung vor Übernahme

Erste technische Abnahme: neue Episode, alle 18 Zustände, Verzögerungsnachweise,
belegter Ausstieg oder klarer Sperrgrund. Danach mindestens 20 Handelstage und
100 vollständige vergleichbare Episoden pro relevanter Paarung anstreben;
das sind Mindestziele, kein statistischer Beweis. Bei weniger Fällen weiter
als unzureichend kennzeichnen. Erste zehn Handelstage sind Erkundung; die
folgenden mindestens zehn getrennte Validierung. Regeln innerhalb v1 einfrieren.

Netto-Modellergebnis, Erwartungswert, Verlustverteilung, fehlende Fälle und
Gewinnrückgabe getrennt nach Marktphase, Richtung und Verzögerung vergleichen.
Nur gemeinsame vollständige Episoden für gepaarte Vergleiche, zusätzlich alle
Sperren/Lücken ausweisen, damit Ausfälle keinen künstlichen Gewinner erzeugen.
Die Diagnose zeigt eine begrenzte Stichprobe der letzten 200 Episoden und
Einzelvarianten-Summen, **keinen** fertigen gepaarten Gewinner oder Portfolio-
Drawdown. Vollständige statistische Abschlussauswertung bleibt ein gesonderter
Abnahmeschritt; automatische Strategieübernahme ist deaktiviert.

## Betrieb

Vorhandener Paper-Worker, vorhandenes 08–22-Uhr-Handelsfenster, keine zusätzlichen
Marktdatenanbieter oder Dienste. Eine kompakte Fallakte je Episode, maximal zwei
aktive Zustände; keine zusätzlichen vollständigen Kerzenkopien pro Takt.
Originalfälle werden nicht automatisch gelöscht. Fehler in diesem Vergleich
können bereits gespeicherte Hauptkonten nicht zurückrollen. Zentrale/Testübersicht
zeigt sechs Gruppen, private Simulationdiagnose die 18 Varianten.
