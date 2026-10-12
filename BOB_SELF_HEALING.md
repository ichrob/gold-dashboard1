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
