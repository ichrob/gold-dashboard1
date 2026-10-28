# Risiko: experimentelle Kurzfristansicht

Der neue Hauptreiter `Risiko` zeigt LONG, SHORT oder ABWARTEN und getrennt
VORWARNUNG/BESTÄTIGT. Er wertet denselben Spot-Snapshot und abgeschlossene
1-Minuten-Kerzen aus dem bestehenden Live-Bundle aus. Die vorhandene Hauptstrategie,
Produktfreigabe und Hintergrund-Tradeüberwachung werden nicht verändert.

## Funktionsumfang

- Originalzeit des echten XAU/USD-Spot maximal 60 Sekunden alt; keine zukünftigen
  Zeiten. 21 vollständige, zusammenhängende Minutenkerzen desselben Instruments;
  keine laufenden Kerzen, ungültigen OHLC-Werte oder Zukunftspivots.
- Experimentelle Vorwarnung aus Spot, Richtung der letzten Kerzen und 0,5 ATR.
  Bestätigung durch zwei abgeschlossene Minutenkerzen jenseits eines vorher
  bekannten Fünfkerzenniveaus plus 0,15 ATR; aktueller Spot muss bestätigen.
- Top zwei aus den bereits geladenen Produktzeilen: bestehende Identitäts-,
  Basiswert-, Faktor-, KO- und Risikoausschlüsse über `earlyWarningRanking`;
  anschließend Hebel absteigend, ISIN als stabiler Tie-Breaker. Keine Veränderung
  der vorhandenen Produktrangliste. Keine Auffüllung mit ungeeigneten Produkten.
- Preisbasis, Quellenzeit und fehlende Nachweise bleiben sichtbar. Die Rangliste
  ist ein Analysevergleich und bestätigt keine DEGIRO-Ausführung oder Freigabe.
- Tatsächlich erfasste aktive Trades aus `BobTradeSync.current()` erhalten eine
  zusätzliche Gold-Warnschwelle: bestehender Stop oder 1,5 Minuten-ATR vom besten
  seit Beobachtungsbeginn gesehenen Spot, immer die engere Grenze. Eine erreichte
  Ausstiegswarnung bleibt bis zum Ende/Wechsel des Trades erhalten. Nach fünf
  Minuten beobachteter Zeit ohne günstige Fortsetzung erfolgt eine Zeitwarnung.
- Verlauf der letzten 30 Zustandswechsel dieser Sitzung; keine Speicherung von
  privaten Produktlisten in Repository, öffentlichen Endpunkten oder Logs.

## Hintergrundbetrieb und Zustellung

`background_analysis.js` verwendet dasselbe `Risk.analyze/advance/monitor` wie
der Browser. Kein dupliziertes Python-Signalmodell. Der vorhandene Worker prüft
mit seinem bestehenden Live-Bundle (typischerweise ca. 30 Sekunden); der
Reiter verspricht keinen Sekundenstream.

Der zusätzliche Risiko-Schalter ist standardmäßig aus und wird in der bestehenden
Push-Konfiguration gespeichert. Marktvorwarnungen/Bestätigungen benötigen zusätzlich
Markt-Push und das bestehende DEGIRO-Zeitfenster. Ausstiegswarnungen benötigen
Trade-Push und einen tatsächlichen aktiven Trade mit passender ID. Testtrades lösen
keine echten Risikowarnungen aus. Der Geräteschalter blockiert auch noch wartende
Risiko-Meldungen im Service Worker und entfernt angezeigte Risiko-Mitteilungen.
Bestehende Stop-/KO-Warnungen werden separat versandt und nicht mit ausgeschaltet.

Zustände (Signal, nachgezogene Warnschwelle, deduplizierte Ankündigungen, Verlauf)
liegen in `subscriptions.background_state.risk`. Erst nach erfolgreicher
Provider-Annahme wird der Versandzustand gespeichert. Bei Teil-/Komplettfehlern
bleibt der vorherige Checkpoint bestehen. Kein Verlust einer Warnung durch
vorzeitiges Abhaken; wiederholte Zustellversuche sind bei unklarem Providerstatus
möglich. Meldungen verfallen spätestens 60 Sekunden nach der Originalkurszeit;
TTL und Service Worker prüfen die Gültigkeit. Keine Zustellzeitgarantie.

Die bestehenden signierten Push-Empfangsbelege bleiben erhalten: Provider-Annahme,
Browser-API-Akzeptanz und tatsächlicher Klick sind unterschiedliche Nachweise.
Der Reiter zeigt gespeicherte Aktivierung und letzten geprüften Serverdurchlauf;
ein gesetzter Schalter allein wird nie als erfolgreiche Überwachung dargestellt.
Beim Neuladen kann eine zum Trade passende dauerhafte Schutzgrenze übernommen
werden, ohne einen tatsächlichen Trade- oder Broker-Stop zu ändern.

## Grenzen

Kein neuer Datenanbieter, keine garantierten Sekundenkurse, keine Brokerorders.
Veraltete Daten sperren Richtung und Rangliste. Fehlende Minutenhistorie wird nicht
mit 5m-/Future-Daten ersetzt. Regeln/ATR-Faktoren sind Forschungsparameter.

Noch offen: unabhängige Simulationen mit echten Produkt-Geld-/Briefkursen,
Kosten und gemessener Nutzerreaktionszeit sowie Nachweis der tatsächlichen
Ende-zu-Ende-Latenz auf dem Handy. Keine Gewinn- oder Ausstiegszeitgarantie.

## Prüfung

`node test_risk_workspace.js`
`node test_risk_background.js`
`node test_risk_push_worker.js`
`python -m unittest test_risk_background test_background_push`
`node test_unapproved_comparison_ranking.js`
`node test_zukunft_navigation.js`
`node --check risk_workspace.js`
`node --check degiro_assistant.js`
`python -m py_compile server.py`

Browser: `NODE_PATH=<playwright modules> node browser_risk_workspace.cjs`.
Prüft fünf Hauptreiter, Risiko/Trade-Navigation, leeren Datenzustand, sichtbare
Betriebsgrenzen und 360px-Breite. Für diesen Test ist Chromium erforderlich.
