# Getrennte Produktpools: DEGIRO und künftige Broker

Stand: 20. Oktober 2026

## Regel zur Aufnahme neuer Produkte

Eine neue Emittenten-ISIN ohne aktuellen **DEGIRO-Produktdetail-Nachweis** darf **nie** automatisch in die DEGIRO-bestätigte Auswahl oder die Gold-Knock-out-Top-3 aufgenommen werden.

1. **Broker-neutraler Recherchepool** (`Mehr → Zukunft → Emittenten-Recherche · zukünftige Broker`): Kandidaten aus bereits vorhandener historischer Emittentenrecherche sowie manuell vorgemerkte gültige ISINs. Produktidentität, Emittentenstatus und Basiswert können später einzeln über bereits erlaubte Emittentenquellen untersucht werden. DEGIRO, IBKR und IG sind jeweils *ungeprüft*, solange kein brokerspezifischer Nachweis vorliegt.
2. **DEGIRO-Nachweis-Pool** (`Produkte → Neue Produkte · DEGIRO-Nachweis erforderlich`): Nur Kandidaten mit einem **noch gültigen, aktuellen, ISIN- und Listenfassungs-gebundenen** `brokerVenueEvidence` aus Bobs privatem Prüfbericht. Der Nachweis muss zu einem zuvor hochgeladenen aktuellen DEGIRO-Screenshot passen, Originaldatum/-minute und Handelsplatz enthalten, in der Zürcher Zeitzone heute liegen und vor 22:00 Uhr noch gültig sein. Dieser Pool bestätigt nur die *Listungsbeobachtung*, **nicht** Geld-/Brief-Ausführbarkeit oder die Top-3-Handelsfreigabe.
3. **Bestehende aktive Gold-Knock-out-Auswahl**: Bleibt vollständig unverändert. Weder Emittenten-Recherche noch Kandidaten-Status schreiben direkt in `bobDegiroProductsV2`, Produkt-Rankings, MyTrade oder Simulationen. Ein Produkt erhält nur über die bereits vorhandene DEGIRO-Screenshot- und Nachweisprüfung Zugriff auf die bestehenden, strengen Freigabegates.

**Ein Issuer-Kurs, eine beliebige Behauptung `degiroListed:true`, ein Portfolio-CSV oder ein historischer DEGIRO-Bildschirm genügt nicht als aktueller DEGIRO-Listungsbeleg.** Auch ein bestätigter Broker-Screenshot ist keine echte Orderausführung oder gesicherter Ausführungskurs.

## Quelle der Kandidaten

- Der vorhandene lokale Bob-Importer übernimmt den öffentlichen, bereits recherchierten Emittenten-Katalog über `/api/degiro/candidates`. Das sind bisher **historische ISIN-Startkandidaten**, keine vollständige Neuemissions- oder DEGIRO-Live-Liste.
- Die Ansicht prüft den bestehenden privaten Produktbericht auf passende Brokerbeweise über `/api/degiro/audit`. Beide Endpunkte sind über Bobs vorhandene Anmeldung geschützt.
- Zusätzlich können gültige neue ISINs unter `Mehr → Zukunft` lokal in einer **eigenständigen Rechercheliste** vorgemerkt und wieder entfernt werden. Diese Liste wird nur auf dem Gerät gespeichert, nie mit Broker-Listung gleichgesetzt und weder an GitHub noch an DEGIRO übertragen.
- Bereits recherchierte Kandidaten werden im Browser bei offener App im Abstand von bis zu etwa zehn Minuten erneut abgefragt. Dies ist eine **Quellenstatusprüfung**, keine vollständige Entdeckung aller Neuemissionen. Eine künftige, freigegebene Emittenten-Neuemissionsschnittstelle kann neue Kandidaten nach denselben Regeln in diesen neutralen Pool liefern.

## Ein DEGIRO-Detailbild direkt in der Rechercheliste

Unter **Mehr → Zukunft → Emittenten-Recherche** kann ein Produkt mit „DEGIRO-Produktbild zuordnen“ oder ein bislang unbekanntes Produkt mit „Neues DEGIRO-Produktbild hochladen“ erfasst werden.

- Bob liest das Bild lokal auf Android mit der vorhandenen Screenshot-Erkennung. Eine **einzige eindeutige ISIN**, eine erkennbare DEGIRO-Kursdatentabelle, Börse, EUR-/CHF-Währung und der originale Kurs-Zeitpunkt sind zwingend. Bei einer vorgewählten ISIN muss das Bild exakt passen.
- Das Bild ist **nur am Tag seiner ursprünglichen Kurszeit bis 22:00 Uhr (Zürich)** als DEGIRO-Produktanzeige gültig. Wenn Quelle, ISIN, Börse, Währung oder Originalzeit unklar sind, bleibt der Kandidat ungeprüft. Eine bloße Emittentenquelle genügt nicht.
- **Datenschutz:** Screenshot und vollständiger OCR-Text werden NICHT übertragen. Nur begrenzte, aus dem Nutzerbild gelesene Produktbelegfelder, Dateityp/-größe und SHA-256-Fingerabdruck gehen über Bob-Anmeldung an den privaten Server. Dieser Beleg bestätigt eine Nutzerbild-Beobachtung, keine unabhängige DEGIRO-Live-Kontoabfrage und keine manipulationssichere Bildprüfung.
- Der neue Belegspeicher ist **von aktiven Gold-Hebelprodukten, Depot-CSV, Top 3, Risiko und Simulation** getrennt. Handelsfreigabe, Orderausführung und automatische Aufnahme in die aktive DEGIRO-Liste bleiben aus.
- Nach der Aufnahme wird die ISIN in die separat bestätigten neuen Produktkandidaten übernommen. Ohne gültigen Tagesbeleg bleibt sie in der brokerneutralen Recherche. Bobs vorhandene Emittentenrecherche wird einmalig für dieselbe ISIN zusätzlich angestoßen.
- Der private Server benötigt authentifizierte Same-Origin-Anfragen und prüft ISIN-Prüfziffer, eindeutigen Bildbezug, Handelsplatz, Originalzeit und Nachweiskonsistenz. Das Originalbild bleibt auf dem Handy, daher sind diese Metadaten **kein unabhängiger Echtheitsnachweis der Bilddatei**.

Der vollständige DEGIRO-Katalog ist weiterhin nicht zugänglich; ein einzelner neuer Screenshot ersetzt keine offizielle Broker-API.

## Vorbereitung weiterer Broker

Das bestehende `broker_bridge.py` bleibt für IBKR und IG als noch nicht verbundene API-Vertragsschicht bestehen. Jede ISIN erfordert später **pro Broker** einen eigenen Instrument-/Marktplatznachweis, Schweizer Handelbarkeit und Preis-/Kurszeit-Validierung. Die DEGIRO-Verfügbarkeit darf nicht auf IBKR/IG übertragen werden.

## Prüfungen

- `node test_broker_candidate_pools.js`: Gleichheit von ISIN, Liste und Nachweis; missbrauchbare Provider-Flags werden ignoriert, veraltete oder widersprüchliche Beweise abgelehnt; keine automatischen Handelsfreigaben.
- `browser_broker_candidate_pools.cjs`: Android-Darstellung, unverifizierte Emittentenprodukte, erfolgreiche aktuelle Screenshot-Zuordnung, Rückfall bei veraltetem Prüfbericht, separate lokal gespeicherte Broker-Rechercheliste und keine Fremdnetzwerk-Anfragen.
- Reguläre Bob-CI mit Python-, JavaScript- und Browser-Tests unverändert.

**Grenze:** Ohne aktuelle DEGIRO-Screenshotnachweise, von DEGIRO bereitgestellte offizielle Schnittstelle oder andere verifizierbare DEGIRO-Datenquelle ist keine vollautomatische neue DEGIRO-Listung möglich.

- Die zusätzlichen Regressionen test_broker_candidate_evidence.py, test_degiro_candidate_one_image.js und browser_degiro_candidate_image.cjs prüfen die isolierte Ein-Bild-Zuordnung, zeitlichen Nachweise, Datenschutz und Smartphone-Ablauf.
