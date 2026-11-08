# Bob: kostenlose zweite KI für Code-Zweitprüfungen

## Ziel und Einschränkungen
Die bestehende Gemini-Android-Planung und die bestehenden KI-Reparaturwächter bleiben unverändert. Ein **unabhängiges** Modell (Cloudflare Workers AI, @cf/zai-org/glm-4.7-flash) kann bei Bedarf einen **öffentlichen GitHub-Pull-Request** auf erkennbare Fehler, Regressionen und fehlende Tests prüfen. Ergebnis: ein ausdrücklich unverbindlicher PR-Kommentar. Es gibt keinen automatischen Code-Patch, Merge, Deploy, Zugriff auf Bob-Datenbanken, DEGIRO oder Echtgeldorders. Kein laufender Render-Prozess und kein zusätzlicher Render-RAM-Bedarf.

## Kostenloser Betrieb / harte Abschaltung
Cloudflare Workers Free bietet 10.000 Neurons/Tag ohne Überziehungskosten; oberhalb der kostenlosen Grenze schlagen Anfragen fehl. Auf einem **Workers Paid** Konto kann bereits eine einzige AI-Anfrage Kosten auslösen, wenn die freie Tagesgrenze erschöpft ist. Das Script kann die Cloudflare-Abrechnung NICHT selbst feststellen. Deshalb ist alles standardmäßig **ausgeschaltet** und darf erst nach Prüfung **Workers Free (keine bezahlte Stufe, keine prepaid credits)** freigeschaltet werden. Das Free-Gate ist eine Betreiberbestätigung und keine technische Abrechnungssperre beim Anbieter.

## Aktivierung nur nach Free-Plan-Prüfung
1. Cloudflare Dashboard → Workers & Pages / Workers AI → Account-Plan überprüfen. Nur kostenloser Workers-Plan.
2. In Cloudflare einen **eng begrenzten API-Token ausschließlich für Workers AI-Inference** anlegen. Keine Accountverwaltung, DNS-Rechte oder Änderungen zulassen.
3. In GitHub → Repository → Settings → Secrets and variables → Actions zwei **Secrets** setzen:
   - BOB_CF_AI_ACCOUNT_ID = Cloudflare-Konto-ID
   - BOB_CF_AI_TOKEN = eben erstellter eng begrenzter API-Token
   Geheimnisse niemals in Chat, Issue, PR oder Repository-Quelltext einfügen.
4. Erst nach bestätigtem Workers-Free-Status in GitHub Actions **Variable** setzen: BOB_AI_FREE_ONLY = confirmed-workers-free.
5. GitHub Actions → „Bob zweite KI - kostenlose Code-Zweitprüfung“ → Run workflow → Nummer eines offenen PR eingeben.

Pro manuellem Aufruf exakt **eine** Cloudflare-Inference (kein Retry, kein paid fallback). Der Code übermittelt nur bis zu fünf kurze, gefilterte Diffs aus dem öffentlichen Bob-Repository; erkannte Secret-Muster und andere Dateitypen werden übersprungen. Die KI verarbeitet unzuverlässige Patchtexte als Daten, nicht als Anweisungen. Die Antwort wird nicht ausgeführt. Posten des Kommentars benötigt GitHubs eingebauten GITHUB_TOKEN, kein separater GitHub-Zugang für die KI. Bei fehlenden Secrets, unbestätigtem Free-Status oder ungültigen Daten wird kein Modell abgefragt.

## Datenschutz und Qualität
Das öffentliche Repository bedeutet nicht, dass jedes Patch sicher für externe Inference ist: Der Filter ist nicht perfekt. Keine privaten Quelltexte, Zugangsdaten, persönlichen Logs, DEGIRO-Kontodaten oder Original-Screenshots in PRs einstellen. AI-Ausgaben können falsch sein; vor Änderungen eine unabhängige Codeprüfung und die normalen Tests verlangen.

**Tests:** python -m unittest test_ai_peer_review.py

**Stand bei Einreichung:** Vorbereitete Integration, lokale Tests erfolgreich; Cloudflare-Konto-Tarif konnte nicht per API gelesen werden (Berechtigung), daher keine Live-Inference durchgeführt, keine Aktivierung und keine Betriebsbehauptung.
