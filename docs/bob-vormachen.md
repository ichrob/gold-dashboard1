# Bob einen Weg zeigen

1. DEGIRO einmal entsperren. Die lokale PIN-Einrichtung bleibt vom Lernen getrennt.
2. In Bob DEGIRO wählen. **Bob etwas beibringen → Ablauf vormachen und lernen → Vormachen starten**.
3. Den gewünschten Weg normal antippen und Text eingeben. Nach jedem Schritt auf die neue Ansicht warten.
4. Über die Android-Appübersicht zu Bob zurückkehren. Die Aufzeichnung endet automatisch.
5. Bob zeigt eine kurze Zusammenfassung und schlägt einen Namen vor. **Speichern und testen** startet den Prüflauf. **Nur speichern** bewahrt den Entwurf ohne Ausführung auf.
6. Bei einer Rückfrage einen erkannten Ergebnistext antippen. Alternativ **Screenshot / Text → Screenshot als Ergebnis auswählen**, passenden Text wählen und **Senden**. Es müssen keine Befehlszeilen oder JSON bearbeitet werden.
7. Später: **Bob etwas beibringen → Gespeicherten Ablauf laden**, dann starten. Erst nach erfolgreichem Prüflauf verwendet Bob den Weg als bestätigte Erfahrung.

Eindeutige neue Texte übernimmt Bob wie bisher. Ein nach einem Suchklick eindeutig geöffnetes Suchfeld und ein nach dem Tippen ausgewähltes Favoritenregister werden jetzt direkt als überprüfbare Ergebnisse gespeichert. Mehrdeutige Texte erfordern eine Auswahl; sie werden nicht willkürlich automatisch gewählt.

Voreinstellung: zwölf Schritte, drei Minuten, nur die ausgewählte App; Länge und Dauer können in Bob-Einstellungen innerhalb der sicheren Gerätegrenzen verändert werden. Bei unvollständiger Aufzeichnung wird kein scheinbar vollständiger Ablauf angeboten. Unbeschriftete Symbole müssen über die bestehende Screenshot-Symbolfunktion erklärt werden. Keine PIN-Aufzeichnung, Orders oder Zahlungen. Aufnahme und Vorschläge bleiben lokal; keine automatische kostenpflichtige KI. Ein gespeicherter Entwurf ist kein erfolgreicher Funktionstest.

## Wenn die Zusammenfassung nicht erscheint

Auf Bobs Hauptseite gibt es **Aufzeichnung beenden / ansehen**. Dieser Knopf beendet eine noch laufende Aufnahme und öffnet den letzten lokalen Entwurf erneut. Der Entwurf bleibt auch nach Schließen des Fensters und einem App-Neustart erhalten. Er wird erst nach erfolgreichem Speichern oder beim Start einer neuen Aufnahme ersetzt.

Bei null erkannten Schritten erscheint eine Erklärung statt eines leeren oder fehlenden Fensters. Eine geschützte Ansicht, ein beendeter Dienst oder eine unvollständige Aufnahme darf nicht als erfolgreicher Lernvorgang gelten. Die gespeicherten Entwürfe sind lokal und noch nicht als erfolgreich geprüfte Abläufe freigegeben.

## Umfangreiche Ansichten

„Bildschirm zu komplex“ bezog sich auf Android-Bildschirmelemente, nicht auf die Zahl vorgemachter Schritte. Die frühere Grenze lag bei 400 gelesenen Elementen, 100 direkten Kindern und 30 Ebenen. Ein gemeinsamer, nicht rekursiver Leser unterstützt nun bis zu 4096 Elemente, 1024 direkte Kinder und 80 Ebenen. Die ganze Ansicht muss lesbar bleiben; bei Überschreitung oder einem während des Lesens verschwundenen Kind wird kein Teilbaum als sichere Grundlage für Klicks verwendet. Die gleichen Grenzen gelten für die Prüfung von Vormach-Ereignissen und Screenshots. Fehlermeldungen nennen jetzt den konkreten Grund. Die Aufnahmegrenze von zwölf Schritten bleibt unverändert.

## Besitzersteuerung und unveränderter Hochschutz

Unter **Einstellungen** in Bob Handy legt der Besitzer die Anzahl der Schritte (1–48), die maximale Ausführungs-/Aufzeichnungsdauer (1–15 Minuten), die Wartezeit pro Schritt (10–120 Sekunden) und die maximale Zahl lokal gespeicherter Abläufe (1–200, standardmäßig 100 statt zuvor 20) fest. Standard bleibt 12 Schritte / 3 Minuten / 20 Sekunden. Die Einstellung gilt für neu begonnene Sitzungen; Änderungen stoppen laufende Aufträge, damit keine alte Ausführung mit anderen Grenzen weiterläuft.

Diese Regler **sind keine Sicherheitsfreigaben**. Geschützte Anzeigen (PIN, Passwort, Kauf/Verkauf, Order, Zahlung usw.), Gerätesperre, ausgewählte App, manuelles STOPP, einmalige Aktion ohne unbestätigten Wiederholungsklick und KI-Freigabe pro App gelten unverändert. Die externe KI darf weiter höchstens zwölf geprüfte Navigationsschritte vorschlagen; längere Abläufe sind nur lokale Besitzerpläne bzw. vorgemachte und geprüfte Schritte. Kein allgemeines Einverständnis wird als automatische Order-, Zahlungs-, Berechtigungs- oder Datenfreigabe behandelt.

Bob führt eindeutig machbare, lokal autorisierte Bedienaufträge ohne zusätzliche Bestätigung aus. Bei einer Schutzgrenze benennt er die konkrete Sperre, statt sie zu umgehen. Ein aufgezeichneter Entwurf allein belegt keine erfolgreiche Wiederholung.

## Hochschutz · Besitzerverwaltung

Unter **Einstellungen → Hochschutzregeln verwalten** stehen dem Besitzer zusätzliche, lokale Datenschutz- und Ausführungsoptionen zur Verfügung.

- **Allgemeine App-Aufträge nur lesen**: Stoppt automatische Klick-/Schreib-Abläufe der generischen Bedienhilfe. Die manuell gestartete Aufzeichnung kann weiter beobachten, wie der Besitzer selbst tippt. Dieser Schalter gilt nicht für den gesonderten DEGIRO-Produktleser.
- **Externe KI-Hilfe abschalten**: Verhindert die KI-Anfrage der allgemeinen Bedienhilfe auch dann, wenn die betreffende App zuvor für KI freigegeben war. Erneutes Einschalten des Schalters stellt niemals fehlende App-Freigaben her.
- **Alle KI-App-Freigaben widerrufen**: Entfernt nach einer gesonderten Bestätigung sämtliche bisherigen Google-KI-Freigaben der allgemeinen Bedienhilfe. Gespeicherte lokale Abläufe bleiben erhalten.

Änderungen werden erst über **Speichern** übernommen, gelten nur auf dem eigenen Handy und stoppen einen noch laufenden generischen Auftrag. Das Zurückschalten der zusätzlichen Einschränkungen kann niemals Passwort-/PIN-Ansichten, Echtgeldorders, Zahlungsfunktionen oder Systemberechtigungen freigeben. Jene Sperren sind unabhängig von den Besitzeroptionen und bleiben aktiv. Es gibt keine pauschale Freigabe für zukünftige sensible Einzelaktionen.

## Schutzwahl des Besitzers: fünf feste Regeln

Nach der Auswahl vom 8. November 2026 sollen **nur die bisherigen Nummern 2, 3, 5, 6 und 7** in der Besitzerübersicht als dauerhaft festgelegte Hochschutzpunkte erscheinen:

- **2** Keine selbstständigen Überweisungen oder Zahlungen.
- **3** Keine Weitergabe von Passwörtern, PINs oder TANs; die autorisierte lokale PIN-Anmeldung bleibt gesondert möglich.
- **5** Keine Aufnahme/Auswertung geschützter Bildschirme.
- **6** Keine eigenmächtige Änderung von Systemrechten, App-Installation oder Löschung fremder Daten.
- **7** Keine mehrdeutigen Klicks oder blinden Wiederholungen unbestätigter Aktionen.

Die früheren Nummern **1, 4 und 8** sind in der Anzeige keine vom Besitzer gewählten *zusätzlichen* festen Hochschutzpunkte mehr. Sie sind jedoch **nicht durch diese Auswahl technisch freigeschaltet**: Für (1) existiert keine freigegebene Echtgeldorder-Ausführung; (4) die Android- oder Kontosperre darf nicht umgangen werden, normale autorisierte Anmeldung ist zulässig; (8) externe KI-Hilfe benötigt weiterhin die App-Freigabe und darf keine privaten Konto-/Zugangsdaten ohne Erlaubnis versenden. Diese unabhängigen gesetzlichen, technischen und Datenschutz-Voraussetzungen bleiben wirksam.

Die Liste ist eine Klarstellung der Besitzerwahl, kein Ausführungsschalter. An den vorhandenen Sicherheitsprüfungen wurde dadurch nichts verändert.
