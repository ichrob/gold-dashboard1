# Kerzenbild: kontrollierter Testbetrieb

`candle_shadow.py` ergänzt `/api/live` um `candleShadow`. Ein einklappbarer
Testbereich erscheint im bestehenden Marktstruktur-Block. Er verändert weder
Marktscore noch Produktauswahl, Ranking, KO-Prüfung oder Push. Alle bestehenden
Sperren bleiben verbindlich. Faktorprodukte bleiben ausgeschlossen; Spread wird
nicht als Rankinggewicht hinzugefügt.

## Daten und Hypothese v1

- 1m, 5m, 15m, 30m und 1h werden separat betrachtet. Quelle aus jeder Kerze: XAU/USD
  oder GC=F. GC=F ist eine Futures-Referenz ohne Nachweis eines konkreten Kontrakts;
  sie wird nicht als GCZ26 oder Spot deklariert.
- Mindestens 21 geschlossene, zusammenhängende Kerzen desselben Instruments.
  Keine Schätzwerte, Lücken, vermischten Quellen, ungültigen OHLC, doppelten oder
  zukünftigen Zeitstempel. Neueste Kerze höchstens eine Periodenlänge seit Schluss.
- Unterstützung/Widerstand: Extremwerte der 20 vorangegangenen Kerzen.
  ATR: 14 vorangegangene True Ranges, ohne aktuelle Signalkerze.
- Gerichteter Hinweis: Docht mindestens 55%, Körper höchstens 35% der Spanne,
  Schluss in obersten/untersten 30%, Dochtende höchstens 0,25 ATR von der
  entsprechenden vorherigen Preiszone; Schluss wieder innerhalb der Zone.
  Kerzenspanne mindestens 0,5 ATR. Beidseitige Dochte bleiben neutral.
- Das sind vorläufig festgelegte Testregeln, keine wissenschaftlich kalibrierten
  Wahrscheinlichkeiten. Fibonacci und Momentum werden nicht erneut gewichtet.
  Der Vergleich zur bestehenden MTF-Richtung ist lediglich Kontext.

## Protokoll und Prüfung

30m entsteht aus jeweils sechs lückenlosen 5m-Kerzen desselben Instruments.
Unvollständige Gruppen werden nicht ergänzt. Die Stundenrichtung bleibt bestehen;
30m liefert nur zusätzlichen Testkontext. Für den Richtungsvergleich sind mindestens
100 abgeschlossene 30m-Kerzen nötig; die Dochtbeobachtung benötigt 21.

Beim regulären Aufbau des Live-Bundles schreibt Bob pro neu beobachteter Kerze
einen JSON-Datensatz mit Präfix `BOB_CANDLE_SHADOW` ins Serverlog. Das geschieht
auch ohne geöffneten Kerzenbereich, wenn die bestehenden Abrufe laufen. Es wird
kein neuer kostenpflichtiger Dienst oder Zeitplan eingerichtet.
Die Duplikatkontrolle ist auf 4096 Einträge pro Prozess begrenzt. Serverlogs
unterliegen der vorhandenen Aufbewahrung; dies ist **kein dauerhaftes Archiv**.
Ein Neustart kann erneut dieselbe Kerze protokollieren. Die Offline-Auswertung
entfernt Duplikate. Für längere Studien müssen Logs und Original-OHLC gesichert
werden. Fehlende Daten dürfen nicht durch Schätzungen ersetzt werden.

`candle_study.py` vergleicht eingefrorene MTF-Richtungen mit einer hypothetischen
Variante, die nur gegenläufige Kerzenhinweise aussortiert. Input enthält
`observations` (JSON aus Logs) und `bars_by_tf` (Original-OHLC). Ein vorab gewählter
Testbeginn ist Pflicht. Einstieg erst an der ersten Kerzenöffnung nach Erfassung;
Auswertung nach drei Kerzen, keine überlappenden Beobachtungen je Zeitebene.
Kosten sind als vollständige Hin-/Rückweg-Annahme in Basispunkten übergebbar und
werden im Ergebnis ausgewiesen, ohne das Produktranking zu verändern.

Beispiel: `python candle_study.py study.json --test-from-ms 1791151200000 --cost-bps 0`

Ausgabe: Anzahl, mittlere Bewegung nach Kostenannahme, Anteil positiver Ergebnisse
sowie aussortierte positive und nichtpositive Fälle. Null bedeutet hier keine
angenommenen Kosten, nicht nachgewiesene Kostenfreiheit.
Dies ist eine explorative Richtungsstudie, kein vollständiger Bob-/DEGIRO-Backtest:
Hebel, KO-Pfad, echte Ausführung, vollständiger Marktscore und Produktfreigaben
sind nicht abgebildet. Noch kein nachgewiesener Zusatznutzen und keine automatische
Aktivierung nach einer bestimmten Trefferquote. Vor einer späteren Freigabewirkung
sind unabhängige Testzeiträume, ausreichend viele Fälle und eine vollständige
Strategieprüfung einschließlich verpasster Chancen und Verlustverteilung nötig.

## Tests

`python -m unittest test_candle_shadow.py test_candle_study.py`

Die Tests verwenden synthetische Daten und belegen technische Regeln, keine
Vorhersagequalität. Der Server kapselt Fehler dieses Moduls, damit die bestehende
Live-Pipeline weiterarbeiten kann.

## Frühe Hinweise 1m/5m und 30m/1h

Die Offline-Ausgabe `earlyHints` prüft verifizierte Docht-Hinweise, während die
zuletzt verfügbare größere Zeitebene noch nicht dieselbe Richtung zeigt.
Einstieg frühestens zur nächsten verfügbaren Kerzenöffnung nach Erfassung.
Folgeverlauf: 15 Minuten für 1m/5m, 180 Minuten für 30m/1h. Keine überlappenden
Fälle innerhalb eines Paars. Fehlende Kontext- oder Folgedaten werden separat
gezählt. Positive und nichtpositive Bewegungen berücksichtigen die übergebene
Kostenannahme; nichtpositiv ist nur ein Fehlstart-Proxy, kein realer Stop-Test.
Zeitvorsprung wird nur zu tatsächlich später protokollierter gleicher Richtung
ermittelt. Fehlende Bestätigung beweist keinen Fehlstart. Die unterschiedlichen
Zeithorizonte erlauben keinen direkten Leistungsvergleich der Paare. Die Studie
ersetzt keinen vollständigen Strategievergleich mit Trendteilnahme, Stop-Pfad,
verpassten Chancen und Produktkosten. Ohne geeignete Archivdaten steht ausdrücklich
„noch keine auswertbaren Fälle“. Keine automatische Freigabe.
