# Bob Handy – Stop-Loss-Felder vorbereiten (ohne Orderauslösung)

**Status:** Geräteadapter im Pull Request; noch kein Nachweis auf einer echten DEGIRO-Verkaufsmaske. Nicht als live bestätigte Handelsfunktion behandeln.

## Einmalige Benutzung nach erfolgreicher Abnahme

1. Bob berechnet im Zwei-Stufen-Stop-Assistenten den Produkt-Stopp mit frischen Gold-/FX-Referenzen. Nur bei einer gültigen EUR-ISIN und positiver ganzer Stückzahl steht **Bob-Handy-Entwurf kopieren** bereit. Der kopierte Entwurf enthält keine Zugangsdaten.
2. In DEGIRO die **tatsächlich gehaltene Position** aufrufen, ISIN, Stückzahl, Produktwährung und Orderbedingungen selbst prüfen. Keine simulierte Position als echte übernehmen. Die Detailseite oder die schon geöffnete VERKAUF-Maske im Hintergrund belassen.
3. Bob Handy → **DEGIRO-Leser · Einrichtung und Einzelprüfungen** → **Stop-Loss-Felder automatisch vorbereiten · keine Order**. **Bob-Entwurf aus Zwischenablage übernehmen**, Checkbox zur Position auswählen und das lokale Bestätigungsfenster freigeben.
4. Bob öffnet die DEGIRO-Detailseite bzw. die **VERKAUF**-Maske, soweit eindeutig erkennbar, wählt **Ordertyp → Stop Loss** und versucht, **Stop (€)** und **Anzahl** zu befüllen. Er liest die Felder anschließend zur Bestätigung erneut aus.
5. Bob stoppt vor **Order platzieren**. Der Mensch prüft einen aktuellen Originalkurs, Stopp-Auslösepreis, Stückzahl, Kosten, offene Orders sowie Ausführungsrisiko und entscheidet selbst über eine Order.

## Grenzen

- **Keine Echtgeldorder, keine automatische Verkaufsbestätigung, keine PIN-/Gerätesperren-Umgehung.**
- Nur **EUR-Produkt-Stopp** in 0,01-EUR-Schritten; ein CHF-Finanzrahmen allein bedeutet nicht, dass das Produkt in CHF notiert.
- Der kopierte Entwurf ist maximal **5 Minuten** alt; die lokale Eingabe hat **120 Sekunden** Laufzeit. Gerät muss entsperrt und der Lesedienst eingeschaltet sein.
- Eine fremde App, ein uneindeutiges Feld, fehlende Bestätigung der **VERKAUF**-Richtung, andere laufende Leseaufträge oder eine Bildschirmsperre beenden die Vorbereitung.
- Ohne bestätigtes Modell, ISIN oder Stückzahl wird kein Entwurf erzeugt.
- Kein Broker-Geldkurs wird durch einen Modellwert ersetzt. Eine Stop-Loss-Order garantiert keinen Ausführungskurs; bei einem Knock-out kann sie wirkungslos bleiben.
- Die Erkennung basiert auf Android-Accessibility-Knoten, **nicht auf festen Koordinaten**. Ein DEGIRO-UI-Update oder unzugängliche Edit-Felder kann die Eingabe blockieren. Niemals automatisch die Blockade umgehen.
- Vor einer Freigabe für die signierte Stable-App: **Android-CI, freigegebener Test auf einem echten Samsung und Nachweis: kein automatisches Order-Submit**.

## Prüfungen

- Reine Kotlin-Policytests prüfen Entwurfsformat, EUR und Alter, falsche ISIN, BUY-Sperre, Start vom Detailbild, Auswahl Stop Loss, Wertekontrolle, Abbruchbedingungen.
- Die bestehende Fernsteuerung/der Produktleser erhält **keine allgemeine Broker-Order-Berechtigung**. Der neue Pfad hat eine eigene, flüchtige lokale Startfreigabe.
