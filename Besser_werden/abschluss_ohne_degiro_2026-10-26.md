# Bearbeitung der offenen Aufgaben – 26.10.2026

Auftrag: Aufgaben 1–4 und 6–12 bearbeiten; direkten DEGIRO-Abgleich (5) ausnehmen.
Stand: Änderungen in PR #936 veröffentlicht; CI und Live-Abnahme werden durchgeführt.

| Nr. | Ergebnis | Noch erforderlich |
| --- | --- | --- |
| 1 | Genau die 13 besprochenen Altfälle erhalten den administrativen Status „Geschlossen – mangels historischer Daten nicht rekonstruierbar“. Zuordnung über feste, gehashte zusammengesetzte Fallkennungen; alle 13 gegen die tatsächliche private Stichprobe abgeglichen. Keine pauschale Schließung neuer Fälle. | Veröffentlichung und Live-Abgleich der Anzeige und Diagnosezähler. |
| 2 | Ungeklärte Fälle zählen künftig nicht mehr als bestätigte Produkt-Ergebnisse. Alte Tageszähler werden in der Berichtsausgabe um zuvor mitgezählte spätere Modellverkäufe bereinigt; Rohdaten und virtuelles Guthaben bleiben erhalten. Unplausible Zähler sperren die Trefferquote. | Datenbank-Integrationstest in CI und Live-Abnahme. |
| 3 | Automatische Löschung der Falldetails nach 30 Tagen entfernt. Neue Ereignisse speichern zusätzlich die empfangenen Kurs-/Analysezeitstempel und Aktualitätsmerkmale. Original-Einstieg, Kursquelle, Ausstiegsereignisse und Kostenmodell bleiben im bestehenden Ledger erhalten. | Veröffentlichung; tatsächliche neue Ein-/Ausstiege anschließend auf Vollständigkeit prüfen. Nicht vorhandene Altdaten werden nicht wiederhergestellt. |
| 4 | Datenübergabe mit vorhandenen Regressionstests geprüft; neue Ereignisnachweise erlauben die Unterscheidung zwischen Quellalter und Verarbeitung. Aktuelle fünf Profile hatten frische Eingänge. | Alte Ursache bleibt ohne damalige Worker-Daten unbewiesen. Künftige Ereignisse auf Quelle, Analyse und Worker-Zeit abgleichen. |
| 5 | Vom Auftrag ausgenommen. | Kein Bestandteil dieses Änderungspakets. |
| 6 | SnapTrade-Historie kann über mehrere begrenzte Abgleiche fortgesetzt werden. Maximal fünf Historienseiten pro Durchlauf; bekannte unvollständige Historie wird bei einem Konto nach frühestens zehn Minuten fortgesetzt. Kopf-Fingerabdruck und Gesamtzahl verhindern das Vermischen offensichtlich geänderter Listen. Doppelte Einträge können keinen Vollständigkeitsnachweis erzeugen. Leere optionale Platzhalter entfallen; bestehende Speicher- und Transportgrenzen bleiben erhalten. | Veröffentlichung und tatsächliche vollständige Übernahme prüfen. Anbieter-Tagesdaten bleiben Tagesdaten; vollständige Anbieterhistorie beweist keine Vollständigkeit vor deren Startdatum. Tests mit 12.599 synthetischen Originalkennungen sind kein Live-Import. |
| 7 | Bereits vorhandene signierte Browser-Rückmeldungen und Push-Tests geprüft. In der Live-Stichprobe zwei bestätigte Browser-Anzeigen. | Android-Benachrichtigungsanzeige und sämtliche Push-Kategorien sind damit nicht unabhängig bewiesen. Kein künstlicher Push versandt. |
| 8 | DMI erkennt die beobachtete XAUS-Stundenkerzenpause Freitag 16 Uhr bis Sonntag 18 Uhr New York, einschließlich Zeitumstellung. Fehlende echte Handelsstunden, fremde Quellen und veraltete Daten bleiben gesperrt. Die Originalquelle bestätigte die Wochenendgrenzen am 16./18. und 23./25. Oktober. | Veröffentlichung und frischen DMI-Livewert prüfen. Keine erfundenen Kerzen und keine Änderung der Handelsfreigabe. |
| 9 | Die Warnungen betreffen die alternativen XAUS-Quellen für 1m/5m. Die verwendeten BiQuote-Quellen waren aktuell. | Externe Verzögerung der Ersatzquelle bleibt sichtbar; kein Nachweis einer Reparatur dieser Quelle. |
| 10 | Ursache geklärt: Der aktive Forschungszyklus hat noch keinen Kandidaten mit hinreichendem historischem Vorteil. Die Selbstprüfung erklärt nun diese Voraussetzung, statt nur einen fehlenden Kostenvergleich zu nennen. Vergleichs- und Kostentests bestehen. | Geeigneten Kandidaten einfrieren und unabhängige spätere Daten sammeln. Keine erfundenen Sitzungen, Trades oder Strategieerfolge. |
| 11 | Beibehaltene öffentliche Videos fragen fehlende Veröffentlichungsmetadaten erneut unabhängig von Untertiteln ab. Echter OCR-Bildtest ohne Netzwerk bestanden. | Zugang zu Mitgliedervideos, fehlende Original-Veröffentlichungszeiten und unabhängige Prüfung realer Video-Chartwerte bleiben erforderlich. Keine Umgehung von Zugangsbeschränkungen. |
| 12 | Gesamttests und aktuelle Betriebsstichprobe geprüft. Keine pauschale Aufwertung von 94 unbestätigten Diagnosezielen. | CI-Datenbankprüfungen, Veröffentlichung und individuelle Live-/Geräte-/Dauernachweise. |

## Prüfung

- PostgreSQL-CI: 2.224 Python-Tests erfolgreich, keine Skips. Der erste Browserlauf fand eine veraltete Texterwartung; diese wurde angepasst.
- Lokaler Gesamtlauf: 2.223 Python-Tests, erfolgreich, 80 lokale Skips wegen zusätzlicher Testvoraussetzungen; keine vollständige Datenbankabnahme.
- Nach letzter Speicheroptimierung und zusätzlichem Duplikat-Test: 104 gezielte Tests erfolgreich, ein Datenbanktest lokal übersprungen.
- Alle 139 JavaScript-Testdateien erfolgreich.
- Isolierter OCR-Lauf: 11 Tests, erfolgreich, ein Datenbanktest übersprungen. Netzwerkverbot wurde vor Import in Eltern- und Kindprozess geprüft; der echte Bildtest lief.
- Render-Stichprobe: Ressourcen unter den konfigurierten Grenzen, aber kein Dauerstabilitätsnachweis. Zwischen 19:10 und 19:19 UTC keine Fehler in der abgefragten Fehlerlog-Auswahl. Frühere Logs enthalten unter anderem Datenbank-Timeouts und einen Deadlock; deren Nichterneutauftreten ist keine bestätigte Ursachenbehebung.

## Veröffentlichung

Der Nutzer hat Upload, PR und Veröffentlichung nach erfolgreicher CI ausdrücklich freigegeben. Der aktuelle Main-Stand einschließlich PR #935 wurde konfliktfrei übernommen. Veröffentlichung und Live-Abnahme stehen noch aus.

Vor Veröffentlichung: aktuellen Main-Stand erneut abgleichen, CI einschließlich PostgreSQL bestehen lassen, anschließend beide Render-Dienste und die konkreten neuen Diagnosefelder prüfen. Bis dahin gelten alle Codekorrekturen als lokal vorbereitet, nicht als live behoben.
