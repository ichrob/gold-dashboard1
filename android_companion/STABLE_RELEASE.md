# Bob – Eine Android-App, dauerhafte Updates

**Ziel:** Ein einziges, dauerhaft updatefähiges **Bob – Handy** statt immer neuer
`Android-Labor`, `Paralleltest` und `Sprachtest`-Pakete. Die bisher auf Samsung
bestätigte Sprachsteuerung und der Start am Anfang der Goldproduktliste bleiben
unverändert. Alle Echtgeldorders und Broker-Automation bleiben ausgeschlossen.

## Stand

Der Android-Code, die feste Paketkennung und die **getrennte signierte
Release-Pipeline** sind eingeführt. Eine erste dauerhafte Version wurde als
`bob-android-v10001` veröffentlicht; nachfolgende Versionen benutzen denselben
Signaturschlüssel. Für jedes Repository ist dafür einmalig ein privater Schlüssel
anzulegen, sicher zu sichern und als verschlüsselte GitHub Actions-Secrets
einzurichten. CI-Debug-APKs bleiben ausdrücklich Teststände, **keine Updates**.

Die dauerhafte Paketkennung lautet:
`ch.bob.degirocompanion.stable`

Die Debug-Testkennung lautet:
`ch.bob.degirocompanion.stable.voicetest`

Diese dauerhafte Kennung darf nach dem ersten Release nicht mehr geändert werden.
Die APK muss bei jedem späteren Update **mit demselben privaten Schlüssel**
signiert werden und eine höhere `versionCode` besitzen. Das GitHub-Releases-
Downloadformat ist nur eine manuelle Installation, **kein** Play-Store-Autoupdate.

## Einmalige sichere Signierung

**Niemals** einen privaten APK-Signaturschlüssel, Passwörter, Base64-Keystore oder
private GitHub-Tokens in ChatGPT-Nachrichten, öffentliche GitHub-Issues, Commits,
Pull Requests oder öffentliche Release-Dateien kopieren.

Wer nur ein Samsung hat, kann für diese einmalige Einrichtung eine geeignete
lokale Terminal-Umgebung mit Java `keytool`, `gh` (GitHub CLI), `base64` und
`bash` verwenden, zum Beispiel eine vertrauenswürdige Termux-Installation.
Alternativ genügt ein PC mit denselben Werkzeugen.

1. Auf einem **eigenen, vertrauenswürdigen Gerät** in GitHub CLI anmelden:
   `gh auth login`. Nicht den Token in den Chat kopieren.
2. Im lokal ausgecheckten Repository das Skript
   `android_companion/tools/setup_stable_signing.sh` **zuerst lesen**,
   anschließend lokal mit Bash starten. Es fragt interaktiv ein starkes
   Passwort ab, legt einen PKCS12-Schlüssel nur im privaten Geräteordner
   `~/.bob-private-android-signing/` an, prüft dessen SHA-256-Zertifikatsfingerabdruck
   und setzt im GitHub-Repository verschlüsselte Actions-Secrets.
3. Den erzeugten `bob-stable.p12` **separat und verschlüsselt sichern**.
   Passwort getrennt in einem Passwortmanager aufbewahren. Das Keystore-Backup
   ist für spätere Updates unverzichtbar. Die GitHub-Secrets sind nachträglich
   nicht auslesbar; sie ersetzen das eigene Backup nicht.
4. Nach erfolgreichem Backup GitHub → **Actions** →
   **Bob Android – dauerhafte signierte App** → **Run workflow** → `main`.
   Die Ausgabe benötigt eine **grüne Bob-CI für exakt diesen Main-Commit**.
5. Die App steht anschließend in **Releases → Latest** als
   `Bob-Handy.apk` bereit:
   https://github.com/ichrob/gold-dashboard1/releases/latest
6. APK in Samsung „Eigene Dateien“ installieren. Sie installiert sich zunächst
   **neben** vorhandenen Test-Apps. Nach erfolgreichem Sprach-/Bild-Test
   können die alten Android-Test-Apps freiwillig und einzeln entfernt werden.
   Die Bob-Webseite im Browser, gespeicherte Screenshots und andere Apps
   bleiben davon unberührt. Achtung: Lokale App-Daten lassen sich wegen
   unterschiedlicher Paketkennungen **nicht automatisch übertragen**.

Das lokale Setup setzt folgende **verschlüsselte** Repository-Secrets:
- `BOB_ANDROID_KEYSTORE_BASE64`
- `BOB_ANDROID_STORE_PASSWORD`
- `BOB_ANDROID_KEY_ALIAS`
- `BOB_ANDROID_KEY_PASSWORD`

Außerdem legt es die öffentliche, **nicht geheime** Repository-Variable
`BOB_ANDROID_CERT_SHA256` fest. Jeder spätere Release-Workflow vergleicht den
tatsächlichen APK-Zertifikatsfingerabdruck damit und verweigert ein Update bei
Abweichung. Der Workflow prüft auch die Offline-Berechtigungen, das feste
Android-Paket und den automatisch steigenden Versionscode.

**Hinweis zur ersten Version 10001 (23.10.2026):** Die signierte Datei wurde
unter dem technisch erzeugten Namen `app-release.apk` veröffentlicht. Die
GitHub-Beschriftung hat den Dateinamen nicht umbenannt. Die Datei ist daher
nicht allein wegen ihres Namens ungültig. Ab der nach diesem Fix gebauten
Version heißt die veröffentlichte Datei `Bob-Handy.apk`; die Signatur und
Paketkennung bleiben gleich.

## Update nach der Ersteinrichtung – ohne Termux oder GitHub-Klicks

**Automatischer Ablauf:** Eine genehmigte Änderung an der Android-App wird
nach dem Merge in `main` von der vollständigen **Bob CI** geprüft. Nur wenn der
`push`-CI-Lauf für exakt den noch aktuellen `main`-Commit erfolgreich
abgeschlossen ist, prüft der Release-Workflow, ob sich die **Android-App-Dateien
seit dem zuletzt signierten Release** verändert haben. Nur dann erstellt er
automatisch die nächste APK – mit der unveränderten Paketkennung, dem in GitHub
gesicherten **selben** Schlüssel, einer höheren `versionCode` und dem streng
geprüften Zertifikatsfingerabdruck. Änderungen nur an Markt, Forschung, Server,
Dokumentation oder Tests erzeugen nicht unnötig eine neue Handy-App.

Eine manuelle GitHub-Aktion unter **Run workflow** bleibt als kontrollierter
Fallback möglich, etwa um einen fehlgeschlagenen Build wieder anzustoßen. Auch
dabei gelten exakt dieselben CI-, Änderungs- und Sicherheitsprüfungen. Ein
ungültiger, unvollständig konfigurierter oder älterer Build darf die signierte
App nicht ersetzen.

Die jeweils neueste `Bob-Handy.apk` steht unter
https://github.com/ichrob/gold-dashboard1/releases/latest.

**Einzige weiterhin manuelle Handlung:** Die APK auf Samsung herunterladen und
die Installation über die bestehende `Bob – Handy`-App bestätigen. Die
GitHub-Webseite kann ohne Android-App-Store, erlaubte Geräteverwaltung oder
explizite Gerätebestätigung **kein** App-Update auf dem Handy installieren.
Du brauchst für normale Updates **weder Termux, neue Passwörter noch einen neuen
Signaturschlüssel**. Alte Test-Apps sind keine Updates und müssen nicht erneut
installiert werden. Der Browserteil von Bob aktualisiert sich separat auf Render.

Die Signatur-/Paket-ID-Prüfung ist absichtlich strikt: Ohne korrekte,
dauerhafte Secrets werden **keine** als updatefähig bezeichneten APKs
veröffentlicht. Keine automatische Echtgeldorder, keine Android-
Bedienungshilfen, kein Gerätefernzugriff.

## Was ChatGPT ohne Gerätebesitz nicht bestätigen kann

- Einrichtung/Backup des **privaten** Schlüssels auf dem Gerät
- Installation von `Bob – Handy` und Migration aus alten Test-Apps
- Spracheingabe, Karten-Scrollposition oder lokales Android-Share-Menü
  auf dem realen Samsung
- automatische APK-Installation ohne Google Play / Geräteverwaltung

Ein GitHub-„Build erfolgreich“ ist kein echter Installationstest.
