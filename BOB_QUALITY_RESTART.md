# Begrenzter Neustart der Simulationen

Implementierung: `quality-restart-20261105-v1`. Aktivierung erst nach Deployment
beim ersten Paper-Zyklus im bestehenden Handelsfenster. Keine Echtgeldorders.

## Alter Bestand

Unter dem bestehenden Worker-Lock werden die sieben Kontosteuerungen, die
Risiko-Studie und die drei Shadow-Steuerungen einmalig in `bob_quality_legacy`
mit SHA-256 des kanonischen JSON gesichert. Alle Fall-, Tages- und Ereignistabellen
bleiben erhalten. Das ist eine lokale, transaktionale Bestandssicherung, **kein
externes Backup und kein historischer Renditenachweis**. Kein Original wird gelöscht.

Erst in derselben Transaktion erhalten die Steuerungen `retiredAt`. Normale
Konten nutzen die bestehende Kampagnen-Endlogik und warten nötigenfalls auf
belegte Ausstiegskurse; Risiko- und Shadow-Positionen werden weiter überwacht,
aber keine neuen alten Fälle eröffnet. Ein Neustart setzt weder Kapital noch
Termine zurück. Der ursprüngliche manuelle Test und andere Forschungsfamilien
sind davon nicht betroffen. Ein Migrationsfehler rollt nur diese Umstellung
zurück; die bisherigen Konten können weiterarbeiten.

## Vier neue Untersuchungen

1. **Reaktion/Qualität:** Paper-Zyklen, unveränderte Quellzeiten, ungültige Eingaben,
   beobachtete Unterbrechungen >90 s während eines Handelstages und Fehler der
   Kontoverarbeitung. Letzte Entscheidung mit Kategorie und Begründung.
   Das ist kein Vollständigkeitsbeweis aller externen Signale oder Push-Zustellungen.
2. **Frühwarnung/Bestätigung:** Gemeinsamer Ursprung ist eine echte angezeigte
   Frühwarnung. Die Vergleichsvariante wartet auf dieselbe bestätigte Richtung.
   Ohne Bestätigung bleibt sie bei Abwarten (0); das ist kein Verlusttrade.
3. **Einstiegsverzögerung:** Gemeinsames Signal; Einstieg sofort oder mit dem
   ersten neuen Originalkurs nach 30/60 s (maximal weitere 60 s Toleranz).
   Entfallene/geänderte Richtung bedeutet keinen Einstieg. Tatsächliche
   Originalzeit des Einstiegs wird festgehalten, nicht rückdatiert.
4. **Seitwärtsfilter:** Bestätigte Richtung gegen denselben Versuch mit festem
   ADX<20-Abwarten. Unbekannter ADX ergibt keinen Vergleich, keinen Ersatzwert.

Die drei Strategiestudien sind zunächst **60-Minuten-Spot-Benchmarks** mit 0,16 %
ausgewiesenen Rundweg-Modellkosten pro eingestiegener Variante. Sie sind keine
Konten mit einem Euro-Risikobudget und keine KO-Produkt-/Broker-Nettorenditen.
Alle Varianten haben denselben Endzeitpunkt. Stop-/Zielberührungen und größte
beobachtete Gegenbewegung werden nur protokolliert; es wird kein Stop-Fill
simuliert und kein kontinuierlicher Drawdown behauptet.

Die Signalzeit wird mit einer bereits geschlossenen Originalkerze des
Signalzeitrahmens verbunden: Bobs 5m-Bestätigung bleibt 5m, statt fälschlich
eine identische 15m-Kerzenzeit zu verlangen. Spot-Identität, Originalquelle,
Zeitabgleich, Frische und Schätzungsverbote bleiben aktiv.

## Abschluss und Speicher

Maximal ein offener Fall je Strategie, höchstens 200 Fälle je Strategie und
20 Kalendertage ab tatsächlichem Start. Neue Fälle nur werktags 08–21 Uhr
Europe/Zurich, damit die 60-Minuten-Nachbeobachtung im Paper-Fenster bleibt.
Offene Fälle laufen nach Ablauf aus; fehlende Originalausgänge bleiben
`inconclusive`. Eine Datenlücke >90 s, ungültige Eingaben während eines Falls
oder ein fehlender Originalkurs am Endzeitpunkt verhindern die Renditewertung.

Nur ein begrenztes Steuerungsdokument und abgeschlossene Fälle werden neu
persistiert, kein dreifaches dauerhaft wachsendes Zyklusjournal. Gemeinsame
Marktdaten werden nicht erneut abgefragt. Die Übersicht zeigt vollständige,
ungeklärte und offene Fälle sowie Qualität und technische Beobachtungen.

Der Status `completed-review-required` bedeutet **Erfassung beendet**, nicht
bewiesene Überlegenheit. Kleine/lückenhafte Stichproben bleiben unzureichend.
Erst eine gesonderte Bestätigung an neuen Daten darf eine Regelübernahme
begründen; es gibt keine automatische Gewinnerauswahl. Die hinterlegten
Erkenntnisse aus Altversuchen bleiben als Hypothesen gekennzeichnet. Nur der
Ausschluss unbelegter Ergebnisse ist eine feste Qualitätsregel.

## Validierung

`test_research_restart.py` prüft gemeinsame Eingaben, 5m-Zeitbezug, Lücken,
Originalzeit, verspätete Bestätigung, entfallene Signale, Modellkosten,
Endbedingungen und Vorrang des neuen Abschlusszeitpunkts. Der PostgreSQL-Test
prüft Bestandssicherung, erneuten Aufruf und Transaktionsverhalten in einer
isolierten Testdatenbank; lokale Läufe ohne Testdatenbank überspringen ihn.
