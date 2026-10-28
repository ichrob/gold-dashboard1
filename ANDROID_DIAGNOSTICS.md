# Bob Handy: automatische Diagnose

Standardmäßig ausgeschaltet. In Bob Handy **Automatische Diagnose verbinden / Freigabe öffnen** wählen, zustimmen und im angemeldeten Bob-Browser den angezeigten Vergleichscode prüfen und **Dieses Handy für Diagnose freigeben** drücken. Bei nötiger Anmeldung öffnet der Link einen neuen Tab; danach zum Freigabetab zurückkehren. In Bob Handy zeigt erst eine bestätigte Statusübertragung „Verbunden“.

Die App erhält Internet-, Netzwerkstatus- und Neustartberechtigung für diesen Zweck. OCR bleibt auf dem Gerät. Gesendet werden ausschließlich App-Version, Dienststatus, Lauf-/Speicherstatus und der letzte feste Fehlercode mit Zeitangabe. Keine ISINs, Kurse, Bildschirmtexte, Bilder, Passwörter oder Kontowerte. Dies ist keine Fernsteuerung; der Diagnoseschlüssel kann keine Listen laden, Daten lesen, Bedienhandlungen auslösen oder Orders senden.

Der zufällige Geräteschlüssel ist lokal mit Android Keystore verschlüsselt. Nur sein SHA-256-Hash gelangt zur Browserfreigabe und in die Datenbank. Freigaben gelten höchstens 90 Tage. Die HTTPS-Zieladresse ist fest; Umleitungen werden nicht verfolgt. Lokales Abschalten beendet weitere geplante Sendungen. Ein bereits laufender Versand kann noch eintreffen. Auf der Freigabeseite lassen sich alle Diagnoseschlüssel serverseitig widerrufen; dazu ist eine Bob-Anmeldung erforderlich.

Statusänderungen planen eine Übertragung; ein persistenter Android-Job plant zusätzlich Meldungen im 15-Minuten-Raster. Android darf die Ausführung wegen Energiesparen, fehlendem Netz oder App-Stopp verzögern. Es gibt keine garantierte Echtzeitverbindung. Der Dienststatus gilt ausdrücklich für den meldenden App-Prozess. Der Server zeigt Empfangszeit und Frische getrennt; alte Meldungen beweisen keinen aktuellen Zustand.

Es wird der neueste Status mit dem letzten bekannten Fehler gespeichert, kein vollständiges Ereignisjournal. Die bestehenden Listenprotokolle und Produktergebnisse bleiben im bisherigen, getrennten Übertragungsweg. Die Diagnosefunktion bestätigt nicht automatisch deren Übertragung oder einen erfolgreichen Produktleselauf.
