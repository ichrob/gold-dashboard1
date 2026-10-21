# Bob Android-Begleitlabor (nicht produktiv)

Zwei strikt getrennte Untersuchungen für Bob:

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
