# #1329: Isolierter JSONB-Kompressionsversuch (12.11.2026)

## Zweck

Die aktuellen Bob-Metadaten zeigen besonders starkes Wachstum von
`bob_diagnostic_history`, `bob_decision_audit` und `bob_metric_checks`.
Die Diagnose-Stichprobe enthielt wiederholte Input-Payloads, jedoch
unterschiedliche Ereigniskontexte. **Ein dedupliziertes Payload ist nicht
gleich einem doppelten Ereignis.** Der vorhandene
`diagnostic_reference_shadow.py` ist bereits der verlustfreie,
rein speicherinterne Referenzmodelltest; diesen nicht noch einmal erfinden.

Dieser zusätzliche Versuch beantwortet eine andere Frage:
Kann PostgreSQL 18 große neue JSONB-Felder auf dem vorhandenen System
mit LZ4 statt pglz besser komprimieren, ohne dass Reader-Inhalt,
identifizierende Datensatzposition oder Originalzeit verändert werden?
Die Antwort ist *nicht* aus theoretischen Python-GZIP-Raten abzuleiten.

## Begrenzte Durchführung – **nicht automatisch**

`storage_jsonb_compression_probe.py` hat keinen Service-Hook, Zeitplan,
API-Endpunkt, Retention-Code oder Schreibpfad. Die Unit-Tests nutzen
nur deterministische, künstliche Input- und Entscheidungsdaten.

Nur bei ausdrücklich geplanter isolierter Abnahme kann ein Operator auf
dem **bereits existierenden getrennten**
`bob_archive_restore_test`-Dienst die Umgebungswerte
`DATABASE_URL` (nur zum Host-/DB-Namen-Vergleich, **ohne
Produktionsverbindung**) und `BOB_ARCHIVE_RESTORE_DATABASE_URL`
aus bestehender Konfiguration benutzen und
`BOB_STORAGE_COMPRESSION_PROBE_ONCE=1` setzen.
Das Programm verweigert andere Datenbanknamen, denselben Host und
fehlende ausdrückliche Aktivierung. Es erstellt **ausschließlich
temporäre Tabellen** für maximal 96 synthetische Einträge, mit
zweimal höchstens 2 MB synthetischem JSON, kurzen Statements und
keinerm dauerhaften Retentions-/Originalschreibvorgang. Kein VACUUM,
kein REINDEX, keine Archivkopie, kein Recovery-Test, keine Bestellung
oder dauerhafte PostgreSQL-Schemaänderung.

Die Abnahme kontrolliert JSONB-Readback auf **jedes Feld einschließlich
synthetischer Quellzeiten**. Berichtet werden die Größen temporärer
Relationen, tatsächlich vom PostgreSQL-Server verwendete
Kompressionsmethode, Row-Count und Differenz zwischen Testmethoden.
Bei fehlender LZ4-Unterstützung wird dies ausdrücklich gemeldet.
Weder eine synthetische Größenersparnis noch ein besserer Vergleich
erlaubt allein ein produktives `ALTER TABLE`, eine Änderung am
Schreibpfad oder die Löschung von Originalen.

## Für reale Einsparungen noch erforderlich

- Nur autorisierte, bereits vorhandene und von bisherigen Reparaturen
  freie Live-Revision zum Vergleich; keine parallelen Code-Branches
  oder ungeplanten Deploys/Neustarts.
- Nach isoliertem Synthetik-Ergebnis ein **gesondert freigegebener**
  repräsentativer, unveränderter Original-Sample-Test auf bereits
  gesichertem getrennten Restore; Datenschutz-/Handelsdetails
  nicht in CI-Artefakte oder Logs.
- Phasenweise, zukünftige Writer-Anpassung nur bei besseren Ergebnissen,
  stabiler CPU/RAM und exakter Reader-/Zeit-/Hash-Gleichheit.
- Bob CI, Risiko, CodeQL, anschließender echter Live-Readback und
  reguläre Markt-/Push-/Simulationsfunktion.
- Physische Render-Volume-Messungen als eigenes vorher/nachher Paar,
  keine Gleichsetzung temporärer Tabellenbytes mit freigewordenem
  Render-Speicher.

Das vorhandene #1329-Archiv bleibt weiterhin durch AES-GCM,
frischen unabhängigen Restore/Recovery-Key, Batchbindung, WAL/Scratch,
Rollback und Retention geschützt. Es werden **keine** laufenden
Originaldaten archiviert oder entfernt.
