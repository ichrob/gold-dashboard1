# Ausfallproben, Lernprioritäten und Hinweise

Alle Angaben stehen eingeklappt im Tagesbericht unter Besser werden.

## Ausfallproben

Der Hintergrunddienst führt einmal pro Schweizer Kalendertag und veröffentlichter Version drei isolierte Proben durch: Kursausfall mit Wiederanlauf, fehlgeschlagener Push-Versand mit erneutem Versuch sowie Wiederaufnahme eines gespeicherten Überwachungsstands in einem neuen Python-Prozess. Jeder Testprozess erhält keine Dienstzugangsdaten und hat eine Zeitgrenze. Ergebnisse werden gespeichert. Das sind simulierte Ausfälle mit echten Funktionen, kein absichtlich ausgelöster Produktionsausfall und kein vollständiger Datenbank-/Server-Neustarttest.

## Lernprioritäten

Eine Aufgabe pro Problemklasse: fehlgeschlagene Ausfallproben, Datenlücken, Versandprobleme, mögliche Wiederholungen, unvollständige Kostenbelege, verpasste positive Testfälle. Die Liste wird aus Nachweisen neu berechnet und täglich gespeichert. Die Priorität ist eine feste Sicherheitsreihenfolge und keine behauptete finanzielle Schadenshöhe. Jede Aufgabe enthält einen getrennten Testvorschlag und ein Prüfziel. Bob aktiviert damit keine neue Handelsregel.

## Hinweise

Neue Hintergrundhinweise werden pro Versandversuch ohne Nachrichtentext und ohne Produktnummer gespeichert. Identische akzeptierte Nachrichten an dasselbe Gerät und denselben Trade innerhalb fünf Minuten werden als mögliche Wiederholungen gezählt. Fehlgeschlagene Wiederholungsversuche sind separat.

Technisch rechtzeitig bedeutet Annahme durch den Push-Dienst binnen 30 Sekunden nach Erzeugung. Das ist kein Beleg für Empfang am Handy oder eine fachlich frühzeitige Warnung. Fehlende Zeitstempel bleiben unbekannt. Quellalter wird separat gespeichert. Fachlicher Nutzen, verpasste Warnungen und vermiedene Verluste bleiben ohne unabhängige Ereignis-/Ausführungsnachweise offen. Kritische Warnungen werden nicht unterdrückt. Die Auswertung umfasst höchstens 30 Tage und 10.000 Versuche und kennzeichnet eine abgeschnittene Stichprobe.
