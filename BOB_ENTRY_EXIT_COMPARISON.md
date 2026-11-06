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

## Vergleichsbericht und Tests & Lernen (Erweiterung 05.11.2026)

Der bestehende 200-Episoden-Kurzbericht bleibt kompatibel. Zusätzlich wertet
`paper_comparison_report.py` den gesamten **aktuell in der Originaltabelle
vorhandenen** Bestand in einer einzigen SELECT-Snapshot-Sicht aus. Ein benannter
Cursor überträgt nur benötigte Felder in 32er-Paketen. Keine Kurse nachladen,
Originale ändern oder Ergebnisjournal duplizieren. 700-ms-SQL-Grenze, zwei Sekunden
Verarbeitungsbudget und höchstens 80 Regel-/Phasen-/Marktgruppen; bei Überschreitung
ist die Auswertung ausdrücklich nicht verfügbar, niemals ein Teilbestand als
vollständig ausgewiesen. Externe Archive und lückenlose ursprüngliche Erfassung
sind damit nicht bestätigt. Vor einer künftigen Auslagerung dieser Tabelle muss
deren geprüfter Archivleser in die Auswertung integriert werden.

33 vorab definierte Paarungen vergleichen Ausstiege, Einstiegsmethoden und
Verzögerungen. Nur zwei belegte abgeschlossene Varianten derselben Episode
zählen. Beim Ausstiegsvergleich müssen zusätzlich Produkt, Kurszeit, Preis,
Stückzahl, Abbuchung und Einstiegszeit identisch sein. Abweichende Produktwahl bei
Einstiegs-/Verzögerungsvergleichen wird gezählt. Fehlende, offene, nicht bewertbare
und nicht eingestiegene Varianten bleiben separat sichtbar, nicht Nullrenditen.
Es bleibt eine bedingte Auswertung vollständiger Paare, kein Nachweis eines
Vorteils für alle Gelegenheiten. Gleicher Einsatz ist weiterhin nicht gleiches
Risiko; keine Änderung an den laufenden 18 Varianten.

Regelversionen werden getrennt. Aus dem frühesten gespeicherten Episodenbeginn
je Regelversion werden die ersten zehn Schweizer Wochentage als Erkundung
zugeordnet, danach Validierung (keine behauptete Börsenfeiertagsabdeckung).
Marktphasen verwenden ausschließlich die ursprünglichen Labels beim Episodenstart;
keine rückblickende Neuklassifikation. Unbekannt bleibt eine eigene Gruppe.
Die Anzeige bietet Phase/Marktlage und feste Paarung zur Auswahl, keine nach
Gewinn sortierte Siegerliste. Sie zeigt gemeinsame Fallzahl, Ausschlüsse,
Netto-Modellsummen/Mittelwerte, Verlusthäufigkeit/-mittel/-extreme,
Standardabweichung und beobachtete Zwischengewinne/-verluste sowie Gewinnrückgabe.
100 Paare sind nur ein Mindestziel; mindestens zehn Validierungstage, mehrere
Vergleiche, Abhängigkeiten und Auswahl durch Datenlücken erfordern weiterhin
eine unabhängige Abnahme. Kein bestätigter Strategievorteil, keine automatische
Regelübernahme und kein Portfolio-Drawdown aus unabhängigen Episoden.

## Eingangsdiagnose

Die Originalprüfung verwendet die vom Auswerter ausdrücklich benannte
5m-Bestätigung (five-minute-confirmation / two-minute-follow-through-v1),
sonst weiterhin 15m. Quellenidentität, Frische und abgeschlossene unveränderte
Kerzen bleiben Pflicht. Ein einzelner überschreibbarer Statusdatensatz belegt
den letzten erfolgreichen Worker-Prüftakt samt Originalprüfung und Wartegrund,
auch ohne Episode. Er ist im geprüften Backupumfang enthalten. Kein historischer
Ticknachweis und kein Beleg für einen Produkteinstieg.

## Vollständige Kurzstatistik aller lokal gespeicherten Fälle

Die ältere `paper_entry_exit_comparison.report`-Übersicht darf keine
200-Fälle-Grenze als Gesamt-Evaluation ausgeben. Ihr SQL zählt nun **alle**
gespeicherten Episoden und gruppiert alle 18 Varianten nur nach Status und
modelliertem Nettoergebnis. Die umfangreichen Original-Quotes,
Triggerkerzen, KO-/Stop-Belege bleiben in PostgreSQL beziehungsweise
gegebenenfalls hinter geprüften Cold-Referenzen; die Kurzstatistik lädt sie
nicht in den Arbeitsspeicher. Die eigenständige, gruppen- und paarbezogene
`paper_comparison_report.report`-Auswertung behält ihren bestehenden
vollständigen Streaming-Reader. Eine zeitlich begrenzte oder fehlerhafte
Datenbankabfrage darf nicht stillschweigend auf 200 jüngste Fälle
zurückfallen.

`episodesSampled` umfasst jetzt alle lokal gespeicherten Zeilen;
`truncated=false` bedeutet nur, dass die Kurzstatistik keine Anzeigegrenze
mehr besitzt, **nicht**, dass alle historischen Originale unabhängig
restauriert wurden. `sourceScope=all-retained-sql-episodes` trennt das
vom vollständigen Archiv-Replay. Fehlt bei einem geschlossenen Fall ein
numerisches `modelNetEur`, werden `closedModelNetUnknown` und die
unvollständige Fallabdeckung sichtbar, ohne daraus 0 Euro oder
Brokergewinne zu erfinden. Gemischte lokale und archivierte Episoden
behalten ihre kleinen Ergebnisfelder lokal.

