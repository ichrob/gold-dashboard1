# Historischer Replay aus bereits gesicherten Originalen – sichere Vorbereitung

**Stand: 07.11.2026 · ENTWURF, NICHT FÜR PRODUKTION FREIGEGEBEN**

## Tatsächliche technische Ausgangslage

- `evidence_archive.py` umfasst als geprüften archivierten Datenbereich die Tabellen `bob_diagnostic_history` und `bob_decision_audit`. Die im späteren Auswertungslauf angelegten `bob_history_eval_segments` und `bob_history_eval_cursor` sind **nicht** Teil dieser standardmäßigen Archivliste. Die gespeicherte historische Manifestfolge muss unabhängig und unverändert im autorisierten Evaluationskontext gelesen werden.
- `evidence_archive.restore_check` verifiziert Originalwerte in **temporären** PostgreSQL-Tabellen und führt danach pro Segment ein `rollback()` aus. Der erfolgreiche frühere unabhängige Restore vom 04.–07.11. ist ein realer Recovery-Nachweis; er stellt **keine dauerhaft abfragbare Kopie** der Quellen für `storage_history_replay` bereit. Dies ist keine fehlgeschlagene Wiederherstellung und kein Grund für eine Wiederholung des technischen Schlüsseltests.
- Der bisherige `storage_history_replay` vergleicht nur lokale scalar projections. Ein historisches, regulär aus der 7-Tage-/60k-Retention gefallenes Diagnosepräfix kann er ohne zuvor separat archivierte Originale **nicht** rekonstruieren. Der 200-Seiten- und Zeitrahmen ist außerdem begrenzt.
- Der aktuelle geprüfte Scope bezieht sich auf `reviewed-evidence-tables-not-full-database-backup`; **kein** Voll-DB-Backup und **keine** pauschale Originalfeld- oder Bildfreigabe.

## Neue isolierte Bausteinprüfung

`storage_archive_page_replay.compare` prüft höchstens **16** vom Operator bereits vorliegende unveränderliche Auswertungsmanifeste und passende, **bereits separat bereitgestellte Originalzeilen** aus einer isolierten read-only Verbindung. Jede Seite hat höchstens 400 Originale. Die vorhandene unabhängig implementierte Digest-/Kategorie-/Outcome-Berechnung wird neu angewendet; Identität, ursprüngliche Zeilenreihenfolge, inklusive gleicher Zeitstempel mit mehreren IDs, und Seiten-/Cursorzählung werden abgeglichen.

Die Schnittstelle erstellt weder Archive noch Wiederherstellungen, verbindet sich mit keinem Dienst, legt keine Tabellen an und bietet **keinen** HTTP-/Background-Hook. Der Host muss eine bereits authentifizierte Manifestfolge und vorher isoliert bereitgestellte Originale liefern. Hash-Gleichheit dieser übergebenen Daten **beweist für sich allein weder die Herkunft aus einem bestimmten AES-GCM-Archiv noch vollständige Historie**. Deshalb bleibt selbst nach passenden Seiten:

- `fullOriginalReplayVerified=false`
- `archiveFileAndBatchBoundVerified=false`
- `restoreIsolationVerifiedByThisCheck=false`
- `deletionAuthorized=false`
- `physicalBytesFreed=null`

Ein späterer eigener, gesondert freigegebener Archiv- und Reader-Abnahmeschritt muss insbesondere kryptografische Archiv-/Batchidentität, vollständige Zeitbereichsabdeckung (auch frühere und nachträglich eingetroffene Reihen), Wiederherstellung in einer **separaten** Instanz, produktiv äquivalente Leser und Rollback nachweisen, bevor man diese Grenzen unabhängig auflösen dürfte.

## Zusätzliche, ausschließlich synthetisch getestete ZIP-/COPY-Herkunftsvorprüfung

`storage_archive_copy_preflight.inspect(path, expected_sha256)` ist ein weiteres **isoliertes** Prüfmodul ohne CLI, Netzwerk, Datenbank, Entschlüsselung, Wiederherstellung oder Hintergrundaufruf. Es kann **später nach ausdrücklicher Freigabe** einen bereits separat vorhandenen, entschlüsselten Original-ZIP-Datensatz mit einer **unabhängig erhaltenen und authentifizierten** erwarteten SHA-256-Prüfsumme vergleichen. Im aktuellen CI werden **nur künstlich erzeugte ZIP-Dateien** geprüft; kein echtes Bob-Archiv wird geöffnet oder kopiert.

Die Prüfung begrenzt ZIP-Größe, Dateiliste, Manifestgröße und die Teilsegmente und prüft Original-COPY-Segmente der zwei historischen Quelltabellen `bob_diagnostic_history` und `bob_decision_audit`: vorgegebene Dateinamen, Datensatzanzahl, Bytezahl, SHA-256 und erforderliche Quellspalten. Ein fehlender, leerer oder veränderter historischer Quellbestand wird abgelehnt. Exakte Originale und Zeiten werden **nicht** an ChatGPT oder in den Testbericht ausgegeben.

**Wichtig:** Ein mit einer vom Aufrufer selbst gelieferten SHA-256 passendes ZIP beweist nur die Übereinstimmung mit **diesem gelieferten Digest**, nicht dessen authentische Herkunft. Das Modul bestätigt daher auch nach vollständiger Teilsegment-Übereinstimmung ausdrücklich **nicht** die unabhängige Quelle des erwarteten Digest, die Identität eines bestimmten verschlüsselten Drive-Objekts oder die Zuordnung zu den gesondert verwalteten Auswertungsmanifesten. Es überprüft auch keine Zeitbereichsvollständigkeit, kein späteres Nachreichen von Quellzeilen, keine tatsächlichen Reader oder Wiederherstellungen. Für diese Schritte fehlen weiterhin echte, getrennt freizugebende Belege.

Die Flags `independentExpectedDigestProvenanceVerified=false`, `evaluationManifestBoundToArchive=false`, `originalTimeRangeCoverageVerified=false`, `fullOriginalReplayVerified=false`, `archiveFileAndBatchBoundVerified=false` und `deletionAuthorized=false` bleiben in jedem Fall gesetzt. Ein SHA-/COPY-Prüfer ist keine Löschfreigabe und kein physischer Speichergewinn.

## Gesperrte Realabnahme

Es wird gegenwärtig **kein** Archivmaterial heruntergeladen/entschlüsselt, kein neuer Restore durchgeführt und **kein** produktiver SQL-Leselauf angestoßen. Das bereits verbrauchte `reclaim-observations-20261107-v1` bleibt unangetastet. Originale, Zeitstempel, Trade-Simulationen, Push, KO-Regeln und alle bisherigen Nachweise bleiben erhalten. Die neue Produktionssperre vom 07.11. hat Vorrang. Ein zukünftiger Betreiber benötigt **separate ausdrückliche Freigabe**, einen bereits legitimierten isolierten Reader, die exakte Original-/Manifest-Batchbindung, geprüfte WAL-/Scratch-/Lock-Reserven und ein unverfälschtes physisches Render-Volume-Vorher-/Nachher-Messpaar für jeden etwaigen Wartungseingriff.

Dieser Baustein ist nur eine reproduzierbare, strikt begrenzte Vorprüfung; **er vervollständigt den historischen Replay noch nicht**.
