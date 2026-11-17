# Bob · Stop-Loss-Übung ohne DEGIRO, Echtgeld oder Position

## Zweck

Der **SIMULATION**-Knopf auf `StopLossPrefillActivity` startet ausschließlich die
`StopLossSimulationActivity`. Anders als der Live-Eingabeentwurf wird hier
**kein Haken für eine tatsächlich gehaltene Position benötigt**; er bleibt leer.

Der Ablauf enthält keine Broker-Verbindung, keinen PIN-Zugriff, keine echte
Android-Bedienung eines anderen Fensters und keine Handelsorder. Er ruft
**niemals** `StopLossPrefillExecutor.execute`, `ProductReadService`,
`StopLossPrefillSession.arm` oder DEGIRO per Intent auf. Auch der Kopierentwurf
ist für diese Übung nicht notwendig.

## Geprüfte simulierte Fälle

1. Fiktives EUR-Produkt `DE000FB0A490`, 3 Stück, Modell-Stop 25,90 EUR:
   Produktdetail erkennen, VERKAUF öffnen, Stop Loss auswählen, beide Felder
   simuliert ausfüllen und die Werte wieder auslesen.
2. Falsche ISIN muss sofort sperren, ohne Eingabe.
3. BUY ausgewählt statt SELL muss sperren.
4. Doppelte Stop-Feld-Bezeichnungen müssen sperren.

Für jeden Durchlauf: Brokerzugriff **nein**, Handelsorder **nein**.
Alle Zahlen sind reine Testwerte, nicht aktuelle Kurse.

## So führt der Besitzer den Test nach dem neuen signierten/abgenommenen Lab-Build aus

Labor-App → DEGIRO-Leser → „Stop-Loss-Felder automatisch vorbereiten · keine Order“
→ **„SIMULATION starten · ohne DEGIRO und ohne Position“**
→ „Simulation starten · ohne echte Position“.

Die Ansicht zeigt je Szenario die Prüf- und Abbruchschritte und im Erfolgsfall
„4/4 Simulationen bestanden · 0 Brokerzugriffe · 0 Orders“.
„Simulation zurücksetzen“ löscht den sichtbaren Übungsstatus ohne Persistenz.

## Freigabevoraussetzung

Neuer Android-Labor-Build mit Unit-Tests und Offline-Fixture auf **exaktem**
Simulations-Commit grün. Labor-APK ist keine signierte Aktualisierung der
dauerhaften Bob-Handy-App. Sie ist nur für die lokale Simulation vorgesehen.
Der Live-Broker-Formularpfad bleibt gesondert abnahmebedürftig und PR #1790
bleibt bis zum gesonderten Samsung-Nachweis ungemergt.
