# Gemeinsame Betriebsübersicht

Die Übersicht verbindet vorhandene Diagnosebeobachtungen, ohne Markt-, Risiko- oder Orderregeln zu verändern. Auf der Startseite steht „Du musst etwas tun“. Nur aktuelle, ausdrücklich als `needs-user` markierte Fälle erscheinen als persönliche Aufgaben. Ein nicht lesbarer Problemindex bleibt unbekannt.

Unter „Betrieb und Datenqualität“ werden Produktkonflikte, erfolgreiche Hintergrundläufe, reine Beobachtungen und erwartete nächste Läufe getrennt dargestellt. Die gemeinsame Prüfung startet über „Produktnachweise und Probleme prüfen“. `/api/operations-summary` benötigt die bestehende Bob-Anmeldung, ist read-only und liefert keine Rohberichte oder Zugangsdaten. Der MCP-Fokus `repairs` enthält dieselbe Projektion.

Produktdaten gelten nur bei aktueller, vollständiger Liste als vollständig. Konflikte bei KO/Basispreis gehen diesem Zustand vor. Es wird keine maßgebliche Originalquelle erfunden. Ältere GitHub-Nachweisfälle werden bei vollständigen aktuellen Feldern als abzugleichen angezeigt, niemals automatisch als repariert geschlossen. Gleiche Problemcodes werden zusammengefasst, ihre Fallnummern bleiben erhalten.

## Historische Fälle

Ein begründet abgeschlossener historischer Fall ohne rekonstruierbare Originaldaten ist kein aktiver Reparaturauftrag und kein Gewinn oder Verlust. Wiederaufnahme erfolgt bei neuen Originalbelegen. Dieser Patch dokumentiert und zeigt diese Regel; er verändert keine historischen Fallakten oder Paper-Kontostände. Das tatsächliche Abschließen einzelner Fälle erfordert deren dokumentierte Prüfung.

## Vergleich

Der bestehende eingefrorene Forward-Vergleich ergänzt je Variante die Verlustquote unter den Signalen und die Differenz zum Basismodell nach den bereits offengelegten Modellkosten. Lern- und Validierungsphasen bleiben getrennt. Diese Zahlen sind weder echte Produktkosten noch belegte Handelsrenditen; Regeln werden nicht automatisch übernommen.

## Prüfgrenzen

Gezielte Python-, HTTP-Authentifizierungs-, JavaScript- und Assettests sind vorhanden. Der synthetische Handy-Browsertest prüft die Statusanzeige und 360px-Breite. Eine erfolgreiche CI oder ein veröffentlichter Build beweist weder dauerhafte Hintergrundausführung noch bessere Signalqualität. Beides benötigt separate zeitlich passende Live-Nachweise.
