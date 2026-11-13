# Bob KI-Studienwache — Release-Abnahme, 11.11.2026

Der vollständig geprüfte PR [#1543](https://github.com/ichrob/gold-dashboard1/pull/1543) wurde als identischer getesteter Commit `6ca173c6271b800203ade06048a78f8d326567f9` auf `main` übernommen. CI, Risiko, Security/CodeQL und Reparaturnachweise sind erfolgreich.

Dieser **ausschließlich dokumentarische** Commit löst einen regulären GitHub-`main`-Push aus, nachdem Render bisher noch den älteren Commit `09676c72accfa80d1dd4925b228f58d7405d50f7` als `live` zeigte. Renders `checksPass`-Regel bleibt unangetastet: Kein manueller, ungeprüfter Deploy.

**Fachliche Abnahme nach Produktivbereitstellung:**
- Scanner und Push-Dienst führen einen Commit aus, der `6ca173c6` enthält.
- Der öffentliche Push-`/health`-Status liefert ausschließlich `studyHealth` mit `scope=bob-original-study-watchdog-v1`, `codes`, `status`, `readOnly=true`, `realOrders=false`.
- Nacht-/Wochenendpause: `status=paused`, keine Studienwarnungen. Morgendliches Paper-Warmup erzeugt keinen veralteten Worker-Fehlalarm.
- Bei echten neuen Originaldatenstörungen erfolgt die GitHub-Watchdog-Doppelprüfung, nur ein Issue pro Fehlercode und ein idempotenter Reparaturübergabekommentar. Gemini-Review bleibt optional und wird ohne echten Kommentar nicht behauptet.
- Keine Produktdaten, Rohlogs, Korrekturen an Handelsrisiko oder echten Orders.

Keine simulierten Vorfälle in der produktiven Datenbank anlegen. **Ohne echten zukünftigen Fehler kann das automatische Eröffnen eines Vorfalls nur mit Regressionstests, nicht anhand eines Live-Störfalls nachgewiesen werden.**
