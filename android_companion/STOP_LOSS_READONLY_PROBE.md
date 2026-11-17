# Bob Stop-Loss: DEGIRO-Oberfläche nur erkennen (Labor, nicht freigegeben)

## Zweck und Grenze

Diese Prüfung erweitert die bereits auf einem Samsung bestätigte 5/5-OFFLINE-Simulation.
Sie prüft **ausschließlich die sichtbar gerenderte Android-Oberfläche** der
offiziellen DEGIRO-App `nl.degiro.trader`. Es werden keine realen Orderfelder
angetippt, keine Texte eingefügt, keine Order geöffnet, bestätigt, gesendet oder
storniert. Die bekannte Stop-Loss-Eingabehilfe bleibt gesondert in Draft-PR #1790
und wird **nicht** durch diesen Test freigegeben.

## Eigene lokale Zustimmung

Nur ein Druck auf „DEGIRO-MASKE NUR LESEN · 45 Sekunden · KEINE ORDER“ in
der nicht exportierten Labor-App startet die Prüfung. Bob öffnet die DEGIRO-App,
aber navigiert darin nicht, entsperrt keine PIN-Maske und führt keine Trades aus.
Der Nutzer kann bei entsperrtem Telefon selbstständig eine Produktdetailseite
zeigen; eine reale Position ist für diese reine Sichtprüfung nicht nötig.
Der Lesedienst muss vorher freiwillig in Android aktiviert worden sein.

Der Prüflauf endet nach spätestens 45 Sekunden, bei Bildschirmsperre,
Dienstunterbrechung, einer geschützten Ansicht oder einem eindeutigen Ergebnis.
STOPP beendet ihn sofort. Parallel laufende Lese-, PIN- oder Brokeraktionen sind
eine Sperre, keine automatische Verlängerung.

## Datenschutz und Erkennungsnachweis

Die reine Erkennung gibt nur einen Code zurück:
NOT_DEGIRO, SCREEN_PROTECTED, VIEW_INCOMPLETE, AMBIGUOUS_ISIN,
PRODUCT_NOT_VISIBLE, PRODUCT_DETAIL_VISIBLE, SELL_FORM_VISIBLE,
SELL_FORM_LABELS_UNCLEAR oder BUY_OR_UNCONFIRMED_FORM.

Keine sichtbaren ISINs, Preise, Stückzahlen, Depotpositionen, Zugangsdaten,
Eingabewerte, Screenshots, Ordernummern oder vollständigen Android-Bäume werden
in die Ergebnisse übernommen, auf Platte gespeichert oder übertragen.
Ein in RAM temporär gelesenes Label dient nur zur sofortigen Prüfung des
Ansichtstyps und wird verworfen. Für Eingabefelder wird nicht einmal deren
aktueller Text gelesen. Die Service-Anbindung ruft ausschließlich
`StopLossReadOnlyProbe.inspect` auf, **niemals**
`StopLossPrefillExecutor.execute` oder Android-Eingabeaktionen.

## Tests und Veröffentlichung

- Kotlin Unit-Tests mit synthetischen Detail-, Verkaufs-, Kauf-, Login- und
  Mehrdeutigkeits-Ansichten
- Separater Android-Gerätetest für die Nur-Lesen-UI ohne Brokerkontakt
- Unveränderte bestehende Offline-Stop-Loss-Tests
- Labor-APK mit eigenständiger Android-App-Kennung, um keine installierte
  oder anders signierte Bob-Version zu überschreiben
- Keine Änderung am produktiven Hauptzweig und keine Veröffentlichung des
  echten Orderfeld-Automaten ohne gesonderte Abnahme

Die nächste reale Samsung-Prüfung darf nur den Ansichtstyp erkennen;
sie beweist ausdrücklich **keine** Bereitschaft zum automatischen
Eintragen oder Platzieren eines echten Stop-Loss.
