# Morgenliste lesen

Bob Handy übernimmt die zuletzt bei Bob gespeicherte Morgenliste über den angemeldeten Browser. Die APK bleibt ohne Internetberechtigung. Es werden keine Broker-Orders bedient.

1. Aktuelle signierte Bob-Handy-Version installieren. Android-Lesedienst einschalten; in DEGIRO und im Browser bei Bob anmelden.
2. In Bob Handy **Morgenliste automatisch von Bob holen und lesen** wählen. Bob lädt höchstens zwölf eindeutige ISINs aus einer maximal 24 Stunden alten Liste. Falls der Browser den App-Wechsel blockiert, den angezeigten Übergabelink antippen.
3. Entsperrtes Handy während des Laufs nicht bedienen. Bob sucht jeweils die exakte ISIN, liest Kurse und Produktparameter und prüft die ISIN nach dem Scrollen erneut. Höchstens zwei Versuche pro Produkt, 60 Sekunden pro Versuch und 15 Minuten je Lauf. Die Sperrtaste oder STOPP hält den Lauf an.
4. Ergebnisse werden vor dem nächsten Produkt lokal gespeichert. Am Ende öffnet Bob Handy den Browser zur Übertragung. Ein Timeout lässt die Ergebnisse gespeichert. **Gespeicherten Listenlauf an Bob übertragen / erneut versuchen** wiederholt die Übertragung. **Unterbrochenen Listenlauf fortsetzen** prüft nur noch unvollständige Produkte mit einem neuen begrenzten Versuchskontingent.
5. Im Bob-Bereich DEGIRO zeigt **Morgenliste automatisch lesen** Ergebnisse, fehlende Felder und Fehler. Die private KI-Diagnose enthält zusätzlich `androidReader` mit den letzten fünf gespeicherten Versionen.

Die Übertragung bestätigt eine konkrete Laufkennung und Speicherversion; ein älterer Beleg löscht keine neueren Ergebnisse. Serverdaten liegen in `bob_android_read_runs`, getrennt von Marktpreisen, Produktfreigaben und Simulationseingaben. Gelesene Bildschirmwerte bleiben ungeprüfte Beobachtungen. Ein gelesener Kurs ist keine Order oder Ausführung.

Die Navigation nutzt sichtbare Accessibility-Texte, Suchfelder und exakte ISIN-Treffer. Unzugängliche oder mehrdeutige Oberflächen werden mit einem Grund protokolliert; Bob errät keine Bildschirmkoordinaten. Login- und Orderansichten stoppen den Lauf. Ein realer Samsung-/DEGIRO-Gesamtlauf muss nach Installation auf dem Gerät geprüft werden; CI ersetzt diesen Gerätetest nicht.
