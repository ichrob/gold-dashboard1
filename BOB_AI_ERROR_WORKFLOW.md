# Bob – gemeinsame Fehlererkennung und Reparatur durch ChatGPT + Gemini

Stand 11. November 2026. Die bestehende GitHub-/Render-Infrastruktur wird benutzt,
**kein** zusätzliches kostenpflichtiges KI- oder Monitoring-Abonnement.

## 1. Was Bob erkennt

- Betriebs- und Servicestatus von Scanner, Push, Quellen, Live-Kerzen und
  Hintergrunddiensten über die unabhängigen Gesundheitswächter;
- Produkt-/KO-/Hebel-/Kurs- und DEGIRO-Nachweislücken sowie Android-Import;
- laufende Paper-Konten, Originalstudien, Frühwarnungen und Zeitstempel;
- ab diesem Ausbau auch Haupt-GitHub-Tests: Bob CI, Live-Smoke,
  Collection Health und Self-Healing-Wächter selbst.

Die in `bob_issue_watchdog.CODES` definierten, festen **öffentlichen**
Fehlercodes sind kein Beleg für eine vollständige Codepfad-Abdeckung.
Unbekannte semantische, finanzielle oder Android-UI-Probleme bleiben möglich.
Ein Test ohne Originalnachweis darf keine Heilung behaupten.

## 2. Zuständigkeiten und harte Übergaben

1. **Bob prüft:** Betrieb nur nach tatsächlich beobachteten Quellenzeiten
   sowie zwei Gesundheitsabfragen. Ein Workflow-Fehler wird ausschließlich
   aus einem vom eigenen Repository abgeschlossenen GitHub-Event abgeleitet.
   Nachts oder am Wochenende sind normale Handelspausen kein Alarm.
2. **Dedup-/Issue-Stufe:** Ein Fehlertyp erhält ein bestehendes oder neues
   GitHub-Issue mit festem Code, ohne private Kurse, ISINs, Logs oder Tokens.
   Fehler-PRs referenzieren die maschinenlesbare Fallkennung
   `BOB-<Issue>-<Code>`. Einzelne neue Fehler erweitern nicht die Rechte.
3. **ChatGPT-Reparaturwächter:** Ist **einziger** Entwickler/Repair-Owner
   für diesen Fall. Nach Ursachennachweis minimaler PR plus Regression.
   Die bereits eingerichteten ChatGPT-Automationen können die Issues prüfen;
   das GitHub-Issue selbst startet **kein** neues ChatGPT-Gespräch.
4. **Gemini:** Optionaler unabhängiger, auf öffentliche Patches
   beschränkter Prüfer. Nur bei explizitem Free-only-Opt-in und verifiziertem
   Aufruf. Ohne tatsächlich erhaltenen Gemini-Kommentar ist das Ergebnis
   `not-reviewed`, nicht `approved`.
5. **Abnahme:** PR-Tests, CodeQL/Risiko, Merge, Render-Buildgleichheit,
   originale Livebeobachtung und unabhängiger Beleg. Danach kann ein
   Fehler als nachweislich behoben bezeichnet werden.

## 3. Kein falsches Schließen

Insbesondere GitHub-Hauptprüfungen können **nicht** durch einen
unabhängigen gesunden `/health`-Poll als repariert gelten.
Produktnachweise, fehlende Daten, KO-Schutz und Studien ohne gültige
Originale sind ebenfalls nicht durch bloßes Verschwinden eines Fehlercodes
geheilt. Jeder Fehler erfordert seine eigene Evidenz.

## 4. Grenzen, Kosten und Priorität

Priorität: aktive schwere Laufzeitfehler > erneute Regressionen >
unentscheidbare neue Originalfälle > historische Unvollständigkeiten.
Schwere echte Handelssignale bleiben von bloßen Diagnosebenachrichtigungen
getrennt. Keine Meldungsflut aus gesunden Wiederholungsprüfungen.

Kein automatischer Orderabschluss, kein Stop-/KO-Lockern, keine erfundenen
Nettoergebnisse, keine privaten Rohdaten im öffentlichen GitHub,
keine dritte kostenpflichtige KI und kein automatischer KI-Merge.

## 5. Offene praktische Abnahmen

- GitHub workflow_run-Rechte, fehlgeschlagenes **synthetisches Event**
  offline nachstellen, auf echten Fehler **nicht** absichtlich
  einen Produktionsdienst ausschalten.
- Ein neuer Incident muss dedupliziert und als Handoff erkennbar sein.
- Ein normaler gesunder Lauf darf den GitHub-Incident **nicht** schließen.
- Optionaler Gemini-PR-Review braucht echten Modellkommentar.
- Eine tatsächliche ChatGPT-Reparatur braucht GitHub-PR, grüne
  Regressionen und datierte Render-/Live-Prüfung.

Die Datei dokumentiert Sicherheits- und Zuständigkeitsregeln, nicht eine
Garantie, dass jede mögliche Softwareabweichung entdeckt oder repariert wird.
