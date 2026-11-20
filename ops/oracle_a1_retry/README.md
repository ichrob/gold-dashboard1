# Bob Oracle A1 — unabhängiger 30-Minuten-Startwächter

Status (2026-11-20): `bob-oracle-a1-retry` als Cloudflare Worker veröffentlicht, Cron `*/30 * * * *` aktiv, **Oracle-Apply bewusst deaktiviert**, solange keine geprüfte OCI-API-Anbindung vorliegt.

## Funktionsweise

- Cloudflare Cron läuft serverseitig unabhängig von Samsung und Oracle Cloud Shell.
- Nur `eu-zurich-1`, OCI Resource Manager: übernimmt **ausschließlich** den zuvor geprüften Terraform-Plan (`FROM_PLAN_JOB_ID`).
- Stoppt bei laufenden Jobs, bei einer im aktuellen Stack-State **oder der aktuellen OCI-Compute-Instanzliste des BobOCR-Compartments** belegten A1-Instanz, unbekannten Fehlern, kaputtem/fehlendem Plan und unklaren Zuständen. Ein älterer erfolgreicher reiner Netzwerk-Apply gilt ausdrücklich nicht als Beweis einer erstellten VM. **Vor jedem Apply wird außerdem der konkrete JSON-Terraform-Plan von Oracle geladen und geprüft:** erlaubt ist genau `oci_core_instance.bob` als einzige Änderung, mit 1 OCPU, 4 GB RAM, 50 GB Bootvolume, geprüftem Ubuntu-Image und bereits vorhandenem isoliertem Subnetz ohne öffentliche IP. Ein alter `4 to add`-Plan wird strikt abgewiesen. Wenn `GetStackTfState` nicht lesbar oder ungültig ist, gibt es keinen neuen Apply.
- Wiederholt frühestens nach 25 Minuten und nur nach einem im letzten Apply-Log bestätigten Oracle-Kapazitätsfehler. Die Cron-Triggers liegen 30 Minuten auseinander.
- Ein deterministischer `opc-retry-token` pro fehlgeschlagenem Apply und geprüftem Plan reduziert das Risiko doppelter Jobs bei zeitgleich ausgeführten Worker-Instanzen. OCI bewahrt Retry-Tokens bis zu 24 Stunden; nach diesem Zeitraum ist das kein dauerhafter globaler Lock. Die Wartezeit beginnt am OCI-Feld `timeFinished` (Ende des Fehlversuchs), nicht bei `timeCreated`. Fehlende oder ungültige Abschlusszeitstempel sperren neue Applies.
- Keine Echtgeldausführung, keine neuen Handelsberechtigungen, keine Änderungen am bestehenden Cloudflare-Bob-Wächter.
- HTTP-Zugriff liefert immer 404; keine extern auslösbare Provisionierung.
- Keine Kosten-/SKU-Freigabe durch den Worker. Der Terraform-Plan muss vor Aktivierung explizit als **Always Free, Zürich, 1 OCPU, 4 GB RAM, 50 GB Boot, kein Public IP** geprüft sein. Danach `PLAN_VERIFIED_ALWAYS_FREE=true` nur gemeinsam mit zwei weiteren Schaltern setzen.

## Vor Aktivierung sicher hinterlegen

Im Cloudflare-Dashboard unter **Workers & Pages > bob-oracle-a1-retry > Settings > Variables and Secrets**:

| Name | Typ | Wert |
| --- | --- | --- |
| `OCI_TENANCY_OCID` | Secret | Oracle Tenancy OCID |
| `OCI_USER_OCID` | Secret | OCID des eigens eingeschränkten API-Benutzers |
| `OCI_API_FINGERPRINT` | Secret | API-Key-Fingerprint |
| `OCI_PRIVATE_KEY_PEM` | Secret | zugehöriger **PKCS#8** RSA Private Key; niemals in GitHub/Chat |
| `OCI_STACK_OCID` | Secret | OCID des bestehenden geprüften Resource-Manager-Stacks |
| `OCI_PLAN_JOB_OCID` | Secret | OCID des bereits geprüften erfolgreichen Plan-Jobs |

Die private Schlüsseldatei ist **kein** Oracle-/DEGIRO-PIN und darf nicht in Bob-Logs, Chat-Nachrichten oder GitHub stehen. Bei PKCS#1 den Schlüssel lokal sicher nach PKCS#8 konvertieren (z. B. `openssl pkcs8 -topk8 -nocrypt`). Nur API-Rechte für den vorhandenen Oracle Resource-Manager-Stack und dessen Jobs einrichten (OCI benötigt `ORM_JOB_MANAGE`, `ORM_STACK_USE` und zum Prüfen des aktuellen Terraform-States `ORM_STACK_READ`). Zusätzlich benötigt der API-Benutzer **`inspect instances` im dedizierten Compartment `BobOCR`**. Ohne diesen Leseschritt wird niemals ein neuer Apply eingereicht.

Die drei Standardschalter bleiben bis zur abgeschlossenen Prüfung **false**:
`ENABLED`, `ALLOW_APPLY`, `PLAN_VERIFIED_ALWAYS_FREE`.

Nach Schlüsselanlage und Überprüfung zunächst mit deaktiviertem Apply Log/Status prüfen, dann alle drei Schalter bewusst auf `true` setzen. Bei jedem anderen Fehler bleiben sie `false`. Keine automatische Kostenfreigabe. Oracle Free Trial/Always-Free-Kontingente und Kontolimits sind separat zu prüfen.

## Tests, Beobachtung, Not-Aus

Lokale Schutzlogiktests: `node ops/oracle_a1_retry/worker.test.mjs`.
Cloudflare: Worker > Observability > Logs; Statuscodes `disabled`, `job_in_progress`, `already_succeeded`, `not_a_capacity_failure`, `apply_submitted`.
Not-Aus: `ENABLED=false` in Cloudflare.
Die bestehende Cloud-Shell-`bob-a1-v4.sh` nicht parallel starten, solange die Cloudflare-Automatik aktiv ist. Cloudflare Cron kann verzögert starten, daher sind 30 Minuten eine Soll-Frequenz, kein Echtzeitversprechen.

## Befund aus Oracle-Terraform-Export vom 20.11.2026

Das hochgeladene Terraform-State enthält Netzwerk, isolierte Security List und privates Subnetz, **keine erstellte OCI-Compute-Instanz**. Das frühere Cloud-Shell-Skript meldete dagegen am 19.11. nach `oci compute instance list` eine vorhandene `bob-ocr-zurich`-Instanz. Deshalb muss vor jeder Aktivierung die **aktuelle OCI-Compute-Liste** verifiziert werden; ein fehlender Terraform-State-Eintrag allein beweist keine fehlende VM. Die originale `main.tf` setzt `assign_public_ip=false`, `prohibit_public_ip_on_vnic=true` und enthält weder Security-List-Regeln noch NAT-/Service-Gateway-Route. Das ist ein absichtlich isolierter Teststand: eine spätere VM wäre damit nicht für Fern-OCR/Updates aus Bob erreichbar. Das ist **nicht** automatisch ein Grund, öffentliche Ports zu öffnen. Netzwerkzugang für spätere OCR-Nutzung erst separat ohne Mehrkosten, mit Authentifizierung und minimalen Firewall-Regeln entwerfen und überprüfen. Der Import/Status beweist keinen konkreten `Out of host capacity`-Fehler; dafür ist das Apply-Job-Log nötig.

Die Sicherheitsprüfung gegen Doppelstarts ist nur Quellcode-Test und ersetzt **keinen** authentifizierten OCI-Joblauf. Der bei Cloudflare bereits veröffentlichte Worker erhält Codeänderungen nicht allein durch den GitHub-Merge: ein gesonderter kontrollierter Worker-Rollout ist erforderlich, solange der Apply-Schalter auf `false` bleibt.
