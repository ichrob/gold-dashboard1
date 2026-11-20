# Bob: Cloudflare Observability FREE -> eine Fehlerzentrale

Stand: 20. November 2026, Europe/Zurich.

## Zweck

Cloudflare ist eine **zusätzliche Diagnosequelle**, kein Handelsmotor, keine
neue Fehler-Push-Zentrale und keine unabhängige Reparaturinstanz. Die vorhandene
ChatGPT-Automation **„Bob – Fehlerzentrale“** ist und bleibt einziger
nutzerseitiger Kanal. Das vorhandene GitHub- und Render-Reparaturverfahren ist
maßgeblich. Kein Cloudflare-Feature darf eine echte Gold-/DEGIRO-Order auslösen,
eine Oracle-VM kostenpflichtig starten, KO-Sperren umgehen oder eine GitHub-CI
überspringen.

## Bereits LIVE konfigurierte Konto-Einstellungen (separat von dieser PR)

Für genau vier vorhandene Cloudflare-Worker wurden am 20.11.2026
Observability-Logs (100%-Head-Sampling), URL-Query-Redaction und
**Issues.enabled=true** per Cloudflare API gesetzt und anschließend gelesen:

- `bob-watchdog-clock`
- `proud-gold-scanner-background-416f`
- `bob-oracle-a1-retry`
- `bob-free-ai-review`

Dabei blieben Traces aus, Logpush aus und es wurden weder Worker noch
Zusatz-Abos erzeugt. Cloudflare-Issues war zum Zeitpunkt dieser Änderung eine
**kostenlose Open Beta**; Preis-/Planänderungen erneut prüfen.

**Keine Live-Fehlersicherheit ableiten:** Am 20.11. zeigte Issues Summary
0 aktive Issues. Dies ist ausdrücklich kein Beweis, dass alle Worker fehlerfrei
oder überhaupt kürzlich ausgeführt wurden. Beim Oracle-Worker gilt der
Cron von 30 Minuten als Konfiguration, nicht als nachgewiesene erfolgreiche
OCI-Aktion. `ENABLED`, `ALLOW_APPLY` und
`PLAN_VERIFIED_ALWAYS_FREE` bleiben alle `false`.

Vorhandene Cloudflare-Abfragen (bereits im Konto gespeichert):

- `Bob – Worker-Protokolle (kostenlos)`:
  `4lwgrwrbau9fd4y66k4w01vx`
- `Bob – Fehler & Ausnahmen (kostenlos)`:
  `lqw7048bj5tdhbbfi8vo5ffn`

Die `/usage`-API lieferte für das separat angefragte Fenster 19.11. bis
20.11.2026 ca. 647 erfasste Ereignisse (Stand der manuellen Abfrage). Das ist
keine Rechnungs-, Kontoplan- oder komplette Service-Verfügbarkeitsbestätigung.

## Quellcode-Integration in dieser PR

`bob_cloudflare_observability.py` normalisiert ausdrücklich **nur**
autorisierte read-only Cloudflare-Responses auf feste Worker-Namen und
Zahlenwerte. `central_digest(...)` liefert Coverage, erlaubte Datenvolumen-
Information, aggregierte Issue-Zähler und stets `healthy: null`: Ein
leeres Issue-Ergebnis ist niemals ein Recovery-Beleg. Keine unkontrollierte
Servicebezeichnung, Roh-Exception, Stacktrace, Anfrage-URL, Header, ISIN,
Preis, PIN oder Token darf in Bobs öffentliches GitHub oder einen Push gelangen.

Der Adapter tätigt keine Netzwerkanfragen, schreibt keine Issues und ersetzt
keinen schon laufenden Wächter. Seine Testfälle laufen automatisch über das
bereits vorhandene `python -m unittest discover` in Bob CI.

Die drei von Bob selbst verwalteten Worker-Konfigurationen sind
als Wrangler-Manifeste vorgehalten:

- `ops/cloudflare-watchdog/wrangler.jsonc`
- `ops/oracle_a1_retry/wrangler.jsonc`
- `ops/cloudflare-ai-review/wrangler.jsonc`

Sie deklarieren die kostenlose Observability-Basis, Issues, URL-Redaction,
ausgeschaltete Traces und Source-Map-Uploads. Bei Oracle bleiben die
Schutzschalter im Manifest `false`; bei KI-Prüfung bleibt das bestehende
`AI`-Binding genannt. Der vierte historische Scanner ist im GitHub-Projekt
nicht als vollständig verifizierte Wrangler-Quelle identifiziert: Hier
keinen Ersatz-Code und keine riskante Neuveröffentlichung erfinden.

**Wichtig:** Diese GitHub-Konfigurationen gelten NICHT durch den Merge als
bereits auf Cloudflare ausgerollt. Ein späterer Cloudflare-Worker-Rollout muss
die tatsächlichen Produktions-Bindings/Secrets, aktiven Cron-Zeiten und
Veröffentlichungsrouten vorher/nachher unabhängig bestätigen. Nie blind
`wrangler deploy` auf Oracle/AI ausführen; es darf weder ein OCI-Secret
verloren gehen noch eine gesperrte Aktion entsperrt werden.

## Zentraler automatischer Ablauf

Die bestehende stündliche ChatGPT-Fehlerzentrale besitzt eine ergänzende
Cloudflare-Prüfanweisung, sofern ihre verbundene Cloudflare API im Lauf
tatsächlich verfügbar ist. Sie darf nur:

1. Bestehende Workers samt Observability-Konfiguration und genau benannte,
   eng begrenzte Aggregat-Abfragen über die autorisierte Verbindung lesen;
2. Issue-Zähler, betroffenen Worker und Laufzeit-/Fehlerindikatoren prüfen;
3. Befunde mit bestehenden Bob-GitHub-Fällen und dem zuständigen
   KI-Reparatur-Owner korrelieren (Dedup, Originalnachweis, CI, Render);
4. Nur neue **wesentliche belegte** Störungen in einer zentralen Meldung
   zusammenfassen; sonst still bleiben.

Keine Cloudflare-Issue-Automation/Cloudflare-Pushs, keine neuen
GitHub-Actions-Secrets, kein zweiter Cloudflare-Worker und kein dauerhaftes
Cloudflare-API-Token im öffentlichen Repository. Fehlt im Zentralenlauf die
Cloudflare-Verbindung, ist der Zustand `unknown`, nicht `healthy`.
Die Ausführung der Zentralen-Automation und tatsächliche Zustellung müssen
gesondert am nächsten Lauf bewiesen werden.

## Kosten und Grenzen

Die damals öffentlich dokumentierte Free-Stufe bietet ab dem
**1. Dezember 2026** `0,5 GB` Ingestion pro Tag und sieben Tage
Aufbewahrung für die eingeschlossenen Observability-Datensätze.
Bei Free stoppt die Ingestion am Tageslimit, anstatt ein Upgrade
vorzunehmen. Die in `bob_cloudflare_observability.py` enthaltene
Warnschwelle von 400 MB bezieht sich nur auf *beobachtete Daten im expliziten
Abfragezeitfenster*, **nicht** auf eine verifizierte tägliche
Gesamtrechnung. Das Modul verändert selbst keine Sampling-Einstellungen.

Vor jedem zusätzlichen Log-/Trace-Volumen erneut Free-Plan und aktuelle
Preise prüfen. Keine Paid-Logpush-Ziele, Browser-Rendering-Abos,
AI-Bezahldienste, Cloudflare-Paid-Fallbacks oder Freigabe von Oracle-Apply.
Auch bei Free können Tageslimits Diagnosen abschneiden.

## Android / DEGIRO

Die vorhandene Android-Komponente `ProductReadDiagnostics.kt` erfasst
bereits feste, anonymisierte Suchfeld-Indikatoren wie
`SEARCH_INPUT_NO_EDITABLE`, `SEARCH_INPUT_TRACKED_QUERY_MISSING`,
`SEARCH_INPUT_TAP_REJECTED` und `SEARCH_FOCUS_REJECTED`. Der bestehende,
auf dem Handy freizugebende HTTPS-Diagnosetransport geht zum Bob-Scanner/
Fehlerpfad, **nicht direkt zu Cloudflare**. Auf diesem Weg kann die
Fehlerzentrale ein DEGIRO-Hängenbleiben zeitlich mit einem Worker-Ausfall
vergleichen, ohne PIN, Textinhalt oder eine ISIN offenzulegen.

Die Cloudflare-Änderung kann weder automatisch das Samsung entsperren noch
ein verdecktes DEGIRO-Eingabefeld fokussieren. Für diesen Fehler ist weiterhin
ein originaler Samsung-Praxistest und eine eigenständige App-Korrektur nötig.

## Abnahmekriterien

- `python -m unittest test_bob_cloudflare_observability test_cloudflare_observability_config`
- Vollständige Main-/PR-CI, keine Abschwächung bestehender Signale/KO-Sperren.
- Nach Auslieferung: Cloudflare-Worker-Settings für alle vier getrennt
  auslesen; Logs/Issues und unveränderte Oracle-Flags nachweisen.
- Mindestens einen frischen Cloudflare-Cron-Protokolleintrag beobachten;
  kein künstlicher produktiver Ausfall.
- Ein bereits bekannter Bob-Fehler muss dedupliziert bleiben; keine
  neue Einzel-Push-Serie.
- Fehlende neue Logs oder leere Issue-Liste dürfen keinen offenen Fehler
  automatisch schließen.
- Source Maps erst als „live“ ausweisen, wenn der Cloudflare-Build sie
  tatsächlich hochgeladen hat.

## Cron-Laufnachweise (Erweiterung vom 20.11.2026)

Zusätzlich ist im bestehenden Cloudflare-Konto die **kostenlose, read-only**
gespeicherte Abfrage `Bob – Letzte Cron-Ausführung (kostenlos)` mit ID
`ykuxjok2rrtscwcolvxaol6d` angelegt und durch einen echten
Observability-Query-Test bestätigt. Sie führt
`max($workers.event.scheduledTime)` gruppiert nach
`$metadata.service` aus und erfasst keine neuen Rohlogs. **Zeitwert in
Unix-Sekunden, nicht Millisekunden.** Der aktuell gemessene Cron-Tick ist ein
Cloudflare-Protokollbeleg, kein Erfolg von Oracle Apply oder GitHub Dispatch.

Der Python-Adapter
`summarize_cron_receipts(response, now_epoch_seconds=...)`
akzeptiert nur zwei aktuell bekannte Cron-Worker, verifiziert das
Antwortformat und berechnet rein numerische Alterswerte:

- `bob-watchdog-clock`: konfiguriert alle 10 Minuten;
- `bob-oracle-a1-retry`: konfiguriert alle 30 Minuten.

`recent` bedeutet protokollierter Tick innerhalb von drei Sollabständen,
`old-observation` bedeutet ein älterer letzter Tick und `not-observed`
bedeutet kein Nachweis im konkret abgefragten Zeitfenster. **Keiner**
dieser Zustände ist allein der Nachweis, dass der Worker insgesamt gesund,
Oracle aktiv oder ein GitHub-/Render-Reparaturfall geschlossen wäre.
API-Ausfall, unzulässiges Datum oder unlesbare Aggregationen geben
`unknown` zurück. Nie eine *neue* Störungsbenachrichtigung nur wegen
einer einzelnen fehlenden Zeitreihe; erst Original-Cron/Schedule
und zwei unabhängige frische Abrufe prüfen, danach in der
bestehenden Fehlerzentrale deduplizieren.

Die bereits aktiven und kostenlosen zwei Fehler-/Usage-Abfragen bleiben
unverändert; kein zusätzlicher Cron, kein Worker, keine Cloudflare-Automation,
kein kostenpflichtiger Dienst, kein neues Secret.



## Source-Maps: Live-Prüfung und offline CI-Gate (20.11.2026)

Die Cloudflare-Live-Abfrage `GET /accounts/{account_id}/workers/workers/{worker_id}/versions/latest?include=modules,sourcemaps` ergab am 20.11.2026 für alle vier Worker **0 Module vom Typ `application/source-map`**. Dies ist ein tatsächlicher Live-Befund, nicht nur eine Vermutung aus den Wrangler-Konfigurationsdateien. Die Source Maps gelten daher **noch nicht als live hochgeladen**. Cloudflare veröffentlicht Source Maps beim Worker-Deployment/Version-Upload; das bloße Speichern von `upload_source_maps: true` löst keinen Upload aus. Die historische Scanner-Worker-Quelle ist weiterhin nicht als überprüfbares Wrangler-Manifest nachgewiesen.

Die neue, ausschließlich lokale CI-Prüfung baut die **drei im Repository verwalteten** Worker mit Wrangler `4.158.0` per `deploy --dry-run --outdir`. `tools/cloudflare_source_map_check.py` verlangt für jeden Build mindestens eine gültige V3-Source-Map mit Quellbezug und Mapping-Daten. Nur Dateianzahl/Feststatus wird protokolliert, keine `sourcesContent` oder Secrets. Das ist **kein** Cloudflare-Deployment und benötigt weder API-Token noch zusätzliche Cloudflare-Worker, Cron-Jobs, Traces oder kostenpflichtige Funktionen.

Vor einer echten Source-Map-Veröffentlichung müssen alle aktiven Worker-Versionen, Bindings und Secrets geprüft, Oracle-Freigaben `ENABLED=false`, `ALLOW_APPLY=false`, `PLAN_VERIFIED_ALWAYS_FREE=false` unverändert gehalten und die ursprüngliche Deploymentroute nachgewiesen werden. Automatisches Überschreiben bestehender Worker ohne diese Belege ist nicht erlaubt. Nach einem kontrollierten tatsächlichen Upload `versions/latest?include=modules,sourcemaps` erneut **lesend** prüfen; erst bei vorhandenem `application/source-map`-Modul `live=true` vermerken. Niemals absichtlich Produktionsfehler erzeugen, um Source Maps zu testen. Ein bestandenes CI-Gate beweist nur, dass sich valide Maps *erzeugen* lassen, nicht dass alle Source Maps auf Cloudflare vorhanden sind.
