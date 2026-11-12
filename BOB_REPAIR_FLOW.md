# Reparaturen übernehmen, nachprüfen und messen

Die vorhandene GitHub-Issue ist der gemeinsame Fall. Kein zweites Fehlerregister,
kein zusätzlicher Wächter. Die Übernahme ist eine dokumentierte Zusage und **keine
atomare technische Sperre**. Vor Schreiben aktuelle Issue, Kommentare und PRs
erneut lesen. Aktive fremde Bearbeitung nicht wegen Zeitablauf überschreiben.

## Übernahme

Der eine tatsächlich arbeitende Owner (ChatGPT oder separat autorisiertes Gemini)
ersetzt im Issue-Body genau eine Zeile dieses Formats; keine privaten Daten:

```text
<!-- BOB_REPAIR_FLOW_V1:owner=chatgpt;acceptedAt=2026-11-11T16:00:00Z;progressAt=2026-11-11T16:00:00Z;nextCheckAt=2026-11-11T18:00:00Z;phase=accepted -->
```

Zeiten sind Beispiele, niemals in reale Fälle kopieren. `acceptedAt` ist die
tatsächliche Übernahme, bleibt unverändert. `progressAt` ändert sich nur bei
neuem belegtem Fortschritt, nicht beim Lesen oder bei unverändertem Warten.
`nextCheckAt` ist eine verbindliche Nachprüfung im vorhandenen Wächterlauf, keine
Garantie eines minutengenauen Starts. Für CI/Deploy zuerst den nächsten regulären
Lauf nutzen; bei erforderlichen Markt-/Studienfällen den tatsächlichen
Beobachtungszeitraum berücksichtigen. Wartegrund und konkrete nächste Handlung
kurz im bestehenden Issue beschreiben.

Phasen: `accepted`, `working`, `testing`, `awaiting-live`, `blocked`.
Bestehende BOB_KI_STATUS-/BOB_KI_REVIEW-Zeilen weiterführen. Keine Phase
`verified` in diesem Marker: ein Ownertext bestätigt keine Live-Reparatur.
Nur vertrauenswürdige Issue-Autoren werden gelesen. Mehrere Marker, ungültige
Zeiten, Übernahme vor Issue-Erstellung und zukünftiger Fortschritt sind ungültig.

## Fälligkeit und Abschluss

Beobachter melden fehlende Übernahme bzw. überschrittenen Prüftermin im bestehenden
Fall einmal pro neuer Episode an den Reparaturwächter. Ein bloß bearbeitetes Issue
ist keine Übernahme. Bei veraltetem/unvollständigem Index keine Ausfälle behaupten.
Der Reparaturwächter prüft den konkreten Blocker, setzt die Arbeit fort oder
dokumentiert den belegten Wartegrund samt sinnvollem neuem Prüftermin. Er darf
Termine nicht ständig ohne neue Evidenz verschieben.

Abschlussbeleg: ursprünglicher reproduzierbarer Fehler, gezielte Regression,
erforderliche erfolgreiche CI für genaue Revision, veröffentlichte Revision und
datierte Prüfung der ursprünglich gestörten Funktion. Bei einer reinen
Konfigurationskorrektur die alte/neue Konfiguration und deren realen Folgelauf
statt eines nicht existierenden Code-Commits dokumentieren. Technische Gesundheit,
Merge, grüne CI oder ein KI-Kommentar allein reichen nicht. Administrativer
Abschluss, Duplikat, spontane Erholung und nicht rekonstruierbare Historie bleiben
separat; keine fiktiven Reparaturen oder Gewinne. Vorläufige Fälle bleiben offen.

## Kennzahlen durch die bestehende tägliche Fehlerwache

Für einen ausdrücklich genannten Zeitraum und deduplizierte Fehler-Episoden:

- Anzahl erkannt, tatsächlich übernommen, noch offen/blockiert, live bestätigt,
  administrativ geschlossen und wieder aufgetreten; fehlende Belege separat.
- Übernahmezeit = tatsächliche Übernahme minus ursprüngliche Erkennung.
- Reparaturdauer = bestätigte Funktionsabnahme minus ursprüngliche Erkennung;
  nur für nachgewiesene Abschlüsse, zusätzlich Alter der offenen Fälle.
- Verifizierte Abschlussquote = live bestätigte Reparaturen / alle im selben
  Zeitraum erkannten reparaturbedürftigen Episoden; offene/fehlgeschlagene Fälle
  bleiben im Nenner. Administrative Fälle und Duplikate separat ausweisen.
- Immer Zähler/Nenner, Zeitraum, geprüfte Abdeckung und fehlende Zeitstempel
  nennen. Ohne vollständige Kohorte **keine Gesamtquote**. Bestehende
  Worker-Neustartzähler sind Ereignisse, nicht eine KI-Reparaturquote.

Die API `problems.repairFlowSummary` misst zunächst nur Übernahmeabdeckung,
Alter und fällige Prüfungen des offenen Index. Abschlussquote und abgeschlossene
Reparaturdauer sind dort bewusst `null`, weil der Index keine vollständige
historische Kohorte enthält. Das ist kein Null-Prozent-Ergebnis. Vollständige
Kennzahlen werden anhand der bestehenden offenen und geschlossenen Issues samt
Belegen ermittelt, ohne historische Originalzeitstempel zu erfinden.

## Gemini und Produktprüfung

Gemini-Review nur mit tatsächlichem Kommentar/Lauf und passendem PR-Head als
ausgeführt kennzeichnen. Ein vorbereiteter Workflow oder global erlaubte
Gegenprüfung bestätigt keinen Modellaufruf. Ohne belegten Zugang `not-run`
festhalten und die autorisierte ChatGPT-Reparatur fortsetzen. Bestehende Gemini-
PRs wiederverwenden. Keine bezahlten Fallbacks, keine neuen Zugriffsrechte.

Eine vollständige aktuelle Produktliste schließt historische oder strengere
Nachweisfälle nicht automatisch. Zeit, Produkt-/Nachweisumfang und fehlendes
Pflichtfeld vergleichen; nur den tatsächlich behobenen Teilfall abschließen.
