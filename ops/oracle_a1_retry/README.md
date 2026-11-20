# Bob Oracle A1 — unabhängiger 30-Minuten-Startwächter

Status (2026-11-20): `bob-oracle-a1-retry` als Cloudflare Worker veröffentlicht, Cron `*/30 * * * *` aktiv, **Oracle-Apply bewusst deaktiviert**, solange keine geprüfte OCI-API-Anbindung vorliegt.

## Funktionsweise

- Cloudflare Cron läuft serverseitig unabhängig von Samsung und Oracle Cloud Shell.
- Nur `eu-zurich-1`, OCI Resource Manager: übernimmt **ausschließlich** den zuvor geprüften Terraform-Plan (`FROM_PLAN_JOB_ID`).
- Stoppt bei laufenden Jobs, bei bereits erfolgreich abgeschlossenem Apply, unbekannten Fehlern, kaputtem/fehlendem Plan und unklaren Zuständen.
- Wiederholt frühestens nach 25 Minuten und nur nach einem im letzten Apply-Log bestätigten Oracle-Kapazitätsfehler. Die Cron-Triggers liegen 30 Minuten auseinander.
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

Die private Schlüsseldatei ist **kein** Oracle-/DEGIRO-PIN und darf nicht in Bob-Logs, Chat-Nachrichten oder GitHub stehen. Bei PKCS#1 den Schlüssel lokal sicher nach PKCS#8 konvertieren (z. B. `openssl pkcs8 -topk8 -nocrypt`). Nur API-Rechte für den vorhandenen Oracle Resource-Manager-Stack und dessen Jobs einrichten (OCI benötigt `ORM_JOB_MANAGE` und `ORM_STACK_USE`).

Die drei Standardschalter bleiben bis zur abgeschlossenen Prüfung **false**:
`ENABLED`, `ALLOW_APPLY`, `PLAN_VERIFIED_ALWAYS_FREE`.

Nach Schlüsselanlage und Überprüfung zunächst mit deaktiviertem Apply Log/Status prüfen, dann alle drei Schalter bewusst auf `true` setzen. Bei jedem anderen Fehler bleiben sie `false`. Keine automatische Kostenfreigabe. Oracle Free Trial/Always-Free-Kontingente und Kontolimits sind separat zu prüfen.

## Tests, Beobachtung, Not-Aus

Lokale Schutzlogiktests: `node ops/oracle_a1_retry/worker.test.mjs`.
Cloudflare: Worker > Observability > Logs; Statuscodes `disabled`, `job_in_progress`, `already_succeeded`, `not_a_capacity_failure`, `apply_submitted`.
Not-Aus: `ENABLED=false` in Cloudflare.
Die bestehende Cloud-Shell-`bob-a1-v4.sh` nicht parallel starten, solange die Cloudflare-Automatik aktiv ist. Cloudflare Cron kann verzögert starten, daher sind 30 Minuten eine Soll-Frequenz, kein Echtzeitversprechen.
