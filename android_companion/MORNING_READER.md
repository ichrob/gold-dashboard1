# Morgenliste lesen

## Ein Knopf für den gesamten Gold-Produktablauf

Auf der **Startseite von Bob Handy** steht jetzt oben der Knopf
**„▶ Bob starten · DEGIRO, Gold und fehlende Werte“**.
Er ist eine ausdrücklich vom Nutzer ausgelöste lokale Aktion, keine Fernanmeldung.

- Wenn die verschlüsselte PIN bereits auf diesem Gerät eingerichtet und der
  Tastaturtest bestätigt ist, öffnet Bob DEGIRO, schließt ausschließlich bekannte
  Anmeldedialoge, versucht die gespeicherte PIN genau **einmal** und wartet auf
  den bestätigten DEGIRO-Marktscreen. Die PIN wird nicht an Bob, GitHub oder
  Render übertragen. Ohne gespeicherte PIN muss DEGIRO bereits angemeldet sein.
- Erst nach dem bestätigten Anmeldeschritt sucht Bob **Gold →
  Hebelprodukte**, nimmt die zehn Listenbilder-Einträge auf und wartet auf
  die authentifizierte Serverbestätigung der aktuellen Zehnerliste.
- Der Server sendet einen **ISIN-genauen Feldplan** für aktuell fehlende
  Geld-/Briefwerte, Original-Anzeigezeiten, Hebel, KO, Basispreis,
  Bezugsverhältnis oder Währung zurück. Nur diese ISINs werden anschließend
  gezielt geöffnet, je höchstens zweimal geprüft und als originalzeitlich
  gekennzeichnete, ungeprüfte Handy-Beobachtung gespeichert.
- Nach Abschluss läuft die vorhandene automatische Detailübertragung.
  Ein abgelehnter oder veralteter Original-Batch bleibt in der lokalen
  Warteschlange und wird nicht mit einer anderen Liste vermischt.
- Der gesonderte Knopf **„DEGIRO-Leser · Einrichtung und Einzelprüfungen“**
  bleibt für Einrichtung, manuelle Wiederaufnahme und technische Diagnose.

Voraussetzungen: eingerichteter Lesedienst, mit Bob gekoppeltes Handy, bei
PIN-Automatik sicher hinterlegte lokale PIN und erfolgreich geprüfte Tastatur,
entsperrtes Samsung. STOPP, Sperrtaste, unbekannte Anmeldeseite, fehlende
Brokeroberfläche oder eine Ordermaske beenden den Lauf; nie mehrfach
PIN raten, nie Orders auslösen. Jede neue Android-Version braucht die
signierte APK und eine Prüfung am realen Gerät. CI bestätigt nur den Codepfad,
nicht den Erfolg auf dem Samsung.

Bob Handy übernimmt die zuletzt bei Bob gespeicherte Morgenliste über den angemeldeten Browser. Die APK bleibt ohne Internetberechtigung. Es werden keine Broker-Orders bedient.

1. Aktuelle signierte Bob-Handy-Version installieren. Android-Lesedienst einschalten; in DEGIRO und im Browser bei Bob anmelden.
2. In Bob Handy **Morgenliste automatisch von Bob holen und lesen** wählen. Bob lädt höchstens zwölf eindeutige ISINs aus einer maximal 24 Stunden alten Liste. Falls der Browser den App-Wechsel blockiert, den angezeigten Übergabelink antippen.
3. Entsperrtes Handy während des Laufs nicht bedienen. Bob sucht jeweils die exakte ISIN, liest Kurse und Produktparameter und prüft die ISIN nach dem Scrollen erneut. Höchstens zwei Versuche pro Produkt, 60 Sekunden pro Versuch und 15 Minuten je Lauf. Die Sperrtaste oder STOPP hält den Lauf an.
4. Ergebnisse werden vor dem nächsten Produkt lokal gespeichert. Am Ende öffnet Bob Handy den Browser zur Übertragung. Ein Timeout lässt die Ergebnisse gespeichert. **Gespeicherten Listenlauf an Bob übertragen / erneut versuchen** wiederholt die Übertragung. **Unterbrochenen Listenlauf fortsetzen** prüft nur noch unvollständige Produkte mit einem neuen begrenzten Versuchskontingent.
5. Im Bob-Bereich DEGIRO zeigt **Morgenliste automatisch lesen** Ergebnisse, fehlende Felder und Fehler. Die private KI-Diagnose enthält zusätzlich `androidReader` mit den letzten fünf gespeicherten Versionen.

Die Übertragung bestätigt eine konkrete Laufkennung und Speicherversion; ein älterer Beleg löscht keine neueren Ergebnisse. Serverdaten liegen in `bob_android_read_runs`, getrennt von Marktpreisen, Produktfreigaben und Simulationseingaben. Gelesene Bildschirmwerte bleiben ungeprüfte Beobachtungen. Ein gelesener Kurs ist keine Order oder Ausführung.

Die Navigation nutzt sichtbare Accessibility-Texte, Suchfelder und exakte ISIN-Treffer. Unzugängliche oder mehrdeutige Oberflächen werden mit einem Grund protokolliert; Bob errät keine Bildschirmkoordinaten. Login- und Orderansichten stoppen den Lauf. Ein realer Samsung-/DEGIRO-Gesamtlauf muss nach Installation auf dem Gerät geprüft werden; CI ersetzt diesen Gerätetest nicht.

## Vereinfachter Einstieg und automatische Diagnose

Der Hauptknopf zeigt die aktuell nötige Aktion: Dienst einschalten, Morgenliste starten, zur laufenden DEGIRO-Prüfung zurückkehren oder ein vorhandenes Protokoll übertragen. Einzelprüfungen und technische Daten liegen unter **Weitere Möglichkeiten und technische Diagnose**. Die Statusanzeige unterscheidet gelesene Produkte von bloß gespeicherten Fehlern.

Bei aktivierter automatischer Rückgabe werden auch Abbrüche übertragen. Eine Bildschirmsperre wird respektiert; der Browser wird erst nach dem Entsperren geöffnet. Pro gespeicherter Version erfolgt höchstens ein automatischer Öffnungsversuch. Nach Dienst-/App-Unterbrechung wird die offene Diagnose beim nächsten Öffnen von Bob Handy angeboten beziehungsweise automatisch übertragen. Ein bewusster STOPP schaltet das Lesen und automatische Öffnen aus. Manuelle Übertragung bleibt möglich.

Dies ist Diagnosezugriff auf übertragene Bob-Protokolle, kein Fernzugriff auf das Samsung, keine allgemeine Bildschirmfreigabe und keine Konto- oder Ordersteuerung.

## Lokale OCR zuerst – ohne Oracle oder neuen Cloudanbieter (11.11.2026)

Dieser Ablauf nutzt **bereits implementierten produktiven Code**:

1. DEGIRO-Accessibility-Texte werden vor und nach dem genehmigten
   Fenster-Screenshot verglichen. Nur vollständige, identische Produktzeilen
   werden als `appText` an den vorhandenen privaten Server übertragen.
2. Wo der App-Text unvollständig ist, versucht **Bob Handy** die
   Offline-Texterkennung mit dem in der signierten APK enthaltenen Google-ML-Kit.
   Zwei unterschiedlich skalierte echte Bildlesungen und ggf. strikt auf
   Produkte begrenzte Region-Lesungen sind nötig. Erst akzeptierte
   `localOcr`-Paare werden übertragen.
3. Auf dem Server bereitet `handset_list_worker.process` zuerst diese
   akzeptierten `appText`- und `localOcr`-Anhänge auf. Nur Bilder,
   **für die daraus kein vollständiger akzeptierter Bildpass entsteht**,
   dürfen in den bestehenden RAM-überwachten lokalen RapidOCR-Prozess fallen.
   Der Bilder-Originalnachweis bleibt im privaten Tagesbatch enthalten;
   bei Speicherknappheit wird der OCR-Versuch begrenzt verschoben.
4. Die abschließende Prüfung fordert weiterhin 10 eindeutige Produkte,
   übereinstimmende Original-Felder/ISIN und bestehende Handelsbarrieren.
   **Weder** Smartphone-Lesung noch Server-Fallback genehmigen eine Order.
   Keine Werte werden aus unterschiedlichen Bildern oder falschen Zeiten
   zu einem angeblich originalen Einzelkurs zusammengefügt.

Neue rein numerische Provenienzfelder im **erfolgreichen privaten**
Importbeleg: `recognitionRoute.appTextImages`,
`phoneMlKitImages`, `serverOcrFallbackImages`,
`missingPhoneReadingImages`, `rejectedPhoneReadingImages`.
Diese zeigen, ob ein tatsächlich importierter Batch ganz ohne
serverseitige optische Erkennung auskam. Keine ISIN, Screenshots,
Kontowerte oder Bildkoordinaten werden in den Zählern gespeichert.
Ältere Belege ohne diese Felder bleiben gültig.

**Oracle nicht erforderlich.** Das nicht aktivierte
[Oracle-Always-Free-Experiment #1474](https://github.com/ichrob/gold-dashboard1/pull/1474)
bleibt ein gesonderter Entwurf; diese Änderung erstellt keine VM,
keinen Cloud-Dienst, keine neuen Secrets, keine Zahlungspflicht und
keinen Remote-OCR-Bildversand. Der bestehende 505-MiB-OCR-Grenzwächter
und die 200-MiB-Startreserve werden nicht aufgeweicht.

Die gespeicherte Samsung-Lesediagnose enthält bereits den technischen
Nachweis von drei Listenscreens mit zwei App-Text- und einem lokalen
ML-Kit-Anhang. Das ist **kein** Nachweis, dass alle zehn Produkte
erfolgreich importiert wurden. Die tatsächliche Ende-zu-Ende-Prüfung
auf der installierten signierten APK und in DEGIRO bleibt ein
eigenständiges Abnahmekriterium.

## Fortsetzen nach bestätigter Übertragung

Der letzte aktuelle Lesestand wird lokal unter einem separaten Checkpoint
atomar mit jeder Berichtsversion gespeichert. Dieser einzelne Checkpoint ist
kein Upload-Kandidat. Die Bestätigung eines aktuellen Uploads entfernt nur den
Uploadauftrag; sie erhält auch bei alten, noch nicht migrierten Berichten den
Fortsetzungsstand. Bestätigungen älterer Archive ändern ihn nicht.

„Unterbrochenen Listenlauf fortsetzen“ und der vorhandene automatische
Wiederaufnahmeversuch verwenden ausschließlich den aktuellen Lauf oder diesen
Checkpoint. Sie wählen niemals einen alten zurückgestellten Upload. Vor einem
Schreibvorgang gelten weiterhin Listenalter, offene Produkte, Versuchsgrenzen
und die bestehenden Anmelde-/Leseschutzprüfungen. Ein neuer Leselauf ersetzt den
einzelnen Checkpoint; Originalberichte in der Uploadwarteschlange bleiben erhalten.

Für die Geräteabnahme einen Leselauf unterbrechen, dessen Upload bestätigen
lassen, Bob Handy neu öffnen und „Fortsetzen“ wählen. Bereits vollständig
bearbeitete Produkte dürfen nicht erneut gelesen werden; die Berichtsversion
muss steigen und die nächste bestätigte Übertragung zum selben Lauf gehören.
Die Tests ändern keine Echtgeldorders oder Ordermaskenberechtigungen.
Bereits vor diesem Update bestätigte und lokal entfernte Läufe werden dadurch
nicht nachträglich wiederhergestellt. Dann ist ein neuer Leselauf erforderlich.
