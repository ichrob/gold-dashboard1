# Unabhängige WAL-, Scratch-, Lock- und Volume-Evidenz vor einer späteren Speicheroperation

**Stand: 07.11.2026 – nur Entwurf und isolierte Tests.** Keine produktive Freigabe, kein
Aufruf auf Render oder PostgreSQL, keine Änderung bestehender Arbeiter, kein neuer
Backup-/Restore-Lauf und keine erneute Schlüsselwiederherstellung.

## Vier voneinander getrennte Belege

1. **Render-Provider-Volume:** Ein frischer, auf die exakt bestehende Produktions-Postgres-Ressource
   bezogener Wert in **Bytes** mit Providerquelle und Beobachtungszeit. RAM,
   `pg_database_size`, `pg_total_relation_size` oder alte Einzelwerte ersetzen
   diese unabhängige Messung nicht. Für den Nachweis einer physischen Änderung
   bleibt außerdem ein **wartungsbezogenes Vorher-/Nachher-Messpaar** nötig.
2. **WAL:** Ein kurzer, durch unveränderten Stats-Reset gebundener
   `pg_stat_wal`-Unterschied sowie `pg_ls_waldir`-Verzeichnisbelegung als
   Momentaufnahme. Kumulativ erzeugte WAL-Bytes oder das WAL-Verzeichnis
   beweisen **keine** freie WAL-Reserve und keine isolierte Spitzenlast
   eines späteren Repack-/Rewrite-Vorgangs.
3. **Scratch und Operation:** Tatsächlich verfügbare Bytes im **konkreten**
   temporären Arbeitsverzeichnis, separat von Provider-Volume sowie ein
   **passendes isoliertes** Lastexperiment für Peak-WAL, Peak-Scratch
   und vollständigen Original-Replay. Nicht aus Tabellen-Bloat-Schätzungen
   oder dem Wiederherstellungsbeleg für andere Tabellen ableiten.
4. **Lock-/Transaktionslage:** Frische lesende PostgreSQL-Aktivitätsstichprobe
   auf Sperrwartezeiten und offenen Transaktionen. Selbst null Wartefälle
   zum Zeitpunkt der Probe garantieren keine freie künftige Sperre.

## Technische Vorbereitung

`storage_maintenance_reserve_evidence.assess` ist eine **pure Funktion**
und wird ausdrücklich nicht von einem Produktivworker importiert. Sie
prüft nur operatorseitig übergebene, separat gemessene Daten auf feste
Provenienz-Kennzeichnungen, Bytes, Frische und konservative
Größenberechnung für die vorhandene historische Zieltabelle. Für
synthetische Prüfungen kann damit ein fehlender Provider-, WAL-, Scratch-,
Lock- oder isolierter Peak-Beleg nachvollziehbar abgewiesen werden.

Auch bei plausiblen Eingabewerten bleiben diese Status **immer false**:
`readyToExecute`, `storageCleanupAuthorized`,
`deletionAuthorized`, `futureLockAvailabilityProven`,
`independentActualWALPeakProven`,
`providerMaintenanceBeforeAfterPairVerified`. Eine plausible
Budgetrechnung allein ist nicht die Abnahme einer realen
Wartung.

## Aktuell fehlender tatsächlicher Nachweis

Für #1329/#1231 fehlen die frische reale isolierte Spitzenlastmessung,
die tatsächliche Scratch-Belegung auf demselben Host/Verzeichnis,
ein aktueller unabhängig zugeordneter WAL-/Sperrnachweis und
das physische, unmittelbar wartungsgebundene Provider-Messpaar.
Der früher nachgewiesene technische Termux-/E-Mail-Recovery-Roundtrip
und die AES-GCM-Prüfung bleiben **erfolgreich abgeschlossen**;
kein erneuter Test und kein Passwort.

**Harte Sperre vom 07.11.2026:** Ein neuer Archiv-/Restore-Lauf,
VACUUM (auch normal), VACUUM FULL, pg_repack, DELETE,
Original-/Pointer-Migration, Claim-Reset, Environment-/Secret-Änderung,
Neustart oder Deployment wird nicht ohne **neue separate ausdrückliche
Freigabe für den konkreten Schritt** gestartet. `reclaim-observations-20261107-v1`
ist bereits verbraucht und wird nicht wiederholt. Derzeit nur synthetische
CI-Tests und lesende Statusprüfung.
