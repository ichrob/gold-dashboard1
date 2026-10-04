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
Der Service Worker unterdrückt Trade-Pushs nach lokalem Ausschalten/Schließen und abgelaufene Produktfreigaben. Serverüberwachung läuft unabhängig von der geöffneten App, solange die kostenlosen Dienste erreichbar sind. Lokale Stop-/Gewinnschutzmodelle benötigen die laufende App. Ein vollständiger Ausfall des Pushdienstes kann nicht über denselben Dienst gemeldet werden.

## Noch manuell nachzuweisen
Auf dem Android-Gerät je einen ausdrücklich bezeichneten Test bei offener App, geschlossener App und gesperrtem Bildschirm empfangen. Danach Trade schließen und verspätete Trade-Warnung prüfen. Ein erfolgreiches Web-Push-Provider-Acknowledgement beweist keinen sichtbaren Empfang auf dem Handy.
