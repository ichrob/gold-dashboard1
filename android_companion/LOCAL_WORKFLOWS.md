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

## Hybrid-Aufträge: lokal ausführen, externe Vorschläge nur auf Anfrage

Unter **Meine Aufträge** eine App und einen Auftrag in eigenen Worten angeben.
**Auftrag vorbereiten** sucht zuerst nach einem lokal erfolgreich bestätigten
Ablauf für exakt dieselbe App und denselben normalisierten Auftrag. Ein Treffer
benötigt weder Netzwerk noch KI. Mit **Auftrag starten** wird er lokal geprüft
ausgeführt. Jeder Schritt muss weiterhin am aktuellen Bildschirm bestätigt werden.

Ohne Treffer: **Bildschirm lernen** starten, gewünschte Ansicht öffnen und
innerhalb einer Minute zu Bob zurückkehren. Notwendige Beschriftungen einzeln
auswählen (anfangs keine ausgewählt); die Vorschau zeigt genau Ziel und Felder,
die über Bob an Groq gehen. Erst **Einmal an Groq senden** gibt diese eine Anfrage
frei. Keine Screenshots, kompletten OCR-Texte, Dateiinhalte, Eingabefeldwerte,
Geräte-Zugangsdaten oder Kontoübersichten werden automatisch angehängt.
Die Auswahl ist kein Anonymisierer: auch ein unscheinbares Label kann privat
sein. Deshalb nur unpersönliche Texte auswählen. Screenshot-OCR bleibt lokal;
beliebiges visuelles Verstehen einer Oberfläche durch die externe KI ist
damit noch nicht implementiert.

Der Vorschlag durchläuft getrennte Server- und Handy-Prüfungen. Er erscheint
im Schritteditor; er startet keine Bedienung. Erst der lokale Startknopf gibt
ihn frei. STOPP, Appwechsel oder Verlassen des Editors verwerfen verspätete
KI-Antworten. Eine bereits versandte Anfrage kann nicht zurückgeholt werden.
Keine automatischen Wiederholungen, Anbieter-/Modellwechsel oder Reparaturklicks.

Nur ein komplett am Bildschirm bestätigter Lauf wird automatisch als Erfolg
gespeichert (maximal 20 Einträge, keine stille Verdrängung). Abbruch oder Fehler
entziehen einem passenden alten Ablauf die automatische Wiederverwendung.
Manuelles Speichern erzeugt keinen Erfolgsnachweis. Vorhandene manuelle
Aufträge bleiben kompatibel. Gespeicherte Inhalte liegen privat auf dem Gerät.
Geänderte Oberflächen können einen gespeicherten Ablauf trotzdem scheitern
lassen; Bob stoppt dann.

### Server-Einrichtung ohne kostenpflichtigen Fallback

Fest: Groq openai/gpt-oss-20b, HTTPS-Endpunkt
https://api.groq.com/openai/v1/chat/completions, strukturierte JSON-Ausgabe,
keine Tools, kein Browsing. Diese Funktion verwendet keinen vorhandenen
Gemini-Recherche-Schlüssel.

Auf **bob-push-service**, ausschließlich über die geschützten Server-Einstellungen:

- BOB_WORKFLOW_GROQ_KEY: Schlüssel eines separaten Groq-Free-Kontos.
- BOB_WORKFLOW_GROQ_FREE_ACCOUNT=confirmed-free-no-payment: erst setzen,
  nachdem im Konto Free-Tarif und fehlendes Zahlungsmittel geprüft wurden.
- BOB_WORKFLOW_AI_DISABLED=1: sofortige serverseitige Sperre neuer Anfragen.

Keinen Schlüssel in Chat, Repository, APK oder Log eintragen. Kein Zahlungsmittel
hinterlegen, kein Developer-Upgrade. Nach Möglichkeit Zero Data Retention im
Groq-Konto einschalten; ohne diese Einstellung können Eingaben zur
Missbrauchsprüfung gespeichert werden. Anbieterbedingungen vor Aktivierung
prüfen: https://console.groq.com/docs/billing-faqs und
https://console.groq.com/docs/your-data .

Die Umgebungsvariable ist eine Betreiberbestätigung, **keine technische Abfrage
des Tarifs**. Ein Schlüssel allein beweist nicht, dass ein Konto kostenlos ist.
Wer später selbst einen bezahlten Tarif aktiviert, muss Bob zuvor deaktivieren.
Bob nimmt keinerlei Tarifänderungen vor und hat keinen alternativen kostenpflichtigen
Zugang. Bei fehlender Einrichtung, Quotenende, ungültiger Antwort oder Ausfall
stoppt die Anfrage.

Das gekoppelte Handy fragt über /api/android-workflow/plan an; Cookies allein
reichen nicht. Intern ist zusätzlich das Push-Service-Token nötig. Vor dem
Modellaufruf wird die Geräteberechtigung geprüft und eine PostgreSQL-Reservierung
dauerhaft verbucht: höchstens 20 Anfragen global / 10 je Gerät in 24 Stunden,
mindestens eine Minute globaler Abstand. Wiederholte Request-ID kostet keine
zweite Anfrage. Fehler verbrauchen die Reservierung. Gespeichert werden nur
Zeitpunkt und Hashes, keine Prompts oder Modellantworten. Provider-Drosselung
führt zu keinem Retry.

**Kostenlosen KI-Zugang prüfen** prüft Konfiguration und Kopplung, nicht die
tatsächliche Erreichbarkeit oder Gültigkeit des Provider-Schlüssels.
Ein echter Vorschlag und ein bestätigter Samsung-Lauf sind gesondert zu testen.
Die neue Funktion ist bis zur ausdrücklichen Server-Einrichtung deaktiviert.
Bestehender DEGIRO-Produktleser, Simulationen und Archivarbeiten sind unverändert.
