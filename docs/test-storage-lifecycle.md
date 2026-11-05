# Dauerhafte Speicherregel für Tests

Alle neuen Testfamilien müssen ihre Tabellen ausdrücklich in der geprüften
Archivauswahl registrieren. Der Regressionstest prüft die CREATE-TABLE-Anweisungen
der aktuellen Vergleichs- und Qualitätsstudien gegen diese Auswahl. Neue Module
müssen in diese Prüfung aufgenommen werden; unbekannte Tabellen werden niemals
blind exportiert (Kontozugangsdaten bleiben ausgeschlossen).

Die bestehenden vollständigen, verschlüsselten Google-Drive-Archive enthalten nun
auch Einstieg/Ausstieg, Qualitätsneustart und ältere Shadow-Studien sowie den
Index der ausgelagerten Testoriginale. Kleine Ergebnis- und Qualitätsdatensätze
bleiben lokal. Ein Vollarchiv allein berechtigt nicht zur lokalen Löschung.

## Abgeschlossene Einstieg-/Ausstiegstests

Der Hintergrundworker im vorhandenen Push-Dienst prüft alle 30 Minuten maximal
acht Fälle, höchstens 128 KiB je Kandidat und 2 MiB Rohdaten je Archiv. Kein neuer
Dienst, keine zusätzlichen Marktabfragen. Erste Prüfung sieben Minuten nach Start.
Ein frischer, unabhängig wiederhergestellter verschlüsselter Backup-Nachweis mit
Recovery-Schlüsselprüfung ist Voraussetzung; andernfalls meldet der Worker
`backup-proof-not-fresh` und lässt die Originale unverändert.

Nur vollständig abgeschlossene Fälle der bekannten Regelstruktur, deren letzte
Prüfung mindestens 24 Stunden zurückliegt, kommen infrage. Alle 18 Varianten müssen
terminal sein. Verschlüsselt ausgelagert werden vollständige Originale. Lokal
entfallen nur die großen Kursnachweise, KO-Nachweise, Triggerkerzen und Stopverläufe;
Status, Originalzeitpunkte, Preise, Produktidentität, Ergebnis, Gebührenbasis und
alle sonstigen Auswertungsfelder bleiben unverändert. Mindestnutzen 1 KiB pro Fall.

Upload → unabhängiger Download → Hash-/Entschlüsselungsprüfung → vollständiger
JSON-Vergleich → transaktionaler Austausch ausschließlich unveränderter Zeilen →
exakter Read-through-Test. Bei Abweichung Rollback. Keine Zeilenlöschung, keine
Änderung laufender Fälle oder Handelsregeln. `cold_test_evidence.get` liefert für
spätere Detailauswertungen das vollständige Original zurück; fehlende Archive
melden einen Fehler und erzeugen keine erfundenen leeren Ergebnisse.

Die beiden vorhandenen Auswertungen bleiben auch ohne Drive erreichbar und werden
im PostgreSQL-Integrationstest vor/nach Auslagerung vollständig verglichen.
Auswertungen, die künftig andere Detailfelder benötigen, müssen den Originalreader
verwenden. Für weitere Testfamilien erst einen ebenso geprüften Reader und eine
vollständige Ergebnisprojektion ergänzen; bis dahin vollständige Sicherung ohne
lokalen Ersatz. Altentscheidungen behalten ihren gesonderten geschützten Ablauf.

Status unter `storage.coldTests`: ausgelagerte Zeilen, logische JSON-Ersparnis,
letzter Lauf, Blockadegrund. `physicalBytesFreed` bleibt unbekannt, bis eine getrennte
Volumenmessung die physische Freigabe belegt. Wiederverwendbare Datenbankseiten sind
keine nachgewiesene Verkleinerung der Render-Disk.

Notabschaltung ohne Originalverlust: `BOB_COLD_TESTS_DISABLED=1`. Bestehende
Referenzen bleiben lesbar. Verschlüsselungsschlüssel und Archivindex aufbewahren.
