# Bob: Fehlererkennung, Selbstheilung und KI-Hilfe

## Automatischer Ablauf

1. Beim Start und in der öffentlichen Gesundheitsprüfung von Bob werden bekannte Hintergrund-Worker geprüft. Gestoppte Worker (Marktdatensammlung, Fibonacci-/Trade-Überwachung, Strategieforschung) dürfen nur über die bereits vorhandenen Startfunktionen neu gestartet werden; der Versuch ist auf einmal pro 180 Sekunden und Fehlertyp begrenzt.
2. Ein unabhängiger GitHub-Workflow (`.github/workflows/bob-self-healing.yml`) kontrolliert Bob, die Hintergrundüberwachung und den Push-/Datenbankdienst alle zehn Minuten. Bei einem Fehler erfolgt nach 15 Sekunden ein weiterer Check.
3. Ist die Störung weiterhin vorhanden, legt der Wächter **eine** offene GitHub-Issue mit dem Titel `[Bob KI-Hilfe] Ungelöste Gesundheitsstörung` an. Bestehende offene Issues werden nicht dupliziert. Sobald die überwachten Dienste wieder gesund sind, wird die Issue automatisch geschlossen und bleibt als Archiv erhalten.
4. In Bob: **Fehlerüberwachung & Selbstreparatur** aufklappen, aktuellen Zustand ansehen, **KI-Hilfebericht kopieren** und in ChatGPT senden. Alternativ die entsprechende GitHub-Issue öffnen.

## Grenzen und Datenschutz

Das GitHub-Repository und seine Issues sind **öffentlich**. Die automatisch angelegten Issues enthalten deshalb nur feste Diagnosecodes, Prüfuhrzeit und den Standard-Arbeitsauftrag. Keine Logs im Rohformat, Personendaten, privaten Produktlisten, Zugangsdaten, Tokens, Handelsinformationen oder Transaktionen.

Der Ereignisverlauf im Bob-Webprozess ist flüchtig und wird bei einem Neustart zurückgesetzt. Die GitHub-Issues sind das dauerhafte Archiv externer Störungen. GitHub Actions können mit Verspätung laufen oder selbst vorübergehend ausfallen. Der Takt ist also keine garantierte Überwachung im 10-Minuten-Sekundentakt.

Bob führt **keine selbstständigen Codeänderungen, Echtgeldorders oder Änderungen von Handelsstrategien/Risikoregeln** durch. Die automatischen Maßnahmen sind auf sichere Neustarts und vorhandene Datenabruf-Wiederholungen beschränkt. Unbekannte Probleme werden für die spätere KI-Unterstützung dokumentiert. Ein automatischer Aufruf eines kostenpflichtigen KI-Modells ist nicht erforderlich und nicht eingerichtet.

## Technische Prüfung

- Unit-Tests: `python -m unittest test_bob_self_healing.py`
- Gesamttests: GitHub-Workflow `Bob CI`
- GitHub → Actions → `Bob independent self-healing escalation` → `Run workflow` für eine manuelle unabhängige Probe
- GitHub → Issues → Titel `Bob KI-Hilfe` für das Archiv.

Zusätzliche Render-Umgebungsvariablen sind nicht erforderlich. Der Wächter nutzt das von GitHub Actions bereitgestellte `GITHUB_TOKEN` mit begrenzter Berechtigung `issues:write`.


## Eigene Sparte „Problem“ (12.10.2026)

Im mobilen Hauptmenü von Bob gibt es einen zusätzlichen Reiter **Problem**.
Daneben steht eine rote Zahl für die Anzahl der **offenen, dauerhaft gespeicherten KI-Hilfeanfragen**:
- Erstes ungelöstes Problem: **1**
- Zweite unabhängige Fehlerart: **2**
- Weitere Fehler: **3, 4, …**
- Nach unabhängig bestätigter Behebung sinkt die Zahl wieder; das Archiv bleibt auf GitHub erhalten.
- Das reine Lesen der Meldung löscht sie nicht.

Jeder Diagnosecode erhält beim unabhängigen Wächter seine **eigene GitHub-Issue** mit sanitisiertem Standardbericht; dieselbe weiterhin aktive Fehlerart wird nicht dupliziert. Unter `Problem` erscheinen pro Fall Erkennungszeit, Fehlerbeschreibung, GitHub-Link und **KI-Hilfebericht kopieren**. Der vorherige Bereich `Fehlerüberwachung & Selbstreparatur` befindet sich jetzt ebenfalls in dieser Sparte.

Der authentifizierte, lesende Endpunkt `/api/problems` lädt ausschließlich GitHub-Issue-Titel aus einer festen Allowlist und liest weder Freitexte noch fremde Issues aus. Servercache 90 Sekunden. Bei GitHub-Ausfall zeigt Bob „nicht erreichbar“ oder „letzter Stand“, **niemals fälschlich 0**. GitHub Actions prüft weiterhin ungefähr alle 10 Minuten: neue Fälle können dadurch mit Verzögerung angezeigt werden.

Der Zähler bedeutet **noch offene KI-Hilfeanfragen**, nicht ungelesene Meldungen. Bei 0 ist die Zahl ausgeblendet. Keine Veränderung am Trading oder den Risikoregeln.

## Zeitstempel und dauerhafte Erfolgsstatistik (12.10.2026)

Im Menüpunkt **Problem → Offene KI-Hilfeanfragen** wird die letzte erfolgreiche Abfrage der GitHub-Issue-Liste mit **Datum und Uhrzeit in Europe/Zurich** angezeigt. Für jeden einzelnen Eintrag werden **Erkannt** und **Letzte Änderung** getrennt ausgewiesen. Während einer Störung zeigt die Oberfläche weiterhin den Zeitpunkt der letzten bestätigten Aktualisierung, nicht fälschlich die aktuelle Uhrzeit.

Unter **Bobs automatische Fehlerbehebung** werden vier Kennzahlen aus dem privaten PostgreSQL-Archiv angezeigt:
- **Selbstständig erkannt**: dokumentierte Störungsereignisse aus den überwachten Komponenten, keine absolute Zahl aller Codefehler.
- **Selbst repariert · geprüft**: ausschließlich Worker-Neustarts, die nach dem Versuch in mindestens zwei Prüfungen mit mindestens 20 Sekunden Abstand als gesund bestätigt wurden.
- **Ohne bestätigten Neustart wieder gesund**: Probleme, die später nicht mehr festgestellt wurden; eine von Bob verursachte Reparatur wird damit ausdrücklich **nicht** behauptet.
- **Reparaturversuche**: angestoßene, erlaubte Neustarts (einschließlich erfolgloser Versuche).

Der neue Zähler startet **erst ab Aktivierung der dauerhaften Erfassung**; ältere flüchtige Ereignisse können nicht nachträglich vollständig rekonstruiert werden. Aufbewahrung im bereits bestehenden privaten PostgreSQL ohne automatische Löschung dieser kleinen, strikt standardisierten Ereignisse. Die Daten bleiben bei regulären Render-Neustarts erhalten. Ein asynchroner Ereignispuffer versucht die sichere Zustellung erneut, ist aber während eines vollständigen App-Ausfalls selbst nicht lückenlos. Bei Datenbankausfall erscheinen ausdrücklich **unbekannte/alte Werte**, keine erfundenen Nullen.

Der unabhängige GitHub-Wächter bleibt für nicht behobene KI-Hilfeanfragen zuständig. Der neue lokale 30-Sekunden-Wächter erkennt abgestürzte Worker auch bei geschlossener App und versucht ausschließlich die bekannten idempotenten Restart-Methoden. **Keine** selbstständigen Quellcodeänderungen, Trades oder neue externe Kosten.


## Automatic product-source and retained-list recovery (14 October 2026)

New checksum-valid SG-family identities (FC/FD/FE/FG/SQ) are looked up by exact ISIN. A German identity HTTP 404 triggers one Swiss lookup; a verified market is remembered for the process lifetime. Each response still has to match ISIN, issuer product ID, market, currency, classification and Gold underlying. Access denials, malformed responses and mismatched market replies do not trigger country fallback. Native CHF observations use the existing dated FX conversion rules.

When Bob is open, stored original list images containing invalid ISIN rows are reread automatically after startup/upload and at most once per 30 minutes. The reread must retain all known IDs and provide a unique checksum-valid confusable-glyph correction with matching direction. Corrected rows are then checked through the normal issuer refresh. Valid product evidence, original files and upload timestamps are retained; rereading never refreshes source clocks. Concurrent uploads or manual edits invalidate an in-progress reread. Unresolved rows remain blocked. This browser-side OCR cannot run while the app is closed; server-side source retrieval continues through the existing background workflow.

## Gesamtprüfung aller acht Bob-Bereiche (15.10.2026)

Im Menü **Problem** zeigt die standardmäßig eingeklappte **Gesamtprüfung** einen Status für Übersicht/Marktanalyse, Gold-Hebelprodukte, Mein Trade, Vollautomatisch, Zukunft, YouTube/Recherche, Lernen/Simulationen und Problem/KI-Hilfe. Die Gesamtprüfung wird erst nach Aufbau der Navigation ausschließlich dort eingebunden; zusätzliche Bereichszeichen im mobilen Menü entfallen. Im aufgeklappten Menü gilt: **✓** für belegte Prüfungen, **⚠** für Probleme und **?** für fehlende Nachweise. Auch wenn etwa der Feed erreichbar ist, gelten unbestätigte Untertitel, simulierte Ausführungen oder eine ungeprüfte Stop-Loss-Position **nicht** als fehlerfrei. Ein Haken ersetzt niemals eine Produkt-/Handelsfreigabe.

Der Browser prüft beim Anzeigen von Bob und dann etwa alle zwei Minuten, solange die App sichtbar und angemeldet ist. Dafür verwendet er die bereits vorhandenen lesenden Endpunkte für System/Markt, Hintergrundüberwachung, Live-Analyse, privaten Produktbericht, Videorecherche, Zukunftsforschung und das öffentliche KI-Hilfe-Archiv. Er ändert keine Trade-/Risikoregeln, veröffentlicht keine ISINs und verschickt keine Push-Nachrichten. Ohne laufenden Browser bleibt der bereits existierende **unabhängige** GitHub-Gesundheitswächter zuständig; die neue Gesamtprüfung ist keine dauerhafte vollständige Funktionstestabdeckung aller Browser-/Brokerabläufe.



## Rueckkanal ChatGPT ↔ Bob und Handy-Anzeige (15.10.2026)

Die bestehende GitHub-Action `.github/workflows/bob-self-healing.yml` erfasst technische Stoerungen ca. alle 10 Minuten und legt pro allowlistiertem Fehlertyp eine sanitisiert oeffentliche Issue `[Bob KI-Hilfe] …` an. Zusaetzlich kann ein eigenstaendiger ChatGPT-Reparaturwaechter diese offenen Issues einmal pro Stunde ueber separat verbundene GitHub- und Render-Werkzeuge bearbeiten. GitHub-Action und ChatGPT-Waechter sind unterschiedliche Prozesse; ein GitHub-Issue allein startet keine neue ChatGPT-Sitzung.

Der ChatGPT-Waechter kann bei einem bereits existierenden, offenen Issue einen dieser **exakten Marker** in die Issue-Beschreibung eintragen; immer nur ein aktueller Statusmarker, alleine in eigener Zeile:

- `<!-- BOB_KI_STATUS:in-progress -->` — KI prueft die Ursache
- `<!-- BOB_KI_STATUS:testing -->` — Reparatur in technischer Pruefung
- `<!-- BOB_KI_STATUS:waiting-for-evidence -->` — Originalnachweis fehlt weiterhin
- `<!-- BOB_KI_STATUS:waiting-for-review -->` — Aenderung wartet auf Freigabepruefung

Ohne gueltigen Marker wird in Bob **Wartet auf KI-Pruefung** gezeigt, selbst wenn das Issue schon lange existiert. Die Statusanzeige ist *kein Nachweis*, dass die automatische Aufgabe bereits gelaufen ist oder eine Reparatur funktioniert. Bei Erfolg muss die KI sichere Aenderungen testen, die PR/Deployment referenzieren und den Befund im Issue dokumentieren. Eine technische Health-Wiederherstellung kann die vorhandene GitHub-Action nach bestaetigter Nachpruefung schliessen; fehlende Produkt-Originalnachweise niemals allein wegen fehlender Fehlercodes schliessen.

Bobs mobiles **Problem**-Panel liest ausschliesslich die exakt erlaubten Marker aus Issue-Beschreibungen vom Repository-Eigentuemer bzw. GitHub-Actions-Bot. Rohe Freitexte, Logs und sonstige Daten werden **nicht** an die UI weitergereicht. Der Browser-Fallback folgt derselben Marker-Allowlist. Kein KI-Status verleiht Handelsfreigabe; unveraenderte Sicherheitsgrenzen gelten. Bei fehlender GitHub-Verbindung zeigt die Anzeige alte/ungewisse Daten statt einer erfundenen Erfolgsmeldung.

Die automatische ChatGPT-Pruefung ist auf hoechstens stuendlich konfiguriert; Laufzeiten, verfuegbare App-Werkzeuge und moegliche Host-Berechtigungsabfragen sind nicht garantiert. Der Nutzer moechte ausschliesslich Status in **Problem**, keine allgemeinen ChatGPT-Pushs oder E-Mails fuer diese KI-Hilfe. Es gibt keine unaufgeforderte Uebertragung privater ISIN-Listen, Zugangsdaten oder Rohlogs in oeffentliche GitHub-Issues.
