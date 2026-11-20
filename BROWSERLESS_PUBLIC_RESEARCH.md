# Browserless: freiwilliger öffentlicher Goldprodukt-Test

Diese Erweiterung ist keine Verbindung zu DEGIRO. Browserless nutzt ausschließlich
anonyme, öffentlich erreichbare Emittenten-/comdirect-Seiten. Keine Anmeldung,
keine PIN, keine Passwörter, keine Kontocookies, keine lokalen oder Cloud-Browserprofile,
keine automatische Tradeausführung, keine Order.

## Aktivierung

- Nur nach isolierter Code- und CI-Prüfung aktivieren: BOB_BROWSERLESS_PUBLIC_RESEARCH=1
  auf dem bestehenden Bob-Scanner-Dienst. Ohne den Wert ist alles gesperrt.
- Zusätzlich MUSS BOB_BROWSERLESS_FREE_ACCOUNT_CONFIRMED=1 gesetzt sein,
  nachdem der Kontoinhaber im Browserless-Dashboard Free/0 USD und das
  verbleibende Monatskontingent gesehen hat. Diese zweite Konfiguration ist
  eine manuelle Bestätigung, KEIN automatischer Beweis eines Free-Abos.
- Geschützte Bob-Statusanzeige: GET /api/browserless/public-status.
  Sie zeigt nur die beiden Freigaben und ob ein Schlüssel konfiguriert ist;
  der Schlüssel selbst und Browserless-Kontodaten werden niemals ausgegeben.
  Ohne alle Voraussetzungen bleibt der Button deaktiviert.
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
- Nach **zwei** unabhängigen, manuell ausgelösten SG-Praxisabrufen
  (20.11.2026, ca. 06:10 und 06:30 CH) meldete Browserless zwar HTTP 200 /
  ok=true, aber Bob konnte die angefragte Produktidentität nicht im
  zurückgelieferten Markdown bestätigen. Ohne die ursprünglichen
  Seiteninhalte ist offen, ob der SG-Seitenfilter Produktdaten entfernte
  oder Browserless z.B. eine unpassende Start-/Schutzseite zurücklieferte.
  Es gibt deshalb keine bestätigte Browserless-Datenextraktion.
- Der SG-Abruf verwendet nun onlyMainContent=false, um die öffentliche
  Produktüberschrift und ISIN/WKN-Stammdaten auch außerhalb des gefilterten
  Hauptinhalts zu bewahren; die erhöhte Antwortgrößengrenze von 512 KiB
  ist weiterhin strikt begrenzt. Für BNP/comdirect gilt weiterhin der
  Main-Content-Filter. Ein SG-Kontingent-Abruf wird dadurch **nicht**
  automatisch erneut ausgeführt.
- Bei einem erneuten Identitätsfehler erscheint lediglich ein
  geschlossener Diagnoseblock: Browserstrategie, grobe Textgrößenklasse,
  Boolesche ISIN/WKN/Produktmerkmale und mögliche Schutzseite.
  Keine Seiteninhalte, Token, Produktpreisfelder, Kontoangaben oder
  Rohlogs werden übertragen. Browserless-Erfolg wird ausdrücklich
  nicht mit verifizierter Goldproduktinformation gleichgesetzt.
- Prozesslokale Schranke: maximal 3 einzelne Versuche pro UTC-Tag und 12 pro
  UTC-Monat; nur ein Versuch je ISIN und Quelle im Prozess. Die Schranke
  wird bei Render-Neustart zurückgesetzt und ist keine dauerhafte Abrechnungssperre.
  Auch der frühere Browserless-Videotest teilt den Anbieterzähler.
  Verbindlicher Kostenschutz ist daher der verifizierte Free-Tarif.

## Technische Felder und Sicherheitsgrenzen

- Start mit genau einer vom Nutzer eingegebenen, prüfsummenvalidierten DE-ISIN;
  sg, comdirect und BNP Paribas sind feste Domain-/Pfadschablonen. Kein frei übergebbarer
  Weblink, kein DEGIRO-Host, keine Cookies oder Login-Profile.
- Die Smart-Scrape-Schnittstelle liefert Markdown und unverbindliche KI-Felder.
  Die öffentliche Quellseite muss HTTP 200 melden. Die KI-Ausgabe muss exakt
  die angefragte gültige vollständige ISIN enthalten. Der Seitentext muss
  entweder dieselbe vollständige ISIN zeigen oder (NUR bei SG) zusätzlich zu
  einer exakt passenden WKN-Überschrift im ersten Produktseitenabschnitt die
  typischen Stammdaten / Basiswert / Knock-Out-Felder enthalten. Im SG-WKN-Modus
  darf die KI die ISIN auslassen und muss die sichtbare WKN exakt auslesen;
  eine abweichende KI-ISIN sperrt immer. Die fehlende ISIN wird niemals
  vom Modell als Originalbeleg nacherfunden. Jede andere vollständige ISIN
  im reinen WKN-Fallback führt zur Ablehnung. Eine allgemeine Trefferliste,
  Seitenleiste oder bloße Erwähnung der WKN genügt nicht.
  Dieses Ergebnis trägt sourceIdentityEvidence und ggf.
  sourceIdentityLimited=true sowie sourceIsinObserved=false. Auch bei Übereinstimmung sind KI-Kurse
  ausdrücklich NICHT durch Originalquelle/Handelsplatz bestätigt.
  Mögliche Hinweise: Richtung, KO, Geld/Brief, Hebel,
  Status, Basiswert und auf der Seite angezeigte Kurs-/Hebelzeiten.
- Der Screenshot des ersten Praxisabrufs (20.11.2026, 06:10 CH)
  dokumentiert identity-not-proven für SG DE000FB0A490. Daraus folgt nur,
  dass die damalige Browserless-Markdown-Antwort keine exakte ISIN enthielt;
  die damalige Markdown-Rohantwort ist nicht gespeichert. Das ist kein
  Beweis einer falschen ISIN oder eines falschen SG-Produkts. Dieser
  Codepfad versucht keine automatischen kostenpflichtigen Wiederholungen.
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

- Bereits vorhandene SG-Originalbeobachtungen dürfen per
  browserless_public_compare nur gegen KI-Richtung und KO verglichen
  werden. Das startet keinen Emittentenabruf und erzeugt KEINE frische
  Kurszeit. Abweichungen erscheinen als solche; fehlende Referenzen
  bleiben ungeprüft. Der Vergleich ist kein Trading- oder Venue-Nachweis.

## Prüfung

Python-Unittests: test_browserless_public_research,
test_browserless_profile und test_browserless_trial.

Praktische Abnahme nach grüner CI: Free-Tarif und Kontingent im Browserless-Konto
prüfen, Secret auf Render verifizieren, Feature-Schalter explizit setzen,
einmal eine noch geeignete, nicht beendete Gold-ISIN an SG öffentlich auslesen und den Research-Status
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

Beispiel: DE000FG77FN1 hat nach bestätigter SG-Produktseite seinen letzten Handelstag am 19.11.2026 (Bewertung am 20.11.2026) und ist für eine neue fortlaufende Kursstudie ungeeignet. Die Liste muss vor einem Abruf auf tatsächliche aktuelle Laufzeit und Knock-out geprüft werden.

BNP-Paribas-Seiten nutzen die offizielle feste Form https://derivate.bnpparibas.com/product-details/DE000BY7UKR4/ (Beispiel-ISIN). Der vorhandene Validierungspfad verlangt die exakte ISIN sowohl im Seiten-Markdown als auch in der KI-Ausgabe. Unabhängiger Laufzeit-, Emittenten-, Handelsstatus- und Kurszeitnachweis bleibt notwendig. Ein leerer Vergleich mit SG ist bei BNP korrekt; er gibt keine Daten frei.
