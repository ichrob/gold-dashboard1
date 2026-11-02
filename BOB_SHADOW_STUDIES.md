# Bob · drei unabhängige Vollbeleg-Simulationen

**Stand:** 03.11.2026. Nur Spielgeld, keine Order, keine Veränderung an Bobs Marktfreigaben.

## 1. Marktphasen-Vergleich (`regime-routing`)

Pro neuem, vollständig belegtem 15-Minuten-Analysezeitpunkt werden zwei Strategien
gleichzeitig eingefroren: bestehende bestätigte LONG-/SHORT-Richtung gegen eine
Marktphasen-Variante. Die neue Variante erlaubt eine Richtung nur bei beobachtetem
ADX >= 25 und einer nicht ungewöhnlich niedrigen ATR-Prozentklasse. Diese Schwellen
sind **Forschungs-Hypothesen**, keine neuen Live-Regeln. Beide erhalten denselben
originalen Spotpreis und eine 60-Minuten-Nachbeobachtung. Ohne Originalkurs im
geprüften Nachfenster bleibt der Fall `inconclusive`.

## 2. Abwarten gegen Einsteigen (`wait-vs-enter`)

Bei neutralem Hauptsignal und einer beobachteten 5-Minuten-DMI-Richtung erfasst
Bob einen rein **kontrafaktischen** LONG-/SHORT-Versuch gegenüber dem unverändert
gültigen Abwarten. Das tatsächlich angezeigte Hauptsignal bleibt neutral.
Die 60-Minuten-Bewegung verwendet ausschließlich einen späteren originalen
Spot-Zeitstempel. Es gibt keine Produkt-, Spread- oder Broker-Gewinnbestätigung;
0,16 % Rundwegkosten sind eine explizite Modellannahme.

## 3. Virtuelles Goldprodukt vollständig dokumentieren (`product-e2e`)

Eigenständiges 1.000-EUR-Spielgeldkonto:
- Nur bestätigte Goldpläne mit Stop/Ziel, passende EUR-Brief-/Geldkurse,
  eindeutige Produktidentität und gültige KO-Emittentennachweise.
- Maximal 65 % Exponierung und 650 EUR je Einstieg, ganze Stückzahlen, kein Kredit.
- Markt-/Kurszeit, Produktwahl, Preise, KO-Zustand, Stop/Ziel, alle Warte- und
  Fehlentscheidungen und virtuelle Kontobewegungen bleiben separat aufgezeichnet.
- Beispielkosten: 1 EUR je Seite und 0,05 % angenommene Slippage je Seite;
  tatsächlicher Spread wird über Geld-/Briefkurs berücksichtigt.
- Stopp/Ziel, Gegenrichtung und Zeitlimit **fordern** lediglich einen späteren
  virtuellen Ausstieg an. Ein Verkauf wird nur mit neuem beobachtetem Emittenten-
  Geldkurs, passendem Spotzeitpunkt und intakter KO-Prüfung verbucht.
- Bei KO-/Produktende ohne Abrechnungskurs bleibt das Kapital unbewertet und der
  Fall offen. Kein garantierter Stop und keine nachträgliche Ausführung.

## Volle Speicherung statt Verdichtung

`bob_shadow_study_control` verwahrt die isolierten Testkonten,
`bob_shadow_study_events` zeichnet **jeden** vom Paper-Worker übernommenen
Evaluationszyklus getrennt für alle drei Studien auf und
`bob_shadow_study_cases` verwahrt jede eingefrorene Hypothese samt datierter
Abschlussbeobachtung. Es erfolgt **keine automatische Löschung, zeitliche
Downsampling-Reduktion oder Verdichtung** dieser Studien.

Gemeinsame archivierte Goldkerzen werden gelesen, nicht mit erfundenen Kursen
aufgefüllt. Die Quellzeiten und das originale 15-Minuten-Analysefenster werden
mit jedem Ereignis verknüpft. Die drei Studien führen keinerlei eigene
Marktabfragen aus; ihre Fehler werden mit einem separaten SQL-Savepoint isoliert.
Der private authentifizierte `/simulation-status` liefert einen
`shadowStudies`-Status samt tatsächlicher Relationengröße in Byte.

## Speicher- und Betriebsvorbehalt

Auf einem festen 1-GB-Render-Volume kann eine **permanent wachsende**
vollständige Ereignishistorie auf Dauer die Kapazität erschöpfen. Der vorhandene
Speicherwächter muss deshalb fortlaufend beobachtet werden; es wird keine
kostenpflichtige Skalierung, Löschung oder externe Archivübertragung ausgelöst.
Vor einer späteren Speicherfreigabe sind unabhängiges verschlüsseltes Archiv,
Prüfsumme und geprüfte Wiederherstellung zwingend. Die Studien werden
ausschließlich im vorhandenen 08:00–22:00-Uhr-Zürich-Paper-Handelsfenster
fortgeführt und starten ohne rückdatierte Alt-Trades.
