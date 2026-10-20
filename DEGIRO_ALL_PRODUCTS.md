# DEGIRO: gemeinsame Produktübersicht und automatische Beobachtung

Stand: 20.10.2026

## Was genau angezeigt wird

Unter **Produkte → Alle DEGIRO-Produkte · Depot & Beobachtung** erscheinen alle verschiedenen, gültigen ISINs aus folgenden vorhandenen Datensätzen:

1. Der auf diesem Gerät gespeicherte DEGIRO-Portfolio-CSV-Export: **tatsächlich gehaltene Depotpositionen zum Exportzeitpunkt**, inklusive CSV-Schlusskurs und Menge.
2. Die auf diesem Gerät gespeicherte DEGIRO-Screenshotliste (`bobDegiroProductsV2`), unabhängig vom Depotbestand.
3. Der vom Bob-Hintergrunddienst gelieferte private Produktprüfbericht (`/api/degiro/audit`), mit einem eigenen Status (ok, teilweise, veraltet, nicht erreichbar).

Mehrfach vorkommende ISINs erscheinen **einmal**, mit mehreren Quellenhinweisen. Das Ganze ist eine Sammlung bisher beobachteter DEGIRO-ISINs, **nicht der vollständige Produktkatalog von DEGIRO**. Ohne valide Quellen kann Bob unbekannte Produkte nicht inventarisieren.

## Aktualisierung

- Die gemeinsame Oberfläche fragt alle ungefähr **30 Sekunden bei offener App** den vorhandenen geschützten Bob-Prüfbericht ab. Ein manueller Knopf startet dieselbe Statusprüfung.
- Die bestehende Gold-Hebelproduktrecherche nutzt ihre **bereits vorhandenen Emittenten- und Vergleichsquellen**, soweit diese technisch erreichbar und erlaubt sind. Deren Quellenzeiten bleiben unverändert. Die neue Übersicht liest nur Bobs bereits erfasste Daten; sie startet keine zusätzlichen Emittenten- oder Brokerabrufe.
- Aus dem Bob-Prüfbericht dürfen auch vorhandene, **datierte Geld-/Brief-Beobachtungen** als Vergleich angezeigt werden. Ein veralteter oder nur teilweise bestätigter Bericht erhält niemals eine aktuelle Kurskennzeichnung; originale Geld- und Briefzeiten sind beide erforderlich. Es bleiben Recherchebeobachtungen, keine ausführbaren DEGIRO-Quotes.
- Ein angezeigter Geld-/Briefwert erhält nur bei gültiger Originalzeit und höchstens 90 Sekunden Alter den Zustand `zeitnahe Vergleichsbeobachtung`; danach ist er veraltet. Es gibt **keinen** automatisch bestätigten DEGIRO-Ausführungskurs.
- Der CSV-Bestand wird **nicht automatisch aktualisiert**. Änderungen am tatsächlichen Depot (Kauf/Verkauf) erfordern weiterhin einen erneuten CSV-Export und Import.
- Bei geschlossenem Handy-Browser gibt es keinen durch diese UI initiierten 30-Sekunden-Abruf. Die vorhandenen serverseitigen Hintergrundjobs sind davon getrennt.

## Sicherheitsgrenzen

- Es gibt **keine offizielle DEGIRO-Konto-API**. DEGIRO weist außerdem darauf hin, dass Wrapper und andere externe Automatisierungen seiner Handelsplattform nicht unterstützt werden und gegen seine Nutzungsbedingungen verstoßen können.
- Deshalb **kein automatischer DEGIRO-Login, keine Kontodaten-Abfrage, keine Session-/2FA-Umgehung, keine Orders**.
- Die neue Übersicht verändert weder den Screenshot-/Produktdatenspeicher noch MyTrade, Knock-out-Schutz oder Top-3-Freigaben. Faktorprodukte sind sichtbar, aber für die Gold-Knock-out-Rangliste ausgeschlossen.
- Depot-CSV-Daten bleiben im lokalen Browser-Speicher. Die private Prüfberichtabfrage sendet **keine** Depotdaten an Bob oder GitHub.

DEGIRO-Quellen: https://www.degiro.ch/helpdesk/de/handelsplattform/bietet-degiro-eine-api und https://www.degiro.ch/helpdesk/de/handelsplattform/verwendung-der-handelsplattform/kann-ich-mit-degiro-automatisierte-trades-oder

## Tests

`node test_degiro_all_products.js` überprüft ISIN-Vereinigung, Dubletten, Quellzeitstempel und Handelsblockaden.

`browser_degiro_all_products.cjs` prüft mit künstlichen Testdaten die gemeinsame Anzeige, Mobile-Breite, Suchfilter, Speicherung, Löschung und den ausschließlichen Zugriff auf den vorhandenen Bob-Prüfbericht. Der CI-Lauf nutzt dafür Playwright.
