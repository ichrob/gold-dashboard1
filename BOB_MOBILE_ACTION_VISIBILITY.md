# Bob – Handy: Gewählten Button sofort finden, ohne dauerhaftes Overlay

## Korrigierter und vom Nutzer präzisierter Wunsch · 25.10.2026

**Beim Öffnen über Bob – Handy** soll der ausgewählte, eindeutig erlaubte
Button **sofort im oberen sichtbaren Bildschirmbereich** erscheinen. Der Nutzer
soll niemals manuell nach ihm scrollen müssen – auch nicht nach einer späteren
Änderung von Bobs Design, der Kartenreihenfolge oder der Position des Buttons.

**Ausdrücklich nicht gewünscht:** Ein blauer Button, der beim normalen Scrollen
dauerhaft unten, oben oder über dem übrigen Seiteninhalt schwebt. Der Nutzer
hat einen solchen fixierten unteren Button auf seinem Samsung per Screenshot
als **falsche Umsetzung** zurückgemeldet.

## Implementierung (keine neue Android-Berechtigung)

- Bob – Handy übergibt weiterhin lediglich einen erlaubten HTTPS-Anzeigelink
  mit `?view=problems#problems` (optional `bobvisit`). Kein HTML-Senden,
  keine Fernsteuerung und **kein Klick auf die gesuchte Aktion**.
- Bobs mobile UI ordnet die ausdrücklich gewünschten Ansichten stabilen
  **semantischen Button-IDs** zu:
  `handyActionTargets = {problems: 'bobMobileHelpShare'}`.
  Ein späterer Umbau darf den Button und seine Karte verschieben; die ID und
  die zugrunde liegende freigegebene Aktion müssen bestehen bleiben.
- `stabilizeHandyActionEntry()` sucht den **Original-Button** per ID,
  öffnet nur dessen eigene gegebenenfalls zugeklappte Anzeige-Karte und
  richtet ihn beim Deep-Link-Einstieg **einmalig am sichtbaren oberen Rand**
  aus. Chrome-Scroll-Wiederherstellung wird in den ersten Frames kurz
  ausgeglichen; nach maximal ca. 850 ms oder bei der **ersten Nutzergeste**
  enden sämtliche Korrekturen.
- Anschließend bleibt der Button normal **im Dokumentfluss** und scrollt
  mit seiner Karte aus dem Bild. Es gibt **keine** feste, schwebende Leiste
  und keine doppelten oder überlagernden Hauptaktions-Buttons.
- Gewöhnliches Öffnen anderer Ansichten und eigenes Scrollen lösen
  **keinen** automatischen Aktionssprung aus. Neue auswählbare
  Bob-Handy-Aktionen müssen bewusst in die kleine, geprüfte Zuordnung
  aufgenommen werden und ihren stabilen Button besitzen.
- Die Originalfunktion öffnet weiterhin nur nach einem **echten Tipp**
  das Android-Teilen. ChatGPT erhält ohne Auswahl und Absenden **nichts**.
  Die Kopieralternative und alle Handels-/Authentifizierungsschutzregeln
  bleiben unverändert.

## Pflichtregeln für zukünftige Designänderungen

1. Der vom Bob-Handy-Link **gewählte** Button muss unmittelbar nach Öffnen
   sichtbar sein; auch wenn er in einen anderen Abschnitt derselben Ansicht,
   eine andere Karte oder ein zuvor geschlossenes Detail verschoben wurde.
2. Sobald der Nutzer selbst nach unten scrollt, bewegt sich die gesamte
   Seite natürlich; **kein fester blauer Button am unteren Bildschirmrand**.
3. Ein Scrollversuch, Tastendruck oder Tipp des Nutzers stoppt spätere
   automatische Scrollkorrekturen. Bei ungültiger, nicht freigegebener
   Aktion findet keine Navigation oder Ausführung statt.
4. Beim Öffnen ohne Bob-Handy-Auftrag wird **nicht** zwangsweise zu einem
   Button gesprungen. Bei einem wiederholten neuen erlaubten Link darf
   die gezielte Positionierung erneut stattfinden.
5. Regressionen: `node test_bob_handy_action_locator.js` und
   `node test_mobile_ki_zentrale.js` müssen bestanden sein.
   Nach größeren Designänderungen zusätzlich auf dem Samsung prüfen.
6. Keine Echtgeldorder, Stoppänderung, Zugriffsfreigabe oder Brokerbedienung
   darf durch diese **reine Anzeige-Navigation** ausgelöst werden.

Diese korrigierte Regel **ersetzt** die ältere Idee einer dauerhaft
feststehenden mobilen Hauptaktionsleiste.
