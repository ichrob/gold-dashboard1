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
