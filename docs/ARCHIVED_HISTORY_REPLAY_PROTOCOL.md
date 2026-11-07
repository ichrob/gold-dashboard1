# Historischer Archiv-Replay – geprüfter Bereich und verbleibende Grenzen

**Stand: 07.11.2026 · PR bleibt Entwurf; isolierte Abnahme durchgeführt, keine pauschale Produktions- oder Löschfreigabe.**

## Tatsächliche technische Ausgangslage

- `evidence_archive.py` umfasst als geprüften archivierten Datenbereich die Tabellen `bob_diagnostic_history` und `bob_decision_audit`. Vor PR #1437 fehlten `bob_history_eval_segments` und `bob_history_eval_cursor` in der standardmäßigen Archivliste. Die inzwischen gemergte Erweiterung nimmt diese in künftige Archive auf; ältere Archive werden dadurch nicht rückwirkend ergänzt. Der Abgleich muss jeweils die tatsächlich enthaltene Manifestfolge und ihre Herkunft prüfen.
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

Die unten dokumentierte, vom Nutzer autorisierte isolierte Abnahme liefert zusätzliche Belege für ihren ausdrücklich benannten Bereich. Diese Belege ändern weder die begrenzte Aussage des Moduls noch seine konservativen Rückgabeflags. Sie bestätigen keine vollständige Historie außerhalb dieses Bereichs.

## ZIP-/COPY-Herkunftsvorprüfung als begrenzter Baustein

`storage_archive_copy_preflight.inspect(path, expected_sha256)` ist ein weiteres **isoliertes** Prüfmodul ohne CLI, Netzwerk, Datenbank, Entschlüsselung, Wiederherstellung oder Hintergrundaufruf. Es kann im autorisierten Prüfablauf einen bereits separat vorhandenen, entschlüsselten Original-ZIP-Datensatz mit einer **unabhängig erhaltenen und authentifizierten** erwarteten SHA-256-Prüfsumme vergleichen. Im aktuellen CI werden **nur künstlich erzeugte ZIP-Dateien** geprüft; kein echtes Bob-Archiv wird geöffnet oder kopiert.

Die Prüfung begrenzt ZIP-Größe, Dateiliste, Manifestgröße und die Teilsegmente und prüft Original-COPY-Segmente der zwei historischen Quelltabellen `bob_diagnostic_history` und `bob_decision_audit`: vorgegebene Dateinamen, Datensatzanzahl, Bytezahl, SHA-256 und erforderliche Quellspalten. Ein fehlender, leerer oder veränderter historischer Quellbestand wird abgelehnt. Exakte Originale und Zeiten werden **nicht** an ChatGPT oder in den Testbericht ausgegeben.

**Wichtig:** Ein mit einer vom Aufrufer selbst gelieferten SHA-256 passendes ZIP beweist nur die Übereinstimmung mit **diesem gelieferten Digest**, nicht dessen authentische Herkunft. Das Modul bestätigt daher auch nach vollständiger Teilsegment-Übereinstimmung ausdrücklich **nicht** die unabhängige Quelle des erwarteten Digest, die Identität eines bestimmten verschlüsselten Drive-Objekts oder die Zuordnung zu den gesondert verwalteten Auswertungsmanifesten. Es überprüft auch keine Zeitbereichsvollständigkeit, kein späteres Nachreichen von Quellzeilen, keine tatsächlichen Reader oder Wiederherstellungen. Die zusätzlichen realen Belege unten stammen aus dem gesonderten isolierten Prüfablauf, nicht aus dem Rückgabewert dieses Moduls.

Die Flags `independentExpectedDigestProvenanceVerified=false`, `evaluationManifestBoundToArchive=false`, `originalTimeRangeCoverageVerified=false`, `fullOriginalReplayVerified=false`, `archiveFileAndBatchBoundVerified=false` und `deletionAuthorized=false` bleiben in jedem Fall gesetzt. Ein SHA-/COPY-Prüfer ist keine Löschfreigabe und kein physischer Speichergewinn.

## Durchgeführte isolierte Abnahme

Die Nutzerfreigabe wurde für eine begrenzte Prüfung in der bestehenden separaten Restoreinstanz genutzt. Sie erlaubt keine pauschale Originalmutation oder Speicherbereinigung.

- Authentifizierte Originalarchive: `bob-evidence-20261103T013823Z.zip.aesgcm` und `bob-evidence-20261107T110617Z.zip.aesgcm`. Verknüpfung über Wiederherstellungsbeleg, verschlüsselte Prüfsumme, AES-GCM-Authentifizierung und Klartextprüfsumme.
- Alle **872 archivierten Manifestseiten / 215.231 Originalzeilen** wurden mit vollständigen SQL-Quellspalten und Manifest-/Cursorwerten verglichen. Pro Seite wurde ein tatsächlicher Rollback geprüft; anschließend waren keine öffentlichen oder temporären Quelltabellen in der Restoreinstanz verblieben.
- **629 Cold-Archivpakete / 52.059 Analyseoriginale** innerhalb dieses Bereichs wurden über die produktiven Reader und die tatsächlich wiederhergestellte PostgreSQL-Verweistabelle vollständig verglichen: keine Abweichung. Die Wiederaufnahme aller 629 persistenten Prüfbelege wurde gesondert getestet.
- Die zuvor ungeklärten **1.570 Payload-Unterschiede** zwischen den beiden Archivständen wurden durch Auflösung der Cold-Verweise vollständig erklärt.
- Die ausdrücklich autorisierte Auto-Deploy-Pause endete nach 12,20 Minuten; die Einstellung wurde auf `After CI Checks Pass` zurückgesetzt.
- Die konservative Gesamtvolume-Reserve legitimierte nur die begrenzten TEMP-Prüfungen. Direkte WAL-Dateistatistik war mangels Berechtigung nicht zugänglich. Keine Freigabe großer produktiver Wartungsoperationen.
- Das gemessene Restorevolume stieg von 66.965.504 auf 69.042.180 Bytes. **Kein Speichergewinn**.

Prüfbelege:
- [SQL, Originalspalten und Rollback](https://github.com/ichrob/gold-dashboard1/issues/1329#issuecomment-6706781917)
- [Cold-Reader, Wiederaufnahme und zurückgesetzte Deployment-Einstellung](https://github.com/ichrob/gold-dashboard1/issues/1329#issuecomment-6707085863)
- [Aufgelöste Payload-Unterschiede](https://github.com/ichrob/gold-dashboard1/issues/1329#issuecomment-6706507408)

## Zeitbereichsabdeckung und historische Unbekannte

Die frühere Sammelzahl von 70.960 Diagnose- und 2.019 Entscheidungszeilen außerhalb der archivierten Manifeste war **keine einheitliche verlorene Historie**. Der vorhandene Evaluator verarbeitet bewusst erst Daten älter als zwei Tage und höchstens 400 Zeilen je Bereich und Lauf. Diese Regeln bleiben unverändert.

Konsistenter SQL-Snapshot vom **07.11.2026, 13:55:25 Europe/Zurich**:

| Bereich | passende Seiten | Originalzeilen mit passendem Manifest | vor erstem Manifest | neu auswertbar | im Zwei-Tage-Fenster |
|---|---:|---:|---:|---:|---:|
| Diagnosen | 534 | 185.065 | 18.000 | 37 | 48.733 |
| Entscheidungen | 359 | 34.491 | 0 | 2 | 1.882 |

Die zusätzlichen **4.325** Zeilen wurden anhand ihrer skalaren Originalprojektionen unabhängig gegen aktuelle Manifeste geprüft. Für diese Erweiterung wird **kein zusätzlicher Vollpayload-/SQL-Rollback-Test** behauptet. Die 39 bereits auswertbaren Zeilen waren während der Prüfung nachgerückt; die 50.615 jüngeren Zeilen sind regulär noch ausstehend. Alle Zahlen sind zeitgebundene Beobachtungen.

Für **18.000 Diagnoseoriginale vom 28.10.2026 10:57:16.042511 UTC bis 29.10.2026 07:49:37.138056 UTC** wurde kein damaliger Manifestnachweis gefunden. Die Originaldaten sind vorhanden. Eine neue rückblickende statistische Zusammenfassung ihrer archivierten Kategorien und Outcomes wurde in 45 Seiten berechnet und unabhängig geprüft:

- `historicalManifestRecovered=false`
- `historicalEvaluationStatus=unknown`
- `tradingStrategyRecomputed=false`

Diese neue Berechnung ersetzt keinen damaligen Auswertungsnachweis und ist kein Handelsbacktest oder Renditevergleich. Eine erneute Berechnung darf niemals als wiedergefundenes damaliges Ergebnis etikettiert werden.

Der vollständige Bericht und der aktuelle Manifestsnapshot wurden auf der getrennten Restoreinstanz in `bob_replay_audit.history_coverage_reports` gespeichert und exakt zurückgelesen. Bericht-SHA256: `3f7063060567674cc8cbcdf99d9a0be79625cd255798c45504f0d73b28713613`.

[Abdeckungsbericht und Suchumfang](https://github.com/ichrob/gold-dashboard1/issues/1329#issuecomment-6707232202)

## Fortsetzung ohne Wiederholung abgeschlossener Arbeiten

1. Bestehende authentifizierte Belege und deren exakten Bereich verwenden; Schlüsselrettung, komplette Restoreprüfungen und Deployment-Pausen nicht allein wegen historisch konservativer Modulflags wiederholen.
2. Neue auswertbare Daten durch den vorhandenen Worker fortschreiben lassen. Ein steigender Zähler belegt Fortschritt, aber für sich allein keine Readergleichheit oder vollständige Abdeckung.
3. Die 18.000 älteren Zeilen als historische Nachweislücke führen. Nur ein tatsächlich gefundener und authentifizierter damaliger Beleg kann diesen Status ändern.
4. Vor jeder zusätzlich beantragten Originalmutation Backup, Restore, eingriffsspezifische WAL-/Scratch-/Lock-Reserven und Rückweg prüfen. Physische Speicherfreigabe nur mit geeignetem Provider-Vorher-/Nachher-Messpaar behaupten.

PR #1435 bleibt ein begrenzter, nicht produktiv eingebundener Prüfbaustein. `fullOriginalReplayVerified=false`, `deletionAuthorized=false` und `physicalBytesFreed=null` bleiben korrekt. Kein Main-Merge oder Deploy wird durch dieses Protokoll ausgelöst.
