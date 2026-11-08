# Bob einen Weg zeigen

1. DEGIRO einmal entsperren. Die lokale PIN-Einrichtung bleibt vom Lernen getrennt.
2. In Bob DEGIRO wählen. **Bob etwas beibringen → Ablauf vormachen und lernen → Vormachen starten**.
3. Den gewünschten Weg normal antippen und Text eingeben. Nach jedem Schritt auf die neue Ansicht warten.
4. Über die Android-Appübersicht zu Bob zurückkehren. Die Aufzeichnung endet automatisch.
5. Bob zeigt eine kurze Zusammenfassung und schlägt einen Namen vor. **Speichern und testen** startet den Prüflauf. **Nur speichern** bewahrt den Entwurf ohne Ausführung auf.
6. Bei einer Rückfrage einen erkannten Ergebnistext antippen. Alternativ **Screenshot / Text → Screenshot als Ergebnis auswählen**, passenden Text wählen und **Senden**. Es müssen keine Befehlszeilen oder JSON bearbeitet werden.
7. Später: **Bob etwas beibringen → Gespeicherten Ablauf laden**, dann starten. Erst nach erfolgreichem Prüflauf verwendet Bob den Weg als bestätigte Erfahrung.

Eindeutige neue Texte übernimmt Bob wie bisher. Ein nach einem Suchklick eindeutig geöffnetes Suchfeld und ein nach dem Tippen ausgewähltes Favoritenregister werden jetzt direkt als überprüfbare Ergebnisse gespeichert. Mehrdeutige Texte erfordern eine Auswahl; sie werden nicht willkürlich automatisch gewählt.

Grenzen: zwölf Schritte, drei Minuten, nur die ausgewählte App. Bei unvollständiger Aufzeichnung wird kein scheinbar vollständiger Ablauf angeboten. Unbeschriftete Symbole müssen über die bestehende Screenshot-Symbolfunktion erklärt werden. Keine PIN-Aufzeichnung, Orders oder Zahlungen. Aufnahme und Vorschläge bleiben lokal; keine automatische kostenpflichtige KI. Ein gespeicherter Entwurf ist kein erfolgreicher Funktionstest.

## Wenn die Zusammenfassung nicht erscheint

Auf Bobs Hauptseite gibt es **Aufzeichnung beenden / ansehen**. Dieser Knopf beendet eine noch laufende Aufnahme und öffnet den letzten lokalen Entwurf erneut. Der Entwurf bleibt auch nach Schließen des Fensters und einem App-Neustart erhalten. Er wird erst nach erfolgreichem Speichern oder beim Start einer neuen Aufnahme ersetzt.

Bei null erkannten Schritten erscheint eine Erklärung statt eines leeren oder fehlenden Fensters. Eine geschützte Ansicht, ein beendeter Dienst oder eine unvollständige Aufnahme darf nicht als erfolgreicher Lernvorgang gelten. Die gespeicherten Entwürfe sind lokal und noch nicht als erfolgreich geprüfte Abläufe freigegeben.

## Umfangreiche Ansichten

„Bildschirm zu komplex“ bezog sich auf Android-Bildschirmelemente, nicht auf die Zahl vorgemachter Schritte. Die frühere Grenze lag bei 400 gelesenen Elementen, 100 direkten Kindern und 30 Ebenen. Ein gemeinsamer, nicht rekursiver Leser unterstützt nun bis zu 4096 Elemente, 1024 direkte Kinder und 80 Ebenen. Die ganze Ansicht muss lesbar bleiben; bei Überschreitung oder einem während des Lesens verschwundenen Kind wird kein Teilbaum als sichere Grundlage für Klicks verwendet. Die gleichen Grenzen gelten für die Prüfung von Vormach-Ereignissen und Screenshots. Fehlermeldungen nennen jetzt den konkreten Grund. Die Aufnahmegrenze von zwölf Schritten bleibt unverändert.
