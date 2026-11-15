# Bob: kostenlose Cloudflare-KI ohne dauerhaftes API-Token

## Kostenstatus
Am 09.11.2026 wurde am Cloudflare-Dashboard des Nutzers Workers Free als aktiv
bestätigt; dort stand keine gespeicherte Zahlungsmethode. Auf diesem Plan
ermöglicht Cloudflare Workers AI derzeit 10.000 Neurons pro Tag kostenlos;
darüber hinaus wird auf der Free-Stufe keine bezahlte Nutzung freigeschaltet.
**Bei späterer Tarifumstellung muss der Betreiber die Freigabe erneut prüfen.**

## Warum OIDC statt dauerhafter Geheimnisse?
Die GitHub-Schnittstelle in ChatGPT kann keine GitHub-Actions-Secrets schreiben.
Daher nutzt diese Integration eine eigene, isolierte Cloudflare Worker Function
mit einer Workers-AI-Bindung und **signiertem kurzlebigem GitHub-OIDC-Token**.
Kein Cloudflare-API-Token muss im Repository oder bei GitHub Secrets gespeichert
werden. Der Worker akzeptiert nur die vertraute Workflow-Identität auf main,
aus dem Repository ichrob/gold-dashboard1, mit fester Audience und RSA-signiertem
GitHub-OIDC-Token. Fremde und gefälschte Token werden abgelehnt.

## Ablauf
1. GitHub CI prüft einen PR.
2. Nur für erfolgreiche PR-CI-Läufe prüft ai_peer_review_free.py den PR:
   nur eigene interne PRs, nicht als Entwurf markiert, genau ein bekannter
   Reparaturfall, kein wiederholter Review derselben Commit-SHA und höchstens
   zwei Reviews pro PR und UTC-Tag.
3. Aus einem GitHub-Actions-OIDC-Kurzzeittoken wird ein sicherer Aufruf
   an https://bob-free-ai-review.robsimon.workers.dev/review erstellt.
4. Der Cloudflare Worker validiert Signatur und GitHub-Claims vollständig
   sowie die streng begrenzte, bereits gefilterte öffentliche Diff-Eingabe.
5. Workers AI / Qwen2.5-Coder-32B-Instruct gibt eine **unverbindliche** unabhängige
   Codeprüfung zurück. GitHub legt maximal einen neuen PR-Kommentar an.
6. Keine automatischen Merges, Orders, Strategie-/KO- oder Stop-Änderungen.
   Die bestehenden Reparaturwächter und unabhängigen Live-Beweise bleiben führend.

## Sicherheit
- Worker verarbeitet keine DEGIRO- oder persönlichen Kontodaten, keine Logs,
  Passwörter, API-Tokens, Screenshots oder vertraulichen Quelltexte.
- Keine öffentlichen offenen KI-Aufrufe: ohne gültiges GitHub-OIDC 401.
- Keine CORS-Freigabe, kein Schlüssel im Code, keine neue Render-RAM-Last.
- Fehler oder erschöpftes Freikontingent liefern einen Fehler, nie Paid-Fallback.
- Die KI darf keine privaten Systeme öffnen oder selbstständig Code deployen.
- AI-Ausgaben können falsch sein; CI und unabhängige Prüfung sind zusätzlich Pflicht.

## Sicherheits- und Abnahmetests
python -m unittest test_ai_peer_review_free.py
node test_bob_ai_free_worker.cjs

**Cloudflare-Deployment:** Ein neuer Worker mit Modulcode bob_ai_free_worker.mjs
und einem Workers-AI-Binding namens AI. Die bestehenden Cloudflare-Worker
bob-watchdog-clock und proud-gold-scanner-background-416f werden nicht verändert.

**Vorsicht:** API-Aufrufe an die Cloudflare AI laufen innerhalb der Free-Quote,
sind aber nicht kostenlos, falls später bewusst auf Workers Paid gewechselt wird
und das freie Kontingent überschritten wird. Die Kontoart muss bei
Tarifwechsel neu überprüft und dann gegebenenfalls der Worker deaktiviert werden.
