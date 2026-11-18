# DEGIRO-Nur-Lesen-Prüfung in der bestehenden signierten Bob-Handy-App

## Behebbarer Samsung-Fehler (18.11.2026)

Die sideloaded Debug-/Lab-APKs besitzen eine andere Android-Identität und
bekommen auf Samsung/Android 16 eigene, oft wegen „eingeschränkte Einstellung“
blockierte Bedienungshilfen. Eine bereits aktivierte Bedienungshilfe für
**Bob – Handy** gilt nicht für diese parallelen Labor-Apps. Die Lösung ist
keine Umgehung der Samsung-Sicherheitssperre.

Diese Änderung behält die **bestehende stabile Paketkennung**
`ch.bob.degirocompanion.stable` und den **bestehenden**
`ProductReadService` bei. Es wird keine neue Accessibility-Service-Komponente,
kein zweiter App-Identifier und keine zusätzliche Berechtigung angelegt.

## Bedienung

In einer **signierten** Bob-Handy-Version direkt auf der Startseite
„🔎 DEGIRO nur erkennen · 45 Sek. · keine Order“ drücken:

- Prüft exakt, ob **Bob – Handy / Produktseite einmal lesen** auf Android aktiviert
  **und** mit der App verbunden ist. Ohne Freigabe: eindeutige Anzeige mit
  „Lesedienst-Berechtigung prüfen / Android-Einstellungen“. Es gibt
  **keine** stillschweigende Aktivierung, kein ADB und keine PIN-Umgehung.
- Läuft kein anderer Bob-Lese-, PIN- oder Tradeauftrag, kann eine maximal
  45 Sekunden lange **passive** Beobachtung gestartet werden. Bob öffnet nur die
  offizielle DEGIRO-App; der Nutzer kann die sichtbaren Seiten selbst wechseln.
- Keine automatischen Klicks, Texteingaben, Navigation durch die Produktliste,
  Screenshots, Orders oder Tradebestätigung. Kein echtes Depot nötig.
- Nach Rückkehr zu Bob zeigt „Prüfergebnis anzeigen“ einen verständlichen
  Befund oder einen exakten Sperr-/Zeitlimitgrund.
- „Ergebnis bewusst an ChatGPT teilen“ nutzt die Android-Teilen-Funktion.
  Nur ein Code und ein kurzer Beschreibungstext werden übergeben. Der Nutzer
  wählt die Empfänger-App selbst; es gibt keine verdeckte ChatGPT-Öffnung.
- STOPP und die Samsung-Bildschirmsperre beenden die Prüfung.

## Grenze

Die 5/5-Offline-Simulation wurde auf Samsung bestätigt, beweist jedoch
**keine reale DEGIRO-Feldbedienung**. Dieser Nur-Lesen-Test dient allein dazu,
die tatsächliche Bildschirmstruktur zu erkennen. Die Draft-PRs für
automatisches Ausfüllen und echte Verkaufsmaske bleiben weiterhin gesperrt.
Eine gesonderte nachweisbare Abnahme wäre dafür erforderlich.

## Abnahme

- Kotlin-Unit-Tests der sicheren, nicht handelnden Ansichtserkennung.
- Statische Sicherheitsprüfung: keine anderen Accessibility-Dienste, keine
  Schreib-/Klickaktionen, keine Speicherung von Orderdaten.
- Android-Labor-Build/Emulator-UI-Tests.
- Nur nach vollständiger grüner CI und signiertem **stable** Release ein
  Update für die installierte Bob-Handy-App empfehlen.
