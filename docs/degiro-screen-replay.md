# Bildschirm-Ablauftest: erster kleiner Machbarkeitsversuch

Der vorhandene Offline-Simulationsknopf führt zusätzlich einen synthetischen
Bildschirmablauf aus: eindeutiges Suchergebnis → passende Produktdetailseite →
Kursbeobachtung. Das Modul gibt ausschließlich beschreibende Vorschläge zurück.
Es besitzt keinen Browser-, Handy-, Netzwerk- oder Orderadapter.

## Nachgewiesener Umfang

`python -m unittest test_degiro_screen_replay test_degiro_sandbox -v`

Prüft eindeutige Identität, Reihenfolge, Aktualität der Bildschirmbeobachtung,
Doppelbilder, widersprüchliche Kurse, Währung und sofortigen Abbruch bei
Anmeldung, Ordermaske, Bestätigung oder Sicherheitsabfrage. Höchstens 20
normalisierte Beobachtungen je Aufruf; nach einem Abbruch keine Fortsetzung.
Ein erneuter Aufruf ist ein separater Offline-Test, keine Freigabe zur Bedienung.

Zeitwerte sind numerische Sekunden einer einheitlichen Uhr. `observedAt` ist
Bildschirmaufnahmezeit und `receivedAt` Empfangszeit, ausdrücklich keine
Originalzeit des Geld-/Briefkurses. Die ISIN im Test ist eine künstliche Kennung.
Die Auswertung prüft die Übereinstimmung, nicht die ISIN-Prüfziffer.

## Nächster messbarer Versuch

Eine kurze, vom Nutzer aufgezeichnete Bildschirmfolge lokal normalisieren und
manuell beschriften. Die Erkennung getrennt gegen diese Beschriftung vergleichen:
richtige Seite, genaue Identität, Geld/Brief, Währung, Originalkurszeit soweit
angezeigt sowie unbekannte Dialoge. Anschließend dieselbe Folge offline
wiedergeben und Fehlerfälle durch Austausch einzelner Beobachtungen prüfen.
Private Originale gehören nicht in das öffentliche Repository.

Erst dies kann eine Aussage über reale Bilderkennung ermöglichen. Der aktuelle
Test bestätigt weder OCR-Qualität noch die Bedienung einer echten DEGIRO-Sitzung,
Brokerzustimmung, kontinuierliche Kurse oder Ausführbarkeit. Es gibt keine
Tarnung, künstliche menschliche Bewegung, Sitzungserhaltung oder Liveorders.
Keine neue Abhängigkeit, kein Dienst, kein Hintergrundjob und keine API-Gebühr.

## Stichprobe mit privaten Originalbildern am 12.11.2026

Zwei vorhandene ältere Originale wurden visuell geprüft, nicht veröffentlicht.
Die Listenaufnahme stimmt bytegenau mit einer vorhandenen SHA-256-Referenz
überein; fünf vollständige Zeilen stimmen in ISIN, Währung, Barriere, Basispreis
und Verhältnis mit der Referenzauswertung überein. Eine angeschnittene Zeile
bleibt unvollständig. Dies prüft den Referenzabgleich, keine neue Listen-OCR.

Die separate Detailaufnahme wurde lokal mit Tesseract (PSM 6) gelesen und durch
Bobs unveränderten `parseDegiroDisplayedQuote` verarbeitet. ISIN, Geld, Brief,
Währung, Handelsplatz und sichtbare Anzeigezeit stimmen mit der visuellen
Kontrolle überein. Eine falsche Ziel-ISIN sowie veränderte Eingaben mit
Geld > Brief, fehlendem Brief oder fehlender Zeit wurden jeweils abgewiesen.
`isExecutableQuote` bleibt false. Die Anzeigezeit ist keine separate Geld-/Briefzeit.
Dieser Versuch testet nicht Android ML Kit oder den Live-Upload.

Die Aufnahmen stammen von unterschiedlichen Tagen und Produkten. Es existiert
für diese Stichprobe daher kein belegter zusammenhängender Such-/Detailablauf;
Aufnahme- und Empfangszeiten wurden nicht erfunden. Kein erfolgreicher kompletter
Original-Replay und keine Navigationsfreigabe werden daraus abgeleitet.

Die Listenprobe zeigte eine unnötige Einschränkung: Der bekannte Zielwert muss
in einer Mehrproduktliste genau einmal vorkommen, nicht der einzige Eintrag
sein. Der Replay-Prüfer akzeptiert jetzt diesen Fall; doppelte oder fehlende
Zielwerte und fehlerhafte Listen bleiben gesperrt.

Validierung: 17 Python-Tests in `test_degiro_screen_replay` und
`test_degiro_sandbox`, `test_degiro_exact_verified_images.js` und
`test_degiro_screen_quote_panel.js` bestanden. Der vollständige Originalablauf
bleibt bis zu einer passenden privaten Aufnahmefolge offen.


## Samsung-Abnahme der Vergleichsanbindung

Voraussetzung: veröffentlichter Build mit `importHandsetReport`, unveränderte
Bob-Handy-App, aktive vom Nutzer geöffnete Lesesitzung und DEGIRO-Anmeldung.
Keine Ordermaske öffnen. Bestehenden Gold-Produktleselauf verwenden; keine
neue Einrichtung oder Wiederholung bereits funktionierender Suchschritte.

1. Einen frischen Produkt-Lesebeleg einschließlich sichtbarer Kurszeit,
   Währung, Handelsplatz, Hebel und KO übertragen. Originale bleiben privat.
2. Im authentifizierten Audit dieselbe ISIN, ursprüngliche Erfassungszeit,
   unveränderte Feldwerte und Übertragungsbestätigung kontrollieren.
3. Bei vorhandenem Rankingkandidaten die Vergleichsansicht öffnen. Geld/Brief,
   Währung und Handelsplatz sollen ohne Abschreiben vorbefüllt sein; Hebel und
   KO stehen als abgelesene Angaben daneben. Bei ABWARTEN keinen Kandidaten
   erzwingen. Neue Beobachtungen dürfen manuelle Korrekturen nicht überschreiben.
4. Die originale Kurszeit mit Datum und Zeitzone selbst prüfen. Die bisherige
   Handy-Anzeige hat nur Minutenpräzision ohne Zeitzone; Aufnahme-/Uploadzeit
   darf dieses fehlende Merkmal nicht ersetzen. Einsatz, Risikobudget und
   Gebühren bewusst eingeben, dann vorhandene Neuberechnung bestätigen.
5. Stückzahl, Modellstopp, CHF-Betrag und Modellverlust gegen dieselbe ISIN,
   frische Markt-/FX-Daten und angezeigte Kurse vergleichen. Nach 90 Sekunden
   oder Produktwechsel muss die alte Beobachtung unbrauchbar werden.

Die automatische Zuordnung ist implementiert; automatische verifizierte
Kurszeitübernahme und reale Samsung-Ende-zu-Ende-Abnahme bleiben offen.
Kein Ausführungsnachweis, keine Order, kein Kauf/Verkauf und keine Stopänderung
an einer realen Position entstehen durch diesen Test.
