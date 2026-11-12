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
