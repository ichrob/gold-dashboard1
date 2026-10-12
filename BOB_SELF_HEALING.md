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
