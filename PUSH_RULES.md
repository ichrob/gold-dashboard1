# Bob: Push-Auslöser und Nachweis

## Schalter
Marktsignale steuert Markt- und servergeprüfte Produktmeldungen. Trade-Push setzt zusätzlich einen als aktiv gespeicherten Trade voraus. Testmeldungen sind ausdrücklich TEST und benötigen keinen aktiven Trade. Push-Berechtigung und Geräteanmeldung bleiben erforderlich.

## Auslöser
- Browser-Marktsignal: Score mindestens 70 und MTF LONG oder höchstens 30 und MTF SHORT, fertige Analyse, kein erkannter falscher Ausbruch. Meldung bei Richtungsänderung; getrennte MTF-Meldung bei MTF-Änderung. UNKNOWN beim Ausbruchfilter ist im bestehenden Modell zulässig.
- Produkt: gemeinsame Auswahlregeln werden serverseitig erneut geprüft. Keine erzwungene Top 3. Unveränderte ISIN/Richtung/Basiswert-Kombination erzeugt keine Wiederholung. Rücknahme einmalig; erneute gleiche Freigabe frühestens nach fünf Minuten. Prüfung und Gültigkeitsende sind keine Kurszeit. Kurszeit und Schätzung werden gesondert genannt.
- Stop: LONG bei Kurs <= Stop; SHORT bei Kurs >= Stop. Annäherung innerhalb max(0,25 ATR, 1 USD). Warnung beim Wechsel zwischen normal, nahe und erreicht sowie neuem Stop/Trade; keine zeitgesteuerte Wiederholung. Ein fehlgeschlagener Versand verbraucht den lokalen Übergang nicht.
- Fibonacci im Hintergrund: festgehaltene Level, passender Basiswert, abgeschlossene Kerze, tatsächliche Kreuzung. Gleichzeitige Kreuzungen werden gebündelt. Keine nachträglich behaupteten Kreuzungen über Datenlücken.
- Datenstatus: fehlende oder mehr als zwei Kerzenintervalle alte passende Kerzen lösen einmalig eine Einschränkung aus. Rückkehr aktueller Kerzen löst einmalig einen Wiederaufnahmehinweis aus, keine Trade-Entwarnung. Berechnungen werden dadurch nicht abgeschaltet.
- Gewinnschutz/Ziel/Richtungsumkehr: bestehende Modelle bleiben erhalten. Keine automatische Orderausführung.

## Zustellung
Der Service Worker unterdrückt Trade-Pushs nach lokalem Ausschalten/Schließen und abgelaufene Produktfreigaben. Serverüberwachung läuft unabhängig von der geöffneten App, solange die kostenlosen Dienste erreichbar sind. Stop, Stop-Nachziehen, Ziel, Gewinnschutz (1R/1,5R/2R), Momentum-Abschwächung, Richtungswechsel, Marktsignale und gespeicherte Produktauswahl laufen nach bestätigter Synchronisierung auf dem Server. Der Browser unterdrückt dann seine automatischen Meldungen. Die Analyse verwendet dieselbe Dashboard-Funktion. Produktnachweise behalten ihre Originalzeit und können ablaufen; eine erneute Prüfung macht sie nicht frisch. Ein vollständiger Ausfall des Pushdienstes kann nicht über denselben Dienst gemeldet werden.

## Hintergrund aktivieren und testen
Bob einmal neu laden. Push-Schalter aktivieren und auf „Hintergrund-Push gespeichert“ achten. Beim aktiven Trade werden Einstieg, Anfangsrisiko, Modell-Stop, Ziel, Richtung und Basiswert mit stabiler Trade-ID gespeichert. Modell-Stops sind Empfehlungen; kein Auftrag wird bei DEGIRO geändert. Status und verschärfter Modell-Stop werden beim Öffnen synchronisiert. Neue Trades erhalten einen eigenen Zustand.

Über „Hintergrund-Push testen (30 Sekunden)“ wird eine einmalige Testnachricht in der Datenbank gespeichert. Danach App schließen und Bildschirm sperren. Der Server löst sie nach etwa 30–45 Sekunden aus. Dieser Test benötigt keinen echten Trade.

## Noch manuell nachzuweisen
Auf dem Android-Gerät je einen ausdrücklich bezeichneten Test bei offener App, geschlossener App und gesperrtem Bildschirm empfangen. Danach Trade schließen und verspätete Trade-Warnung prüfen. Ein erfolgreiches Web-Push-Provider-Acknowledgement beweist keinen sichtbaren Empfang auf dem Handy.

## Produktbezogener Trade und fortgesetztes Ziel
Unter „Mein Trade“ kann die geprüfte Ausstiegsreferenz über „Produkt-Trade überwachen / aktualisieren“ an den aktiven Trade gebunden werden. ISIN, Produktrichtung, tatsächlicher Kaufpreis, Stückzahl sowie zusammengehöriger Geld-/Gold-/FX-Nachweis werden gespeichert. Das vorhandene lineare Modell unterstützt bestätigte einfache Gold-Spot-Turbos in EUR. Für Futures, Optionsscheine oder andere Modelle wird keine unpassende Euroberechnung eingesetzt.

Stop und Ziel erscheinen in EUR je Stück, ausdrücklich berechnet. Formel: Referenz-Geldkurs + Richtung × Bezugsverhältnis × [(Gold-Szenario − Basispreis) × FX-Szenario − (Referenz-Gold − Basispreis) × Referenz-FX]. Originalzeit und Modellannahmen bleiben sichtbar. Ein Goldschwellen-Ereignis bestätigt keinen tatsächlichen DEGIRO-Verkaufskurs. KO und nichtpositive Modellkurse liefern keine Eurozahl. R bleibt das anfängliche Risiko des technischen Goldplans; es ist nicht der tatsächliche Eurogewinn. Eine Abschwächungs-Gewinnwarnung setzt bei verbundenem Produkt zusätzlich einen positiven modellierten Gewinn gegenüber dem Kaufkurs voraus.

Nach Erreichen des bisherigen Ziels darf der Server ein weiter entferntes Ziel vorschlagen, wenn aktuelle Analyse, Richtung, MTF und MACD die Fortsetzung bestätigen (Score LONG >=70 / SHORT <=30). Mindestabstand zum aktuellen Kurs und alten Ziel: max(0,5 Anfangsrisiko, 0,5 ATR). Je abgeschlossener Kerze höchstens eine Erweiterung. Ziel erreicht wird weiterhin gemeldet; Stopnachziehen endet nicht am ersten Ziel. Neuer Stop und neues Ziel werden dauerhaft gespeichert und beim Öffnen übernommen, ohne durch alte App-Werte zurückgesetzt zu werden. Kein Brokerauftrag wird verändert.
