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

## SG-Quellproblem · 20.11.2026, Diagnose 10:24 CH

Dritter einzelner, vom Nutzer gestarteter Browserless-Aufruf für
DE000FB0A490 auf öffentlicher SG-Seite:

- Browserless: strategy=browser, markdownSizeClass=long, sgFullContentRequested=true
- hasExactIsin=false, hasMatchingWknHeading=false,
  hasProductMarkers=false, hasOtherProductIsins=false
- possibleChallenge=false ist KEIN Beweis gegen andere Schutzseiten,
  Cookie-Barrieren oder eine regionale Abweichung.

HTTP 200 beweist nur einen erfolgreichen Browserless-Providerabruf.
Die gelieferte Seite ist nicht als SG-Produktseite nachgewiesen.
Die ursprüngliche Rohantwort wurde nicht gespeichert. Ursache offen.

Nächste begrenzte technische Schritte:

- Nur SG verwendet die offizielle Shared-Fleet-Region
  https://production-ams.browserless.io/smart-scrape statt SFO.
  Browserless dokumentiert Amsterdam, London und San Francisco.
  Regionalwahl ist eine Hypothese, kein nachgewiesener SG-Fix.
- Für SG werden ausschließlich markdown und rawText angefordert.
  Damit entfällt die frühere KI-JSON-Extraktionsgebühr für
  falsch geladene SG-Seiten. Browserzeit und ggf. Proxy kosten weiterhin
  Einheiten des kostenlosen 1.000er-Monatskontingents.
- SG-Feldhinweise werden aus klar beschrifteten Stammdaten-Zeilen
  konservativ ausgelesen. Bid/Ask und Originalkurszeiten werden NIE
  aus der vereinfachten SG-Seite erfunden.
- Neue anonyme Fehlerdiagnose zeigt, ob ISIN nur in HTML oder
  Rohtext statt in Markdown vorkommt, die Klasse des Seitentitels
  und eine strikt gefilterte Anbieter-Strategiefolge.
  HTML-Treffer allein sind NIE ein Identitäts- oder Handelsnachweis.
- Bobs bestehender SG-Direktimport bleibt unabhängig und vorrangig,
  keine automatische Zusatzabfrage anderer Provider.
- Kein Browserless-Autoretry; API nur durch Nutzerklick;
  immer researchOnly=true, eligible=false, tradeApproved=false,
  isDegiroQuote=false. Kein DEGIRO-Konto/PIN, keine Orders.


## Provider-Ablehnung nach EU-Regionalwechsel (20.11.2026)

Der fünfte sichtbare Versuch? Nein: Belegt sind drei SG-Anfragen mit
identity-not-proven sowie am 20.11. um 14:42 CH ein SG-Abruf mit
provider-unavailable. Die anschließende Anzeige already-attempted bedeutet,
dass Bob keine neue Browserless-Anfrage abgeschickt hat. Der konkrete
HTTP-Status des ursprünglichen AMS-Abrufs wurde von der alten Version
nicht gespeichert, so dass 400, 401, 403, 429 und 5xx NICHT rückwirkend
unterschieden werden können.

- Browserless-Dokumentation: AMS, LON und SFO sind Shared-Fleet-Adressen;
  403 kann u.a. auf einen falschen Regionalendpunkt oder Berechtigungen
  hinweisen. Das beweist NICHT die Ursache des konkreten AMS-Fehlers.
- VORSICHTIGE RÜCKKEHR: SG verwendet wieder production-sfo.browserless.io,
  weil SFO den gleichen API-Schlüssel zuvor mit HTTP 200 akzeptiert hatte.
  Die kostenärmere SG-Variante bleibt ohne KI-JSON, mit markdown und rawText
  sowie strengem Produktidentitätsnachweis erhalten.
- Provider-HTTP-Status (100–599) und neutrale Fehlerkategorie werden
  künftig ohne Body, URL oder API-Token zurückgegeben.
- Ein zweiter Klick mit derselben ISIN/Quelle im gleichen Serverprozess
  liefert, sofern vorhanden, den zuvor gespeicherten sicheren HTTP-Status
  zusammen mit already-attempted. Es erfolgt dabei KEIN weiterer
  Provideraufruf. Das ist ein Prozessspeicher, keine dauerhafte Rechnung
  oder globale Monats-Quota.
- Bei jeder Providerablehnung gilt weiterhin researchOnly=true,
  eligible=false, tradeApproved=false und fields={}.
- Weiterhin KEIN automatischer erneuter Abruf, kein kostenpflichtiger
  Plan, keine Anmeldung oder Bedienung des DEGIRO-Kontos.

Der Rückwechsel ist ein begründeter Reparaturversuch, nicht der Nachweis,
dass SG die korrekten Produktdaten liefert. Der bestehende direkte
SG-Emittentenimport bleibt für Bob primär.

## 20.11.2026: SG-Browserless ausgesetzt, SG-Direktquelle bevorzugt

Der Nutzer hat mehrere öffentliche SG-Browserless-Abrufe für dieselbe ISIN
DE000FB0A490 mit identity-not-proven beziehungsweise provider-unavailable
dokumentiert. Der jüngste Browserless-Report (15:44 CH) zeigt SFO / browser,
langes Markdown, aber weder vollständige ISIN noch WKN, Produktmerkmale oder
die ISIN in RawText bzw. RawHTML. Ursache der falschen/irrelevanten
Browserless-Seite ist ohne die ursprüngliche Rohseite nicht bestimmbar.

Dagegen bestätigt Bobs aktueller interner read-only-Produktstatus für
DE000FB0A490 (20.11., 15:45 CH) analysis-evidence-complete,
missing=[], Quelle "SG · datierter Chartkurs", Originalkurszeit
20.11. 15:45 CH. Die Direktquelle ist bereits für den gewünschten
Produktanalyse-Zweck verfügbar; sie ist ausdrücklich keine
DEGIRO-Handels- oder Kaufberechtigung.

Verbindliche Kosten-/Zuverlässigkeitsentscheidung:
- SG_BROWSERLESS_SUSPENDED=True als serverseitige Sperre (nach
  erfolgreichem Readiness-Check, vor Tokenverwendung und Quota-Reservierung).
  SG-Aufruf liefert direct-sg-preferred, researchOnly=true,
  eligible=false, tradeApproved=false, fields={} und providerCallStarted=false.
- SG bleibt als deaktivierte Auswahl im UI sichtbar und verweist auf Bobs
  Produkte-Ansicht und den vorhandenen direkten SG-Datenimport.
- BNP und comdirect bleiben nur als explizite, kostenbegrenzte,
  öffentliche Browserless-Recherche testbar; keinerlei automatische Abrufe.
- Eine Freigabe für SG-Browserless setzt eine separate technische
  Untersuchung mit verifiziertem echten SG-Produktnachweis und ein
  kontrolliertes neues Review voraus. Kein stilles Umgehen der Sperre durch
  Serverneustart oder wiederholten Klick.
- Unverändert: keine DEGIRO-PIN/Kontoautomatisierung, keine Echtgeldorders,
  keine automatische Übernahme in Quotes, Rankings oder Simulationen.

Bei vollständiger Produktanalyse gibt es aktuell keinen sachlichen Anlass,
weitere Browserless-Free-Einheiten an denselben fehlschlagenden SG-Abruf
zu verlieren.
