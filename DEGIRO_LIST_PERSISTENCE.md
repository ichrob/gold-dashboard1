# Persistente DEGIRO-Screenshotliste (12. Oktober 2026)

**Aktive Liste:** Nach einem erfolgreichen Screenshot-Import bleiben die
Produktidentitäten und die Original-Listenbilder in der lokalen IndexedDB
gespeichert, auch nach 22 Uhr und über Nacht/Wochenenden. Die Bilder werden
nicht aus dem Dateinamen, sondern aus tatsächlich eingelesenen ISINs zugeordnet.

**Austausch:** Ein neuer gültiger Mehrfachbild-Upload ersetzt die bisherige
Liste mitsamt Produktidentitäten in einer einzigen IndexedDB-Transaktion.
Ungültige OCR/fehlgeschlagene Speicherung bewahren die vorherige aktive Liste.
Beim Austausch werden alte pro-Produkt-Felder, manuelle KO-Bestätigungen und
PDF-Verweise verworfen. Produktdetail-Originalbilder, die vor der neuen Liste
gespeichert wurden, dürfen nicht wieder in die aktive Liste eingelesen werden.

**Hintergrund:** Der zuletzt erfasste Screenshot-Produktbestand wird per
bestehendem Simulation-Sync in der PostgreSQL-Datenbank gespeichert und von
der Paper-Simulation bei geschlossener App weiter für neue Prüfungen verwendet.
Neue Uploads umgehen die normale 60-Sekunden-Synchronisationspause.
Bei konkurrierenden Browser-Tabs darf ein älterer Screenshot-Stand nicht die
neuere serverseitige Liste überschreiben. Historische virtuelle Positionen
und Trade-Protokolle bleiben unverändert, auch wenn sie alte ISINs enthalten.

**Zeitbezug:** Der Uploadzeitpunkt bezeichnet nur die Version der Produktliste.
Er ersetzt niemals tatsächliche Geld-/Briefkurszeiten, Hebel- oder KO-Nachweise.
Quellen müssen weiterhin aktuell, zugeordnet und bestätigt sein. Eine über
mehrere Tage gespeicherte Produktidentität ist keine aktuelle Handelsfreigabe
oder bestätigte DEGIRO-Verfügbarkeit.

**Speichergrenzen:** Die Listenscreenshots bleiben lokal auf diesem Gerät;
Browser-Datenlöschung oder Speichereviction können sie entfernen. Der
Hintergrundserver speichert Produktdaten, nicht die Screenshot-Originaldateien.
Kein DEGIRO-Konto und keine automatische Order sind angeschlossen.

Tests: test_list_archive.js und test_paper_simulation.py; dazu vollständige CI.