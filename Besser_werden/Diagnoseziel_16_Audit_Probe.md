# Diagnoseziel 16 – Audit-SQL-Laufzeit / Warteschlange (Teilnachweis)

Stand: 25.10.2026. **Noch keine bestätigte Reparatur und keine vollständige Einzelabnahme.**

Bob hat bereits in `decision_audit._build_report` einen unabhängigen 30-Tage-Forschungslauf und einen auf 24 Stunden begrenzten Wiederholungsversuch. Beide werden mit monotoner Zeitmessung getrennt protokolliert. Eine PostgreSQL-Ausnahme der Klasse `QueryCanceled` belegt eine abgebrochene SQL-Abfrage, **aber nicht automatisch** eine bestimmte Ursache wie ein langsamer Index-Plan, Lock, Datenbank-CPU, absichtliche Unterbrechung oder ausgelasteten Connection-Pool.

Die neue, ausschließlich **prozesslokale** `decision_audit.prospective_query_probe()`-Ansicht bewahrt den zuletzt **durchgeführten** originalen Abfrageversuch in festen Kategorien: 30-Tage-Status/-Dauer, 24-Stunden-Fallback-Status/-Dauer, Beobachtungszeitpunkt. Private Bobs `/diagnostics`-Sicht übernimmt sie als `simulationAndPush.databaseAudit` über den bereits erlaubten geschützten Leseweg. Keine Datenbankabfrage für diesen Status, keine Protokoll- oder Ergebniszeilen, keine Passwörter, keine SQL-Texte, keine Orderausführung. Für ein neu gestartetes Exemplar **ohne bisherigen Audit-Lauf** steht `status=not-observed`, niemals `healthy`.

### Abnahme

- GitHub-CI prüft mit `test_diagnostic_audit_query_probe.py`, dass die feste Kategorie `query-timeout` und `completed-partial` nur einen eingeschränkten Bericht ergeben; dass nach Neustart kein Erfolg behauptet wird; und dass manipulierte Payloads/Secrets keinen Weg in den privaten Status finden.
- Erst nach grüner CI und gleicher Live-Commit-ID auf beiden Diensten den **tatsächlich beobachteten** `databaseAudit`-Status protokollieren. Er kann `not-observed` sein, bis ein erlaubter Auditbericht erstellt wird. Niemals zur Beweiserzeugung massenhaft teure Report-Abfragen auslösen.
- Für die Root-Cause-Abnahme weiterhin **intern begrenztes EXPLAIN / pg_stat_activity / DB-Pool-Korrelation** auf dem autorisierten privaten Datenbankweg nötig. Keine öffentliche PostgreSQL-IP-Allowlist, kein blindes Anheben des SQL-Timeouts, kein riskantes CREATE INDEX in Produktion.

**Die 100er-Zählung bleibt 2/100**, Ziel 16 bis zu separaten Originalbelegen `partial`. Der Status enthält keine Handelsfreigabe und beweist keine Rekonstruktion fehlender Produkt- oder Marktdaten.
