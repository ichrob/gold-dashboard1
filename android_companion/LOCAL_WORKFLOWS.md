# Meine Aufträge — lokale Bedienabläufe

Implementierter Ausbau, vor signierter Veröffentlichung am Samsung zu prüfen.
In Bob Handy: **Meine Aufträge · Screenshots, Sprache und Abläufe**.
Die separate Android-Bedienungshilfe „Bob · Meine Aufträge“ muss lokal aktiviert
werden. Sie arbeitet nur während eines lokal gestarteten Auftrags in der vom
Nutzer gewählten App. Der bestehende DEGIRO-Leser bleibt separat; DEGIRO wird
nicht durch den allgemeinen Ausführer bedient.

## Ablauf beibringen

1. App wählen, „Bildschirm lernen“ starten, zur gewünschten Ansicht wechseln.
2. Zu Bob zurückkehren und gelernte Beschriftungen anzeigen. Ein Ziel auswählen.
3. TEXT und ERGEBNISTEXT durch konkrete Inhalte ersetzen, weitere Schritte
   ergänzen. Eine Zeile pro Schritt:

   ```text
   Tippe auf "Suche" -> "Suchbegriff"
   Schreibe "Gold" in "Suchbegriff"
   Warte auf "Gold"
   ```

   Diktat versteht auch „Tippe auf Suche und warte auf Suchbegriff“ und
   „Schreibe Gold in Suchbegriff“. Ein Feld kann alternativ über seine angezeigte Android-ID adressiert werden.
4. Unter einem Namen lokal speichern, später laden und einmal starten.
   Kein ChatGPT-Aufruf ist für die Ausführung erforderlich. Über „Gespeicherten
   Auftrag per Sprache starten“ genügt der exakt erkannte gespeicherte Name.

## Grenzen und Erfolgsnachweis

Maximal zwölf Schritte, drei Minuten pro Lauf und zwanzig Sekunden je Schritt.
Ein Klick wird genau einmal angefordert; danach muss ein vorher noch nicht
sichtbarer, ausdrücklich benannter Ergebnistext erscheinen. Schreiben benötigt eine eindeutige Android-Feld-ID und wird am
selben Feld geprüft. Doppelte Ziele, geschützte Ansichten, Appwechsel,
Bildschirmsperre und eigener Touch während der Ausführung stoppen den Lauf.
Es gibt keine Koordinatenklicks, Shellbefehle oder Orderaktionen. Ein Neustart
nimmt nichts wieder auf. STOPP beendet auch die Lesesitzung.

Die Sprachfunktion diktiert Schritte in den Editor; Form und Ziele müssen dem
beschriebenen Wortschatz entsprechen. Das ist **kein universelles Sprachmodell**
und kein beliebiger selbstprogrammierender Agent. Auch gespeicherte Abläufe
werden bei jedem Laden erneut validiert. Sie enthalten Eingabetexte lokal im
privaten App-Speicher; keine Passwörter darin speichern. App-Backups bleiben aus.

## Screenshots und JSON

Direkte Screenshot-Texterkennung in der gewählten App ab Android 11 oder
Bildauswahl über Android (auf maximal 2048 Pixel pro Seite verkleinert). Lokales ML Kit, keine neue Cloud-Verbindung. Es ist
OCR, keine allgemeine visuelle Interpretation von Symbolen oder Diagrammen.
Texte aus Bildern/Dateien werden nur angezeigt und niemals als Befehle behandelt.
Ergebnisse werden nicht in Diagnoseberichte oder Auftragsdateien übernommen.

Die JSON-Suche erhält genau den lokal ausgewählten Ordner über Androids
Dateiauswahl, ohne dauerhafte neue Ordnerfreigabe. Bis zu fünf Unterordnerebenen,
300 Einträge und 50 Treffer, mit Abbruchprüfung nach 15 Sekunden zwischen
Provideraufrufen. Ein blockierender Dokumentanbieter kann länger brauchen.
Lesen bis 1 MiB; Objekt/Array-Validierung; Vorschau bis 20.000 Zeichen. Keine
Änderung, kein Upload und keine Ausführung der Dateiinhalte.

## Abnahme

JVM-Tests: gesamter Plan statt Teil-Ausführung, geschützte/mehrdeutige Ziele,
Klick-Wirkungsnachweis, falsche Eingabefeld-ID, Zeitlimit, Sperre und Appwechsel.
Zusätzlich erforderlich: Android-Build, vorhandene Repository-Gates, signierte
APK und realer Samsung-Lauf einschließlich STOPP, OCR, Dateiauswahl und
abgelehntem Ziel. Quellcode und Lab-APK sind kein Nachweis einer installierten
funktionierenden Erweiterung. Freie KI-Auftragsplanung und visuelle Erkennung
von Symbolen bleiben eine gesonderte, noch nicht implementierte Ausbaustufe.
