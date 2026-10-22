## 0.9 (Test): deutlich weniger Tippen, natürliche Einzelaufträge

Die vier beschrifteten Schnellzugriffe **Bob direkt öffnen**, **Goldprodukte direkt öffnen**, **Mein Trade direkt öffnen** und **Simulationen direkt öffnen** öffnen ausschließlich eine feste Bob-Seite nach einem einzigen bewussten Tastendruck. Eine erfolgreiche Anzeige der Zielseite wird dadurch **nicht** bestätigt; bei Bedarf die bestehende Bob-Anmeldung im Browser durchführen. Es gibt keine verdeckten Folgeaktionen und keinen Zugriff auf andere Apps.

Im Textfeld kann man jetzt neben der bestehenden strengen `BOB-AUFTRAG: ...`-Syntax auch einfache, frei **formulierte, aber auf die Positivliste beschränkte Einzelphrasen** (z. B. `Zeige mir meine Goldprodukte`) eingeben. Ein mehrteiliger freier Text kann **nicht** über den Einzelaktionsknopf freigegeben werden; Sprachpläne werden als begrenzte Schrittfolge vorbereitet und benötigen vor jedem Schritt eine eigene Prüfung. Unbekannte und finanzielle Befehle bleiben gesperrt. Zusätzliche Unit-Tests decken diesen Schutz ab.

**Noch ausstehend:** CI für den letzten Commit; danach Samsung-Echttest samt Signaturprüfung. Diese Version führt keine echte Marktanalyse aus; sie zeigt nur Bobs schon vorhandene Übersicht. Keine automatische Broker-/DEGIRO-Bedienung.

## Ausbau 22.10.2026 – Sprachdialog, Bob-Navigation und begrenzter Kontext (0.8, vor Samsung-Gerätetest)

Die bestehende Android-App unterstützt zusätzlich zu lokalen harmless Aktionen **read-only** Navigation
zu **Goldmarkt-Übersicht, Goldprodukten, Mein Trade, Simulation, Lernen und Recherche**. Die
Ziele stammen aus einer fest codierten Allowlist und öffnen ausschließlich die vorhandene
Bob-Webseite im Browser; Bob selbst verlangt seine normale Anmeldung. Eine Marktanalyse wird
**nur angezeigt/angesteuert**, nicht vom Android-Begleiter autonom gestartet oder als
aktuelle Preisprüfung behauptet. Die App bedient weder DEGIRO noch andere Broker-Apps.

Sprachfolgen wie „Zeige meine Goldprodukte und danach die Simulationen“ werden bis zu drei
erlaubten Schritten verarbeitet. Jeder Schritt muss erneut auf dem Gerät geprüft und einmalig
freigegeben werden. „Und jetzt die Recherche“ kann als eigenständiger Anschlussbefehl
verstanden werden. „Nochmal“ wiederholt nur den letzten **tatsächlich angestoßenen**,
zulässigen Schritt, nur innerhalb von 120 Sekunden und stets nach neuer Prüfung.
Weder Kontext noch Anmeldedaten, Audio oder Screenshots werden für Sprache persistiert.

Ein zusätzlicher **„🔊 Bobs Rückmeldung vorlesen“**-Button gibt nur lokale
Auftrags-/Fehlermeldungen über die auf dem Gerät vorhandene Text-zu-Sprache-Engine aus.
Sprachdienst und Sprachausgabe können je nach Samsung-/Android-Anbieter Onlinedienste nutzen.
Keine stets aktive Mikrofonüberwachung, keine ungeprüfte KI, kein Remote-Pairing,
keine Änderung von Handelsregeln und keine Echtgeldorders.

Bis die Android- und Bob-CI sowie der echte Samsung-Test erfolgreich sind, bleibt 0.8 eine
**Testfassung auf einem Entwicklungszweig**. Der Nutzer muss die APK manuell installieren;
eventuelle Signaturkonflikte zuerst untersuchen, nicht blind deinstallieren.

## Erweiterung 22.10.2026: zusammenhängende deutsche Sprachaufträge (Entwicklungsstand)

Die bestehende Offline-Android-App kann jetzt **bis zu drei eindeutig erlaubte, unterschiedliche Schritte**
in **einem gesprochenen Satz** erkennen, z. B. „Bob, öffne zuerst Bob und danach
wähle meine Produktbilder aus“. Sie zeigt die gesamte erkannte Schrittfolge an.
**Vor jedem einzelnen Schritt** sind ausdrücklich „Handy-Auftrag prüfen“ und
„Geprüften Handy-Auftrag einmalig ausführen“ nötig. Der nächste Schritt wird
nur vorausgewählt und niemals selbst gestartet. Jede Freigabe ist einmalig
und maximal 60 Sekunden gültig; App-Wechsel widerruft eine offene Freigabe.
„STOPP“ verwirft alle noch offenen Schritte (kein Rückgängigmachen bereits
geöffneter Apps).

Die vollständige Äußerung wird abgelehnt, falls **irgendein** Teil unbekannt,
handelsbezogen, ein Login-/Passwortauftrag oder mehr als drei Schritte ist.
Keine künstliche Schätzung eines unbekannten Befehls; keine generelle
KI-Fernsteuerung, keine Dauer-Mikrofonüberwachung, keine selbstständige
DEGIRO-Bedienung. Gesprochene Stopp-Befehle wirken **nur nach Antippen des
Mikrofon-Buttons**, nicht als permanentes Hotword. Die Android-Spracherkennung
kann trotz Offline-Präferenz die Daten beim Geräte-Anbieter verarbeiten.

Automatische Gradle-Tests prüfen harmlose Verknüpfungen, verbotene Mischsätze,
Duplikate, die Einzelaktionssperre und STOPP. Ein erfolgreicher CI-Lauf
ersetzt **nicht** den Test des Sprachdienstes auf dem Samsung. Für 0.7
ist eine neu signierte APK erforderlich; ein Signaturwechsel kann bei
bestehender Testinstallation die Aktualisierung verhindern.

## Zweite sichere Ausbaustufe: schnelle Auswahl und Not-Stopp (22.10.2026)

Auftragseingabe in derselben Android-App jetzt auch über Klartext-Schaltflächen: **Bob öffnen**, **Produktbilder auswählen**, **Android-Einstellungen öffnen**. Jede Schaltfläche wählt **nur** die gewünschte Aktion aus; erst eine eigene **Prüfung** und anschließend die **einmalige Ausführung** starten etwas. Text-/Sprachänderungen verwerfen die Freigabe. Die Freigabe ist maximal **60 Sekunden** gültig, einmalig verwendbar und verfällt bei App-Wechsel, fehlgeschlagener Ausführung oder dem klar sichtbaren **STOPP – Auftrag verwerfen**. Unit-Tests decken Wiederholung, anderes Ziel, Ablauf, Zeitrücksprung und Widerruf ab.

Wichtig: Der Stoppknopf widerruft einen **noch nicht ausgeführten** Auftrag. Er kann eine bereits geöffnete fremde App oder eine bereits ausgelöste Android-Systemaktion nicht rückgängig machen. Es gibt weiterhin **keinen Bedienungshilfendienst**, keine Hintergrund-Auftragsschleife, keine DEGIRO-Bedienung und keine automatische Anmeldung.

## Ergänzung 22.10.2026: Gesprochene, ausdrücklich bestätigte Handy-Aufträge

Die bereits vorhandene Android-Labor-App (kein Zweitprojekt) erhält einen Button **„🎤 Auftrag sprechen“**. Dieser öffnet nach ausdrücklichem Tippen Androids System-Spracherkennung per `RecognizerIntent.ACTION_RECOGNIZE_SPEECH`. **Keine dauerhafte Mikrofonüberwachung**, keine App-eigene Aufnahme und keine neue Mikrofon-, Internet- oder Accessibility-Berechtigung. Die bevorzugte Offline-Erkennung ist nur eine Bitte an den auf dem Samsung installierten Sprachdienst: **Der Android-/Drittanbieter-Sprachanbieter kann Audio dennoch online verarbeiten**. Das wird in der App angezeigt; ohne installierten Dienst bleibt die bisherige Text-/Button-Bedienung möglich.

Nur eindeutige, vollständig erkannte deutsche Sätze werden interpretiert, zum Beispiel **„Bob öffnen“**, **„Produktbilder auswählen“** und **„Öffne die Einstellungen“**. Sätze mit Handel, Login, DEGIRO-Bedienung, Zusatzaufträgen oder unklarer Absicht werden abgelehnt. Nach erfolgreicher Erkennung zeigt Bob den konkret erlaubten Auftrag im Klartext als Vorschau. Erst **„Geprüften Handy-Auftrag einmalig ausführen“** startet eine einzige Aktion. Die Freigabe verfällt danach; bei Abbruch/Fehler keine Aktion. Spracheingabe innerhalb der ChatGPT-Unterhaltung wird **nicht** heimlich an die Android-App weitergeleitet. Einen Auftrag mit „Goldprodukte anzeigen“ kann diese Version noch nicht bis in die Web-App hinein navigieren.

Die neue Funktion ist erst nach Installation der **neu gebauten APK** auf dem Samsung verfügbar; GitHub CI kann Kotlin-Parser und Build prüfen, aber nicht die Verfügbarkeit des Spracherkennungsdienstes oder die Bedienung auf dem echten Gerät. Gerätetest: auf **„🎤 Auftrag sprechen“** tippen, „Bob öffnen“ sagen, Vorschau lesen, einzeln bestätigen und Browserstart prüfen; danach ein nicht unterstütztes Handelskommando sprechen und die Ablehnung kontrollieren.

# Bob Android-Begleitlabor (nicht produktiv)

## Korrektur: BOB_OEFFNEN war nur ein Platzhalter (Samsung-Test 22.10.2026)

Ein realer Gerätetest zeigte beim Tippen auf „Handy-Auftrag prüfen“ den Fehler „Nicht erlaubter Auftrag“, obwohl der Beispielbefehl grau zu sehen war: `EditText.hint` zeigt nur einen Platzhalter, `text` blieb leer.

**Neue Bedienung:** Beim Öffnen steht **„Bob öffnen“** als tatsächlich vorausgefüllter, normal lesbarer Feldinhalt (nicht grau als Platzhalter). Es ist kein Kopieren oder Eingeben erforderlich: erst **Handy-Auftrag prüfen**, dann **Geprüften Handy-Auftrag einmalig ausführen**. Danach steht „Bob öffnen“ erneut zur Auswahl bereit, die Bestätigung ist jedoch verbraucht und muss für jede weitere Aktion wieder mit „Prüfen“ eingeholt werden. Für andere erlaubte Aufträge bleibt die Texteingabe bzw. Android-Teilen erhalten; die Zulassung von externen Kommandos bleibt auf die strenge Befehlsliste beschränkt.

Zusätzlicher Android-UI-Test kontrolliert den vorausgewählten Klartext „Bob öffnen“, Prüfvorschau und dass die Vorschau **keinen** Browserstart auslöst. Die CI kompiliert diesen UI-Test, führt ihn aber nicht automatisch auf einem Samsung aus. Eine Aktualisierung der APK ist für die Korrektur erforderlich; die bereits installierte 0.5 lässt sich bis dahin nutzen, indem der Befehl **wirklich eingegeben oder eingefügt** wird.

## Ergänzung 22.10.2026: ChatGPT/Bob-Handy-Aufträge – ohne Doppelentwicklung

Diese Teilstufe **erweitert die vorhandene** App `android_companion`; sie startet **keine zweite App** und überschreibt **nicht** die separat laufende Vereinfachung von Bob in PR #728.

**Bereits funktionsfähig im Quellcode:** Ein Nutzer kann in ChatGPT/Bob einen der folgenden exakt geschriebenen Einzeiler kopieren und in der Android-Begleit-App einfügen, oder den Einzeiler ausdrücklich über Android **Teilen → Bob: Android-Labor** senden:

- `BOB-AUFTRAG: BOB_OEFFNEN` – öffnet die bestehende Bob-Web-App im Browser.
- `BOB-AUFTRAG: PRODUKTBILDER_WAEHLEN` – öffnet den bereits vorhandenen Android-Bildwähler der lokalen OCR.
- `BOB-AUFTRAG: ANDROID_EINSTELLUNGEN_OEFFNEN` – öffnet nur die Einstellungen, ändert dort aber nichts.

Die App zeigt zunächst **eine Vorschau mit Klartext**. Erst nach einer separaten Berührung auf „Geprüften Handy-Auftrag einmalig ausführen“ wird genau **eine** der drei Aktionen ausgelöst. Änderungen an der Eingabe, beliebige Sätze, längere Skripte, zusätzliche Befehle, Käufe, Verkäufe und Login-Automationen werden abgewiesen. Nach Ausführung wird die Freigabe verbraucht; keine wiederholte oder verdeckte Abarbeitung. Falls Android die Ziel-App nicht öffnen kann, erscheint eine Fehlermeldung.

Das ist eine **lokale, nutzerbestätigte Auftragsübergabe**, **noch keine ChatGPT-Fernsteuerung**: Es existiert weder ein dauerhaft gekoppelter ChatGPT-Befehlskanal zum Smartphone noch ein Android-Accessibility-Service zur Bedienung von Drittanbieter-Apps. Das Labor erhält weiterhin keine Netzwerk-, Overlay-, Bildschirmaufnahme- oder Accessibility-Berechtigungen. Besonders DEGIRO wird **nicht automatisiert bedient**, und keine Echtgeldorder wird vorbereitet/ausgeführt. Bobs bestehende Broker-/OCR-/Handelsfreigaben bleiben unverändert.

**Prüfung:** `gradle -p android_companion :app:testDebugUnitTest :app:assembleDebug` sowie GitHub Actions `android-companion.yml`. Zusätzlich auf dem Samsung die **neue APK** installieren, einmal eine gültige und einmal eine unerlaubte Textfreigabe probieren und prüfen, ob das Gerät wirklich die vorgesehenen Apps öffnet. Ein erfolgreicher APK-Build ist kein Gerätetest.


## Nachbesserung 22.10.2026: „BNP OTC“ bei erfolgreicher Kurslesung

Die reale Samsung-Prüfung von zwei DEGIRO-Bildern zeigte korrekte ISIN, Geld 7,04 EUR, Brief 7,05 EUR, Zuletzt 7,04 EUR und sichtbare Anzeigezeit 22/10/2026 10:35. **Nur der Handelsplatz fehlte**, obwohl er auf dem Detailbild steht.

ML Kit kann eine Kopfzeile als mehrere einzelne Elemente erkennen, etwa `DE000PJ9NB98`, `•`, `BNP`, `OTC`. Der neue `QuoteLayout`-Parser erkennt einen OTC-/DOT-Handelsplatz nur, wenn er rechts von einer sichtbaren ISIN auf derselben visuellen Zeile oder rechts von „Börse“/„Handelsplatz“ steht. `BNP` aus dem Produktnamen allein ist ausdrücklich kein Beleg. Werte bleiben unbestätigte OCR-Beobachtungen, niemals verifizierte Handelsplätze oder ausführbare Geld-/Briefkurse.

Der neue Build und die Regressionstests müssen bestehen. Die tatsächliche Erkennung auf dem Samsung muss mit den **bereits vorhandenen** zwei Screenshots erneut geprüft werden; neue Screenshots sind nicht nötig.


## Korrektur 22.10.2026: Produktwerte in DEGIRO-Kursspalten erkennen

Die von Samsung/ML Kit extrahierten OCR-Zeilen können `Geld`, `Brief`, `Zuletzt` und die jeweiligen Zahlen in **getrennten Textblöcken** ausgeben. Deshalb sah Bob trotz vollständig sichtbarer Kurse oft nur die ISIN.

`QuoteLayout` nutzt jetzt OCR-Wort-/Zeilenrechtecke, sucht nur **räumlich passende** Werte rechts vom jeweiligen beschrifteten Feld und akzeptiert nur klare Betragsformate. `BNP OTC` wird als ungeprüfte Handelsplatzbeobachtung nur aus einer ISIN-Kopfzeile oder expliziten Handelsplatz-Beschriftung übernommen. `22/10/2026 10:35` in der Zeile „Zuletzt“ wird als **Anzeigezeit** bezeichnet und **niemals** als originalverifizierter Geld-/Briefkurs-Zeitstempel behandelt. Die Uhr im Android-Statusbereich ist keine Kursquelle. Preis im Produktkopf (z. B. `7,02 €`) wird nicht als Geld/Brief ausgegeben. Hebel und KO bleiben bei fehlender eindeutiger Beschriftung offen.

Für einen bewusst geteilten Satz aus 1–4 Bildern prüft Bob zuerst die gemeinsame ISIN, dann die extrahierten Felder. Widersprüchliche Feldwerte zwischen Bildern führen zu einer erkennbaren Ablehnung statt zu einer stillen Überschreibung. Alle Beobachtungen bleiben ungeprüft, unveröffentlicht und ohne Einfluss auf Top-3- oder Handelsfreigaben.

Synthetische Android-Testfälle decken `Geld 7,04 €`, `Brief 7,05 €`, `Zuletzt 7,04 €`, `BNP OTC` sowie abweichende Kopf- und Tageswerte ab. Das reale Samsung-OCR-Ergebnis muss nach Installation weiterhin kontrolliert werden.


Zwei strikt getrennte Untersuchungen für Bob:

## Korrektur: Teilen von zwei oder mehr Screenshots
- Samsung Galerie kann beim Teilen mehrerer ausgewählter Bilder den Android-Intent `ACTION_SEND_MULTIPLE` verwenden. Die frühere App meldete nur `ACTION_SEND` an und erschien deshalb möglicherweise **nicht** in der App-Auswahl.
- Neu: `ACTION_SEND` und `ACTION_SEND_MULTIPLE` mit `image/*`; über **Teilen → Mehr** kann „Bob: Android-Labor“ beim Teilen von 1–4 Bildern ausgewählt werden. Aus der App selbst lassen sich ebenfalls mehrere Bilder über **Produktbilder auswählen** wählen.
- Alle Bilder werden **lokal** und nacheinander gelesen. Bei ausdrücklich gemeinsam ausgewählten Bildern genügt jetzt **eine** eindeutig erkannte und prüfziffergültige ISIN als Serienanker. Andere Bilder ohne fehlerfrei erkannte ISIN werden nur **vorläufig als Teil dieser vom Nutzer zusammengestellten Serie** zugeordnet. Eine andere erkennbare ISIN oder ein widersprechender Kennzeichentext sperrt die Serie. Die App meldet transparent, auf wie vielen Bildern die ISIN tatsächlich erkannt wurde. Alle übernommenen Werte bleiben unbestätigt und können niemals Handelbarkeit oder ausführbare Kurse nachweisen.
- OCR liest zusätzlich die beschrifteten Felder `Börse` (als ungeprüfte Handelsplatzbeobachtung) und `Zuletzt` (separater, nicht ausführbarer Preis). Fehlende Geld-/Briefkurse werden **nicht** durch `Zuletzt` ersetzt. Kein automatischer Handelsnachweis.
- Diese Intent-Korrektur behebt eine plausible Ursache des fehlenden Share-Ziels; ob die App im Samsung-Galerie-Menü erscheint, muss **am konkreten Handy** geprüft werden.
- Für die neue APK muss der Nutzer eine aktualisierte Version installieren; die alte APK bekommt die neue Mehrfachteilen-Funktion nicht allein durch Bobs Web-Update.

## Vereinfachter Ablauf (22.10.2026)
1. In DEGIRO **ein einzelnes Produkt** öffnen und bis zu vier Screenshots dieses Produkts ohne Depot-/Kontodaten aufnehmen.
2. Ein oder mehrere Bilder in Samsungs Galerie auswählen und über **Teilen → Mehr → Bob Android-Labor** ausdrücklich teilen.
3. Das Android-Labor verarbeitet das freigegebene Bild mit lokalem OCR und öffnet **Bob** über eine HTTPS-URL mit einem **Fragment** (kein HTTP-Request mit OCR-Daten). Die Web-App entfernt das Fragment unmittelbar aus dem Verlauf und zeigt den **ungeprüften** Datensatz unter **Mehr → DEGIRO** an. Keine manuelle Dateiauswahl, Zwischenablage oder Texteingabe mehr nötig. Falls Bob eine Anmeldung fordert, zuerst anmelden und anschließend die Übertragung wiederholen.
4. Alternativ im Android-Labor **Bild manuell auswählen** und **In Bob anzeigen – ohne Kopieren** drücken. Der alte Kopierknopf bleibt als Rückfalllösung erhalten.

**Sicherheit:** Die automatisch erzeugte Übergabe enthält ausschließlich eine gültige ISIN und eng begrenzte OCR-Felder; Originalbild, Benutzerkennung, Kennwörter und sonstiger OCR-Text werden nie übertragen. Daten werden nicht als verifizierter Handelsplatz, Livekurs oder Handelsfreigabe gewertet. Fragmentdaten sind kurzzeitig für den lokal öffnenden Browser sichtbar; Bob entfernt sie nach dem Laden. Keine Echt-Order- oder Bot-Funktion. Der neue Ablauf muss auf dem konkreten Android-Gerät und mit der bestehenden Bob-Anmeldesitzung überprüft werden. Der GitHub-APK-Build ist noch kein tatsächlicher Gerätetest.


1. **Lokale Bild-Erkennung**: Nutzer wählt ein bereits vorhandenes Bild bewusst über Androids Dokumentauswahl aus oder teilt ein Bild über das Android-Menü ausdrücklich mit dem Bob-Android-Labor. Google ML Kit erkennt lokal Text; ein eng begrenzter Parser zeigt prüfziffergültige ISINs und einzelne klar beschriftete Zahlen als **unbestätigte OCR-Entwürfe**. Die Übergabe erfolgt ausschließlich durch bewusstes Kopieren in die Zwischenablage und Einfügen in Bobs neuem Menü **Mehr → DEGIRO → Android-Bildschirmdaten** oder durch Auswahl eines Empfängers im Android-Teilen-Menü. Es gibt keinen automatischen Upload und keinen direkten Bob-API-Zugriff. Keine Vollständigkeits- oder Zeitgültigkeitsbehauptung.
2. **Automatisierte Bedienung – nur eigenes Mock-UI**: Android UIAutomator gibt eine ISIN ein, tippt einen Suchknopf und kontrolliert den simulierten Ergebnistext in diesem Testprogramm. Nicht die DEGIRO-App, nicht die Anmeldung und keine Ordermaske.

## Hintergrund / Integrationsgrenze

- DEGIRO selbst untersagt Drittanbieter-Automatisierung und hat keine öffentliche Entwickler-API. Für die Live-App wird deshalb **keine** Accessibility- oder UIAutomator-Steuerung ausgeliefert. Offizielle Aussage: https://www.degiro.ch/helpdesk/en/trading-platform/can-i-automate-trades-or-use-trading-bots-degiro
- SnapTrade DEGIRO bleibt read-only: https://snaptrade.com/brokerage-integrations/degiro-api
- Bob nutzt bereits eine authentifizierte, same-origin-geschützte Nachweisstrecke (`/api/degiro/candidate-proof`), die Bildprüfung und Berechtigungen nicht automatisch durch Android-OCR ersetzt. Das Labor ruft sie bewusst **nicht** auf.
- Die Android-Anwendung hat **keine INTERNET-, Accessibility-, Bildschirmerfassungs- oder sonstigen besonders sensiblen Berechtigungen**, speichert keine Kontodaten, fragt keine Zugangsdaten ab und hat keine DEGIRO-Paket- oder URL-Verweise im ausführbaren Code. Eine Bildfreigabe erfolgt durch eine bewusste Android-Aktion. Wer den OCR-Entwurf in die Zwischenablage kopiert, muss wissen, dass andere Apps vorübergehend Zugriff auf den kopierten Text bekommen könnten.
- OCR kann 0/O/9 vertauschen, Labels vertauschen, mehrere Produkte mischen und Zeitstempel falsch lesen. Gültiger ISIN-Prüfcode ist nur ein Identitäts-Plausibilitätsfilter, kein Handelsplatz- oder Kursbeleg. Die Originalbild-, Originalzeit-, Emittenten-, KO- und Brokerprüfungen in Bob bleiben vollständig bestehen.

## Android Studio – lokale Prüfung

1. `android_companion/` als Android-Studio-Projekt öffnen (Android-Gradle-Plugin 8.7.3 / Kotlin 2.0.21, Android SDK 35 erforderlich). GitHub Actions erstellt einen Debug-APK als **Testartefakt**; dies ist keine App-Store-Veröffentlichung.
2. Auf eigenem Android-Gerät oder Emulator starten. Über **Bild manuell auswählen und lokal lesen** ein Testbild wählen oder in der Galerie ausdrücklich **Teilen → Bob Android-Labor**. **Keine** Screenshots mit Login, Passwort oder Kontodaten teilen. Bei mehr als einer ISIN werden keine Produktwerte übertragen.
3. Den unbestätigten OCR-Entwurf mit dem Kopierknopf manuell in Bob unter **Mehr → DEGIRO → Android-Bildschirmdaten** einfügen und prüfen. Diese Prüfansicht sendet nichts an Bobs Server, verändert weder Prüfstatus noch Rangliste und behält die Eingabe nicht dauerhaft. Danach im Demo-Bereich die künstliche ISIN DE000FG14AV8 suchen. Es darf ausschliesslich `DEMO-TREFFER ... KEIN ECHTER HANDEL` erscheinen.
4. Den unabhängigen UI-Test über Android Studio auf einem Emulator/Gerät starten. Falls später ein Gradle Wrapper hinzugefügt wurde, kann auch `./gradlew connectedAndroidTest` genutzt werden; aktuell ist kein Wrapper eingecheckt.
5. Vor einer Verbindung zu Bob erforderlich: freigegebener Datenumfang, brokerrechtliche Zustimmung für automatischen Abruf, authentifiziertes Pairing ohne Passwort-Weitergabe, replay-sicherer Empfang, separates zeitbehaftetes Quellenschema, Einwilligung/Abbruch, lokale Redaktions- und Review-Prüfung sowie Device-Tests.

**Status**: Laborquelle / unveröffentlichter Entwurf. Weder APK-Erstellung, Gerätetest noch produktiver Betrieb sind durch das Einchecken nachgewiesen. Bestehende Bob-Builds, Datenquellen, Handelsfreigaben und Trading-Simulationen bleiben unverändert.
