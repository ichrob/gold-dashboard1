# SnapTrade-Historie und Gerätenachweise – 26.10.2026

## Behobener Importfehler

Der Test mit der privaten Originalhistorie (12.599 eindeutige Buchungen) reproduzierte einen Abbruch bei 7.000 Buchungen durch das bisherige Journal-Limit. Die früheren vereinfachten Testdaten bildeten die tatsächliche Größe der Datensätze nicht ab.

Eine verlustfreie Spaltencodierung teilt wiederholte Feldnamen. Originalwerte, fehlende Felder, Nullwerte, Identitäten und Zeitstempel bleiben erhalten. Die 12.599 Einträge benötigen damit etwa 2,75 MB statt 4,38 MB kompaktem JSON. Das Journal-Limit von 3 MB, das Archiv-Limit von 4 MB und die verschlüsselte Transportgrenze von 900 KB bleiben bestehen. Zusätzlich ist die expandierte Arbeitsdarstellung auf 8 MB begrenzt. Alte Archive bleiben lesbar; bestehende Teilimporte werden fortgesetzt, sofern Anbieterzahl und Fingerabdruck unverändert sind.

Die private Historie wurde lokal vollständig durch alle sieben begrenzten Abrufzyklen verarbeitet und nach jedem Speichern neu geladen. Ergebnis: 12.599 eindeutige Einträge, vollständiger Durchlauf, identische Werte nach jedem Speicher-/Ladezyklus. Keine privaten Buchungen oder Kontokennungen werden veröffentlicht. Dieser Offline-Nachweis ersetzt noch keine vollständige Speicherung auf dem Live-Dienst.

## Gerätenachweise

Drei vorhandene Handy-Screenshots erneut visuell geprüft. Sie zeigen eine SHORT-Frühwarnung und deren Rücknahme sowie eine LONG-Frühwarnung in der Android-Benachrichtigungsleiste; zwei Bilder zeigen dieselbe LONG-Nachricht und zählen nicht als zwei Zustellungen. Die Kurszeitstempel passen zu den vorhandenen Versandprotokollen. Das bestätigt diese drei konkreten Anzeigen, nicht sämtliche Benachrichtigungskategorien oder dauerhafte Zustellbarkeit. Die bestehende enge Abnahme von Diagnoseziel 69 wird dadurch bestätigt, nicht pauschal erweitert.

Drei spätere signierte Browser-Anzeigerückmeldungen liegen ebenfalls vor. Es fehlen weiterhin unabhängige Nachweise zur aktuell installierten Android-Version, Spracherkennung, lokalen Freigaben/STOPP, OCR-Teilen und aktueller Navigation. Der Server hat keine authentifizierte Fernkopplung zum Samsung. Keine künstlichen Pushs versandt, keine Telemetrie erfunden.

## Prüfung

145 SnapTrade-Tests erfolgreich (ein lokaler Datenbank-Skip); fünf Push-Rückmeldungstests erfolgreich. Zusätzliche Tests decken realistisch große Buchungszeilen, verschlüsselten Neustart, alte Teilarchive, beschädigte Spaltendaten, Zeilen- und Größenbegrenzungen sowie die exakte Erhaltung fehlender/null/leerer/Null-Werte ab. Live-Vollständigkeit erst bei gespeicherter Historie, eindeutiger Anbieter-Gesamtzahl, null Identitätskonflikten und `complete=true` bestätigen.

Aufgabe 5 (direkter DEGIRO-Abgleich) bleibt ausgeschlossen.
