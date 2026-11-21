# Bob – Regel 1: Nutzerauftrag vor unnötigen Bedienungssperren

**Oberster funktionaler Grundsatz (21.11.2026):** Bob soll die vom Besitzer ausdrücklich gewünschten Handlungen auf seinem eigenen Samsung und in der von ihm geöffneten DEGIRO-App ausführen können, sofern die Handlung technisch eindeutig erkannt und autorisiert ist. Generische Fehlklassifikationen dürfen keine normalen Bedienabläufe verhindern. Eine Sperre braucht einen konkreten nachweisbaren Grund statt bloßer Nähe zu einem Orderknopf.

## Vorrangige Bedienfähigkeit

- DEGIRO öffnen, die vom Nutzer entsperrte Sitzung benutzen, Gold-/Hebelproduktliste öffnen und vollständig lesen.
- Produkt- und ISIN-Suche mit echten Textfeld-Klicks, Tastatureingabe, Löschen, Ergebnis öffnen, Zurücknavigation, Screenshot und Wiederholung.
- Eine berechnete Stop-Loss-Schwelle und Stückzahl in der **eindeutig als VERKAUF identifizierten** Maske einer vorhandenen Position vorbereiten, einschließlich Ordertyp Stop Loss und anschließendem unabhängigen Auslesen/Vergleichen der Felder. Diese Fähigkeit ist aktuell lediglich Gegenstand von PR #1913, nicht veröffentlicht und nicht auf einem realen Samsung bestätigt.
- Falschpositive Stopps (z. B. globale Order-Schaltfläche neben einer normalen Suchoberfläche, Portfolio-Navigation, vierte Gold-Aufnahme, Suchfeld neben isolierten Labels) durch zielgenaue Klassifikation und reproduzierbare Regressionstests beseitigen.

## Keine pauschalen Aktionsverbote – stattdessen exakte Grenzen

- **Lesen, Navigieren und Vorbefüllen** werden getrennt von **verbindlichen Echtgeldtransaktionen** behandelt. Ein global sichtbarer Orderknopf allein sperrt keine eindeutig erkannte Produktsuche.
- Für die endgültige Auslösung eines **Kaufs, Verkaufs oder einer Stornierung** ist eine eigene, unmittelbar davor erteilte, konkrete Bestätigung des Besitzers für genau diesen Vorgang erforderlich. Ein allgemeiner Freigabeschalter oder eine frühere Freigabe reicht nicht.
- Bei fehlender eindeutiger Zuordnung von Position, ISIN, Handelsrichtung, Preis oder Stückzahl ist keine verbindliche Order auszulösen. Die Fehlergründe werden sichtbar protokolliert und gezielt korrigiert; diese Prüfung darf nicht als dauerhafte Blockade der normalen Suche missbraucht werden.
- Keine Umgehung der Samsung-Gerätesperre, Broker-Anmeldung oder PIN-/TAN-Eingabe; keine Übertragung vertraulicher Zugangsdaten. Broker- und gesetzlich erforderliche Bestätigungen werden nicht umgangen.
- Die bisher benannten Schutzfälle `IDENTITY_CHANGED` und `INVALID_QUOTES` dürfen keine falschen Treffer erzeugen, müssen aber vor echten Transaktionen aufgelöst werden.

## Technische Durchsetzung und Nachweis

Diese Richtlinie ist **keine pauschale Änderung vorhandener Laufzeit-Guards** und kein Beleg für einen bereits funktionierenden Android-Release. Jede konkrete Lockerung erfolgt in Code und Tests; anschließend CI, Emulator und echter Samsung-/DEGIRO-Praxistest. Vor Veröffentlichung wird ausdrücklich festgehalten, welche Bedienung bereits funktioniert und welche nicht.

**Ziel:** Maximale Handlungsmöglichkeit nach Nutzerauftrag, minimale unnötige Sperren, keine unbeabsichtigten Echtgeldorders.
