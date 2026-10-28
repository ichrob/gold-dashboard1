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

## Bewusste Betriebsgrenzen

Nur Vordergrundanalyse: kein neuer Hintergrunddienst, keine neue Push-Kategorie,
kein neuer Datenanbieter und keine Brokerorder. Die bestehende Tradeüberwachung
bleibt separat. Ein Neuladen beginnt eine neue Zusatzbeobachtung, der tatsächliche
bestehende Trade-Stop bleibt unverändert. Der Reiter zeigt diese Grenzen ausdrücklich.

Ein Update der Ansicht pro Sekunde erzeugt keine neuen Quellkurse. Veraltete Daten
sperren Richtung und Rangliste. Fehlende Minutenhistorie wird nicht durch 5m- oder
Future-Daten ersetzt. Regeln und ATR-Faktoren sind unvalidierte Forschungsparameter.

Für den vollständigen späteren Hintergrundbetrieb fehlen ein nachgewiesener
schneller Datenzugang, dauerhafte serverseitige Risikozustände, Push-Ablaufzeiten
und Zustellmessungen sowie Simulationen mit echten Produkt-Geld-/Briefkursen,
Kosten und Nutzerreaktionszeit. Keine Gewinn- oder Ausstiegszeitgarantie.

## Prüfung

`node test_risk_workspace.js`
`node test_unapproved_comparison_ranking.js`
`node test_zukunft_navigation.js`
`node --check risk_workspace.js`
`node --check degiro_assistant.js`
`python -m py_compile server.py`

Browser: `NODE_PATH=<playwright modules> node browser_risk_workspace.cjs`.
Prüft fünf Hauptreiter, Risiko/Trade-Navigation, leeren Datenzustand, sichtbare
Betriebsgrenzen und 360px-Breite. Für diesen Test ist Chromium erforderlich.
