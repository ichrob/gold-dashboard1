# Bob: kostenfreier RAM-Schutz durch optionale Arbeitslast-Priorität (14.11.2026)

## Geltungsbereich
- Kein Tarifwechsel, kein zusätzlicher Dienst, keine neuen API-Kontingente, keine Echtgeldorders.
- Bereits markierte optionale Arbeiten im **Push-Service-Prozess** (historische Evaluationen, Cold-Storage-Scanner und jetzt auch die reguläre bounded VACUUM-Wartung) teilen sich den vorhandenen `ocr_workload_priority.maintenance_slot`. Höchstens **ein** solcher Job arbeitet gleichzeitig.
- Die bereits vorhandene Handy-OCR-Erfassung erhält an den *Grenzen* zwischen optionalen Jobs Vorrang. Angefangene Aufgaben oder Datenbanktransaktionen werden **nie** abgebrochen. Ihre Ergebnisse gehen durch die Änderung nicht verloren; anstehende Arbeiten warten und setzen automatisch fort.
- Die Live-Kursabfrage, Signal-/Push-/Stop-Überwachung und neue Benutzeranfragen werden durch diese Schranke **nicht** künstlich gedrosselt. Es gibt keinen zusätzlichen Poll-Takt, keine pausierten Live-Threads und keinen gemeinsamen Queue-Zwang für Handelsfunktionen.
- Große oder bereits laufende Wartungsschritte können weiterhin Zeit/RAM beanspruchen. Bei gleichzeitig vielen Aufgaben kann sich die **optionale** Nacharbeit verzögern. Die Garantie „jeder Benutzerauftrag sofort“ ist physikalisch auf einem Free-Service nicht möglich.

## Bestehende kostenlose Schutzbausteine (nicht überschreiben)
1. `memory_watch.py` überwacht den Render-Dienst über cgroup-Prozessspeicher und protokolliert ab 85 % Warnungen; sie sind **keine Aiven-Host-RAM-Messung**. Es entfernt ausschließlich bereits freigegebene glibc-Seiten, keine Live-Daten.
2. `aiven_health.py` erhebt SQL-Gesundheit; Aiven-Host-RAM ist über den vorhandenen verbundenen SQL-Zugang **nicht messbar**. `aiven_host_capacity_review.py` bewertet echte Console-Messwerte konservativ: 85 % nur bei zwei korrelierten Beobachtungen; 95 % einzeln kritisch. Ohne Konsolenwerte bleibt der Zustand unbestätigt, nicht „gesund“.
3. SQL-Evaluationen haben bereits kleine Seiten und Zeitlimits. Die neue Serialisierung vermeidet überlappende optionalen Läufe; sie verändert weder Live-Daten noch Handelsregeln.
4. Archivierung auf Google Drive bleibt an unabhängige Restore-/Download-/Schlüssel- und Kapazitätsnachweise gebunden. **Keine automatische Löschung** von Originalen oder Auslagerung aktiver Markt-/Produkt-/Trade-Daten. Historische Kopien werden nicht als freigewordener physischer RAM oder Disk ausgegeben.
5. Erweitertes „Rechnen auf einem anderen Anbieter“ wird **nicht** automatisch aktiviert: Es gibt keinen verifizierten zusätzlichen kostenlosen CPU-/RAM-Kredit oder App-Zugang dafür. Bestehende serverseitige Berechnungen bleiben unverändert.

## Grenzen und Nachweis
- Der Slot ist **prozesslokal**, keine globale Aiven-/Render-Quotensteuerung; separate Web-Services und PostgreSQL-Autovacuum laufen unabhängig. Daher ist eine historische Aiven-Auslastung von rund 98,6 % **nicht ursächlich auf Benutzeraufträge zurückgeführt** und durch diese Änderung nicht als beseitigt bewiesen.
- Tests: `python -m unittest -v test_ocr_workload_priority.py test_storage_maintenance.py test_aiven_host_capacity_review.py test_memory_watch.py`.
- Nach Deployment beobachten: nicht überlappende `maintenanceRunning`-Zahl (0 oder 1), OCR-Durchsatz/-Timeouts, Render-RAM-Warnungen, Aiven-Console-RAM bei neuen Spitzen und normale Markt-/Push-Liveness. Bei auffälligen Tests oder Betrieb: keine riskante Sofortfreigabe, sondern Korrektur/Rollback.
