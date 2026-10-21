# Produktbilder: Erkennung und Wiederprüfung

Stand: 6. Oktober 2026. Der echte Android-Ablauftest ist ausdrücklich auf den 7. Oktober verschoben und noch nicht durchgeführt.

## Verhalten

- Feldbezogene Ausschnitte: Basispreis und KO getrennt von Datum; zusätzliche Ausschnitte für Bezugsverhältnis, Hebel, Geld und Brief bei unsicheren Lesungen. Eindeutige Feldgeometrie und übereinstimmende Lesungen erforderlich.
- Bei unsicheren Zahlen im Produktimport werden nur diese Werte ausgelassen. Bestätigte andere Felder und bisher gespeicherte Nachweise bleiben erhalten. Geld/Brief werden als zusammengehöriges Paar behandelt; keine Mischung mit alten Kursseiten.
- Eine Bildauswahl bleibt eine Aufnahmeserie. Sichtbare Originalzeiten werden nicht ersetzt. Fehlende Zeiten können innerhalb derselben ISIN bei maximal 90 Sekunden Abstand der Quellenzeiten mit der frühesten Zeit der Serie ergänzt werden; dieser Zeitbezug bleibt als abgeleitet gekennzeichnet. Bedingungsdaten werden nicht durch Kurszeiten erneuert.
- Zuordnung eines Bildes bedeutet nicht vollständige Produktdaten. Anzeige: Dateien zugeordnet, Werte teilweise übernommen, verbleibende Anforderungen mit Fundort und Emittentenlink. Datenübermittlung komplett wird separat aus der Produktprüfung ermittelt.

## Originaldateien

Neue Produktuploads einschließlich PDF werden als Originalbytes in IndexedDB auf demselben Gerät gespeichert: maximal sieben Tage und insgesamt 100 MB, älteste Dateien werden bei Bedarf entfernt. Keine Übertragung an einen neuen Dienst. Speicherfehler werden angezeigt und blockieren die Erkennung nicht. Bereits vor Einführung dieser Funktion hochgeladene Originale können nicht rückwirkend gespeichert werden.

Einträge enthalten ISIN, Aufnahmeserie, ursprünglichen Zuordnungskontext, Dateiname, Dateityp und Erkennungsversion. Nach einem Versionswechsel prüft Bob passende gespeicherte Serien einmal neu, sobald die App sichtbar ist und das Produkt in der Liste vorhanden ist. Eine unterbrochene Serie wird vollständig wiederholt. Die manuelle Wiederprüfung ist unabhängig davon verfügbar. Löschen der Originale entfernt nicht bereits erkannte Produktdaten.

Bei künftigen Änderungen der Erkennung `PRODUCT_OCR_VERSION` erhöhen. Wiederprüfung verändert weder Quellenzeiten noch die Gültigkeitsregeln. Ältere datierte Stammdaten und ältere Kurse überschreiben keine neueren Nachweise. Keine automatische Handelsfreigabe durch die Wiederprüfung allein.

## Automatisierte Prüfung

`node test_sg_numeric_ocr.js` umfasst Original-OCR-Fixtures, Feldkonflikte, Datum/WKN-Prüfung und `test_resilient_import.js`. Letzterer prüft Originalbytes, Speicherung, Ablauf/Größenlimit, Speicherfehler, ISIN-/Serientrennung, einmalige Wiederprüfung, unvollständig bearbeitete Serien, Teilimporte und Zeitbezüge. Weitere Regressionen: Auswahl, manuelle Importe und Screenshot-Status.

## Für den Android-Test am 7. Oktober

1. Mehrere SG-/BNP-Bilder einschließlich eines unvollständigen Bildes auswählen.
2. Gezielte Fehlwertanzeige, erhaltene sichere Werte und Produktzuordnung prüfen.
3. App schließen/öffnen und gespeicherte Originale erneut prüfen, ohne Galerieauswahl.
4. Eigene Zeitstempel und unveränderte ältere Kursnachweise kontrollieren.
5. Originale löschen und prüfen, dass Produktdaten erhalten bleiben.


## DEGIRO-Listenlayout (21. Oktober 2026)

Der Listenimport verwendet nun ein festes Leseschema für SG-/BNP-Goldprodukte.
Jede Produktzeile wird anhand ihrer Überschrift im Originalbild ausgeschnitten,
vergrößert und unabhängig gelesen. Zwei vollständige Lesungen müssen bei ISIN,
Richtung, Barriere, Basispreis, Verhältnis, Handelsplatz und Währung übereinstimmen.
Bei Unsicherheit folgen eine andere Segmentierung und eine Version ohne
Bildglättung. Prüfziffern dienen der Kontrolle, nicht dem Erraten einer Kennung.

- SG/BNP: Emittent; Gold: Basiswert; Long/Call und Short/Put: Richtung.
- BAR/SL: Barriere; BP/STR: Basispreis. Bei Mini-Produkten bleiben unterschiedliche Werte getrennt.
- Bv/R: angezeigter Verhältnisnenner, etwa 10 für 0,1. Kein Hebel und kein Kurs.
- LV: nur ausdrücklich angezeigter Hebel. Laufzeitdatum und Open End bleiben getrennt.
- ISIN: vollständige Produktkennung mit Prüfziffer. Keine feste Liste alter Produkte oder Zahlen.
- OTC-Zeile: Handelsplatz und EUR/CHF des unmittelbar darüberstehenden Produkts.
- K/V: Bedienknöpfe, keine Kurse, keine Orderbestätigung. Kontostand, Navigation
  und Telefonuhr werden nicht als Produktwerte oder Kurszeiten übernommen.

Dateien werden einzeln gelesen. Scrollüberlappungen werden anhand identischer
Produktdaten zusammengeführt; widersprüchliche Doppelzeilen blockieren die
Ersetzung. Eine abgeschnittene letzte Zeile ohne Kennung/Handelsplatz wird nicht
an die nächste Datei angehängt. Ab 13 Produkten wird nicht still gekürzt.
Bei Lesefehlern bleibt die alte gespeicherte Liste erhalten.

Der strukturierte Listennachweis bleibt mit Originalbildreferenz im Listenarchiv
und wird auf der Produktkarte angezeigt. Er bestätigt den gelesenen Eintrag,
keinen ausführbaren Brokerkurs. Uploadzeit bleibt Uploadzeit; Kurse und
Handelsfreigabe werden weiter separat geprüft.

Prüfung: `node test_degiro_list_reader.js`, bestehende Import-/Tabellentests und
lokale OCR-Wiederholung der beiden Nutzeroriginale. Private Originalbilder und
deren vollständige OCR-Texte werden nicht ins öffentliche Repository übernommen.
