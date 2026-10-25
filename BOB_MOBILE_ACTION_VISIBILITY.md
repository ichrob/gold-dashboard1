# Bob Samsung: Hauptaktionen ohne Scrollen (dauerhafte Designregel)

## Verbindliche UX-Regel ab 25.10.2026

Die **wichtigste sichere Aktion** des aktuell geöffneten Bob-Bereichs
muss auf dem Samsung **ohne Scrollen** erreichbar sein. Ihr Standort darf
nicht von der Reihenfolge langer Karten, Tabellen, Statistiken oder
Hilfeabsätze abhängen. Auch bei einer späteren Änderung von Farben,
Navigation, Kartenlayout oder Texten bleibt die Hauptaktion unmittelbar
sichtbar. Lange Erklärungen werden aufklappbar dargestellt.

Dies gilt für neue primäre Handlungen, die der Nutzer ausdrücklich
auslösen soll, insbesondere **„Fehlerdiagnose an ChatGPT teilen · ohne Kopieren“**.
Es ist **nicht** die Anforderung, sämtliche sekundären Buttons gleichzeitig
auf einem kleinen Bildschirm anzuzeigen. Die mobile Aktionsleiste zeigt
höchstens **eine kontextbezogene Hauptaktion je Ansicht** und verdeckt weder
die untere Navigationsleiste noch den letzten Seiteninhalt.

## Technische Umsetzung

- Die mobile Hauptaktionsleiste mit der stabilen ID `bobPrimaryActionDock`
  ist ein eigenständiges, am sichtbaren Bildschirm befestigtes Element
  **außerhalb der umgestaltbaren Inhaltskarten**.
- Die explizit im Code registrierte Zuordnung
  `registerPinnedAction(view, buttonId, feedbackId)` hängt den **bereits
  existierenden Original-Button** samt Bedienhandler und Statusfeld um.
  Keine zweite Aktion, kein Duplikat, keine automatische Ausführung.
- `showPinnedAction(view)` wird bei **jedem** Bereichswechsel aufgerufen.
  Auf nicht dafür registrierten Ansichten verschwindet die Leiste.
  Zusätzliche Hauptaktionen lassen sich zentral aufnehmen; sie müssen
  eine semantisch stabile ID und einen nutzerbestätigten Handler besitzen.
- Die Leiste orientiert sich dynamisch an der Höhe der unteren Navigation.
  Die Seite erhält zusätzlichen Innenabstand, sodass der letzte Inhalt
  trotz feststehender Leiste erreichbar bleibt. `ResizeObserver` und
  Fenstergrößenänderungen passen die Position an.
- Diagnose-Teilen ruft weiterhin lediglich die nutzerinitiierte
  native Android-Teilen-Auswahl auf; der Bericht wird nicht automatisch
  gesendet. Kopier-Ersatzweg, STOPP- und andere Sicherheitsregeln bleiben.
- Brokerorders, Kauf/Verkauf, Stoppänderungen, Logins und Zugriffsfreigaben
  dürfen **nie** ohne gesondertes Sicherheitsdesign als Sofortaktion gepinnt
  oder ausgeführt werden.

## Definition of Done für **jede zukünftige Bob-Designänderung**

1. Beim Öffnen eines Bereichs auf 360px breitem Samsung-Viewport ist die
   registrierte Hauptaktion sofort sichtbar und mindestens 44px hoch.
2. Nach Scrollen bis zum Ende, wechselnden Kartenpositionen, Aufklappen
   langer Informationen, wiederholten Deep Links und Tabwechsel bleibt
   sie zuverlässig erreichbar; andere Bereiche zeigen keine falsche Aktion.
3. Die Navigationsleiste und Hauptaktion überdecken sich nicht; am Seitenende
   bleibt der Inhalt erreichbar. Änderungen an der Navigationshöhe werden
   berücksichtigt.
4. Kein automatischer Klick/Versand beim Öffnen; die echte Freigabe bleibt
   zwingend und ein abgebrochener Teilen-Dialog sendet nichts.
5. `node test_bob_primary_action_dock.js` und
   `node test_mobile_ki_zentrale.js` bleiben grün. Bei größerem Layoutumbau
   zusätzlich realen Android-Test durchführen; ein CI-Erfolg ersetzt den
   Samsung-Test nicht.

Die zuerst bestätigte Fehlerdiagnose-Übergabe bleibt Referenzfall. Neue
Ansichten erhalten eine Hauptaktion **nur**, wenn ihre erlaubte Funktion
eindeutig und sicher spezifiziert ist.
