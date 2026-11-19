# Browserless: freiwilliger öffentlicher Goldprodukt-Test

Diese Erweiterung ist keine Verbindung zu DEGIRO. Browserless nutzt ausschließlich
anonyme, öffentlich erreichbare Emittenten-/comdirect-Seiten. Keine Anmeldung,
keine PIN, keine Passwörter, keine Kontocookies, keine lokalen oder Cloud-Browserprofile,
keine automatische Tradeausführung, keine Order.

## Aktivierung

- Nur nach isolierter Code- und CI-Prüfung aktivieren: BOB_BROWSERLESS_PUBLIC_RESEARCH=1
  auf dem bestehenden Bob-Scanner-Dienst. Ohne den Wert ist alles gesperrt.
- Der Schlüssel liegt ausschließlich als Server-Secret BROWSERLESS_API_TOKEN auf
  Render, nie in GitHub, Logs, mobilem Gerät oder Browser-JS.
  Die schon existierende Browserless-Video-Testfunktion verwendet denselben Namen;
  deren Kontingent ist ebenfalls zu berücksichtigen.
- Auf Browserless Free, ohne Kreditkarte, verbleiben. Der Anbieter weist
  1.000 Einheiten/Monat aus und verweigert weitere Aufrufe nach deren Verbrauch.
  Ein bezahlter Plan ist nicht freigegeben.
- Der neue Aufruf ist nur durch bewusstes Klicken auf
  "Browserless · öffentliche Produktrecherche" im angemeldeten Bob-Webbereich möglich.
  Keine selbsttätige Polling-Schleife, keine periodischen Abfragen.
- Smart Scrape verwendet ausdrücklich den günstigeren datacenter-Proxy als
  Fallback, aber die dokumentierte Eskalation kann trotzdem zusätzlich
  Browserzeit, KI-Extraktion und CAPTCHA-Einheiten kosten. Daher keine
  Zusicherung eines festen Einheitenpreises pro Einzelaufruf.
- Prozesslokale Schranke: maximal 3 einzelne Versuche pro UTC-Tag und 12 pro
  UTC-Monat; nur ein Versuch je ISIN und Quelle im Prozess. Die Schranke
  wird bei Render-Neustart zurückgesetzt und ist keine dauerhafte Abrechnungssperre.
  Auch der frühere Browserless-Videotest teilt den Anbieterzähler.
  Verbindlicher Kostenschutz ist daher der verifizierte Free-Tarif.

## Technische Felder und Sicherheitsgrenzen

- Start mit genau einer vom Nutzer eingegebenen, prüfsummenvalidierten DE-ISIN;
  sg und comdirect sind feste Domain-/Pfadschablonen. Kein frei übergebbarer
  Weblink, kein DEGIRO-Host, keine Cookies oder Login-Profile.
- Die Smart-Scrape-Schnittstelle liefert Markdown und unverbindliche KI-Felder.
  Die öffentliche Quellseite muss HTTP 200 melden. Die Identität muss sowohl
  im tatsächlichen Markdown als auch in der KI-Antwort exakt stimmen. Mögliche Hinweise: Richtung, KO, Geld/Brief, Hebel,
  Status, Basiswert und auf der Seite angezeigte Kurs-/Hebelzeiten.
- Antwortfelder bleiben reine Recherchekandidaten. Sie werden nicht
  in product_quotes, quote_updates, Handelsstatus, Produktfreigaben,
  KO-Schwellen, Simulationseinstiege oder Echtgeldaufträge übernommen.
  tradeApproved=false, eligible=false, isDegiroQuote=false,
  originalQuoteTimeVerified=false sind feste Rückgaberegeln. Die
  Rückgabe nennt die Browserless-Strategie zur manuellen Kostenprüfung; sie
  enthält keine Konto- oder Authentifizierungsinformationen.
- Kein erfundener Zeitstempel: checkedAt ist allein der Zeitpunkt der
  Browserless-Recherche, ausdrücklich nicht der Originalkurs.
- Statuscodes und Fehler sind datensparsam; Browserless-Token und Provider-Fehlertext
  werden nicht geloggt. Antwortgröße sowie Einzelsitzung sind beschränkt.
  Fehlschläge führen nie zu einem automatischen zweiten Anbieteraufruf.

## Prüfung

Python-Unittests: test_browserless_public_research,
test_browserless_profile und test_browserless_trial.

Praktische Abnahme nach grüner CI: Free-Tarif und Kontingent im Browserless-Konto
prüfen, Secret auf Render verifizieren, Feature-Schalter explizit setzen,
einmal DE000FG77FN1 an SG öffentlich auslesen und den Research-Status
mit dem ursprünglichen Emittentenbeleg vergleichen. Keine Originalbelege und
keine Marktfreigaben ersetzen. Danach erst über eine weitere, separat zu
testende Zuordnung von unabhängig verifizierten Daten zu Bob entscheiden.

## DEGIRO separat

DEGIRO verbietet automatisierte Drittanbieterwerkzeuge auf seiner Plattform:
https://www.degiro.de/helpdesk/handelsplattform/kann-ich-mit-degiro-trades-automatisieren-oder-trading-bots-verwenden

Deshalb ist keine Browserless-Anmeldung am persönlichen Depot und keine
Weitergabe der DEGIRO-PIN vorgesehen. Bob Handy und seine vorhandene
lokale Lesediagnostik bleiben als eigener Arbeitsstrang bestehen, ohne
Zugangsdaten an Browserless zu übertragen.
