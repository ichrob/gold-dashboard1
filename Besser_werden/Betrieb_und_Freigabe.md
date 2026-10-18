# Betrieb, Nachweise und Freigabe

Unter „Besser werden“ zeigt „Tagesbericht · Nachweise und nächste Schritte“ den aktuellen Stand. Weitere Angaben sind eingeklappt.

1. **Erfassungsstart:** Eine separate Kontrolle ist für den Vormittag des 19. Oktober 2026 eingerichtet. Sie prüft gespeicherte Messfenster und Originalzeitstempel anhand bestätigter Betriebsdaten. Ein erreichbarer Server allein beweist keine laufende Erfassung.
2. **Tagesbericht:** Gültige, ungültige und fehlende Messfenster sowie ausgewertete Signaltests und offene Folgeergebnisse. Die letzten sieben Kalendertage werden angezeigt; der jeweils neueste Stand pro Tag bleibt in der Datenbank gespeichert. Signaltests sind keine tatsächlichen Gewinne.
3. **Selbstreparatur:** Betriebsfehler werden nach Fehlercode in Episoden zusammengefasst. Bestätigte Reparaturen, offene Episoden, Wiederholungen und Dauer werden getrennt von bloßer Erholung gezählt. Zeitraum: 30 Tage, maximal 10.000 Ereignisse. Testfehlerarten und betroffene Fälle sind separat ausgewiesen. Die Quote ist kein Nachweis einer kausalen Fehlerursache.
4. **Tatsächliche Kosten:** Abgeschlossene Trades benötigen bestätigte Ausführungspreise, Menge, Währung, eindeutige Zeitangaben, Gebühren und CHF-Nettoergebnis. Fehlende Gebühren bleiben unbekannt. Benutzerangaben sind keine unabhängige Brokerbestätigung; unbekannte Slippage wird nicht erfunden.
5. **Marktphasen:** Der Vergleich weist Standard- und Stresskosten, vermiedene negative und verpasste positive Fälle je Marktphase aus. Unbekannte Marktphasen ersetzen keine Nachweise für die drei vorgesehenen Phasen.
6. **Freigabedossier:** Datenabdeckung, unabhängige Prüfung, tatsächlich abgeschlossene Vergleichsfälle, Kostenbelege und ausreichend belegte Marktphasen müssen die angezeigten Bedingungen erfüllen. Auch dann ist persönliche Freigabe erforderlich. Das Dossier dokumentiert einen vorbereiteten Rückkehrablauf, führt aber keinen Regelwechsel und keinen automatischen Rollback aus.

## Speicherung und Kontrolle

Tagesstände und Freigabedossiers werden im bestehenden Hintergrundlauf gespeichert. Erst nach erfolgreichem Datenbank-Commit erscheint `BOB_IMPROVEMENT_STATUS` mit ausschließlich technischen Zählern und Zeitstempeln. Private Produktnummern, Preise und Gewinne werden dort nicht protokolliert. Ein fehlendes Protokoll wird nicht als Erfolg gewertet.

## Vor einem späteren Regelwechsel

Aktive Parameter und tatsächlich eingesetzte Version sichern; Kandidat separat prüfen und freigeben; laufende Trades weiter schützen. Bei Datenproblemen oder Verschlechterung keine neue Variante freigeben. Eine Rückkehr erfolgt über einen überprüften Revert mit Tests und Kontrolle der veröffentlichten Version. Änderungen an Risiko, Stops oder echten Aufträgen brauchen gesonderte Autorisierung.
