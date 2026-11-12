# Bob Überwachung und Stop-Vergleich, 12.11.2026

Keine Echtgeldorders. DEGIRO-Ausführung bleibt manuell; der bestehende Orderentwurf und Belegabgleich bleiben erhalten.

Produktwidersprüche (Spot/Future, Basiswert und Long/Short) werden vor dem automatischen Überwachungsstart zurückgewiesen.

Der prospektive Stop-Vergleich v2 wird an neue Fälle der bestehenden Konten balanced, trend800nov, normal1000nov, ema3000nov und noema5000nov angehängt. Er startet keine Konten neu und erzwingt keine Einstiege. Historische v1-Fälle bleiben gespeichert und werden nicht mit v2 vermischt. Ergebnisse sind nach Konto getrennt. Die Oberfläche zeigt nur die neue Vergleichsversion.

Varianten: eingefrorener Anfangsstop, 1,5 ATR, Struktur, Bobs gemeinsame dynamische Stop-Engine und 2 % unter dem höchsten beobachteten Produkt-Geldkurs. Der prozentuale Produktstop gilt für Long- wie Short-Turbos gleich. Alter Stop wird zuerst geprüft; Stop und Höchstkurs werden mit dem Studienzustand in PostgreSQL gespeichert. Alle Varianten verwenden denselben Einstieg, volle Stückzahl, dasselbe feste Ziel und Zeitende. Dies ist ein Stop-Vergleich, keine Replikation von Bobs gesamter Teilverkaufs-/Zielverlängerungsstrategie. Keine automatische Gewinnerübernahme.

Tests: JSON-Wiederherstellung, separate Datenbankverbindung nach Commit (nur isolierte Testdatenbank), veraltete Kurse, Datenlücken, doppelter Tick, getrennte neue Einstiege, LONG/SHORT-Produktrichtung und gemeinsame Bob-Engine. Offline-End-to-End-Tests prüfen Analyse, Produktwahl, Ausstieg und Kosten. Ein Produktionsneustart und echte Geräte-/Brokerbelege bleiben gesonderte Abnahmeschritte.

## Offizielle Broker-Alternative

IG Bank Schweiz dokumentiert REST/Streaming und einen Demo-Zugang, verlangt dafür jedoch ein zugeordnetes Livekonto. Die API handelt CFDs, nicht die bisherigen DEGIRO-KO-Produkte. Kein Konto angelegt, kein Vertrag abgeschlossen.
https://www.ig.com/en-ch/trading-platforms/trading-apis/how-to-use-ig-api
https://www.ig.com/en-ch/trading-platforms/trading-apis

IBKR dokumentiert eine offizielle Trading-API und Warrants/strukturierte Produkte. Das beweist weder die Verfügbarkeit einer bestimmten ISIN noch deren Konto-Handelserlaubnis. Wertpapier-Marktdaten über API benötigen meistens ein Abonnement; eine streng kostenlose Echtzeitlösung ist damit nicht nachgewiesen.
https://www.interactivebrokers.eu/campus/ibkr-api-page/web-api-trading/
https://www.interactivebrokers.com/docs/general/market-data-subscriptions/introduction
https://www.interactivebrokers.com/en/pricing/commissions-stocks.php

Entscheidung: kein Brokerwechsel und keine kostenpflichtige Datenanbindung ohne gesonderte Nutzerentscheidung; aktuelle Umsetzung bleibt Simulation plus manuelle DEGIRO-Ausführung.
