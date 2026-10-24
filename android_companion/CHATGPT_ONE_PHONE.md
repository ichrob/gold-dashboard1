# ChatGPT → Bob – Handy auf **einem** Samsung (bewusste Übergabe)

## Ziel und Grenze

Diese Stufe braucht **kein zweites Gerät**. ChatGPT kann einen kurzen, fest
definierten **Anzeige-Auftrag** liefern. Der Benutzer kann ihn auf demselben
Samsung über „Kopieren“ oder Androids Teilen-Menü bewusst an **Bob – Handy**
übergeben. Bob zeigt zunächst eine Vorschau und öffnet **erst nach einem
zweiten ausdrücklichen Tastendruck** die fest eingestellte Bob-Webseite.

Das ist **noch keine direkte ChatGPT-Fernverbindung**, kein verschlüsselter
Hintergrundkanal, kein dauerhaftes Mithören und keine automatisierte Bedienung
anderer Apps. Diese lokale Übergabe ist vom separaten signierten
BOB-FERN/1-Kopplungskanal strikt getrennt.

## Nutzerschritte – Kopieren (zuverlässiger Ein-Handy-Weg)

1. In ChatGPT den einen zulässigen Auftrag **BOB-HANDY/1|OPEN_PRODUCTS**
   per Kopier-Schaltfläche kopieren.
2. Die Samsung-App mit dem exakten Namen **Bob – Handy** öffnen.
3. Oben **„📋 Kopierten ChatGPT-Auftrag prüfen“** tippen.
4. Die Vorschau unter **„CHATGPT → BOB – freigegebenen Anzeigeauftrag übernehmen“**
   lesen und **„✅ Geteilten Anzeigeauftrag einmalig öffnen“** tippen.
5. Die Bob-Webseite soll die Gold-Hebelprodukte anzeigen. Wenn App-Wechsel,
   Zeitüberschreitung (60 s), Abbrechen oder **„🛑 NOT-STOPP – alle Handy- und
   Fernaufträge sperren“** dazwischen liegen, wird nichts gestartet.

Alternative: Exakten einzelnen Auftrag über Android-Teilen an **Bob – Handy**
schicken; die gleiche Vorschau ist sichtbar. **Nicht den ganzen Chat teilen**,
denn lange oder zusammengesetzte Nachrichten werden vollständig abgewiesen.

## Technische Invarianten

- Die Clipboard-Eingabe wird **nur nach sichtbarem Tastendruck** und nur als
  Plain Text einmalig gelesen; niemals Hintergrundüberwachung, Speichern,
  Hochladen oder Auswertung von Bildern/Dateien.
- Erlaubt sind **nur** vorgegebene Anzeigen: Bob-Startseite, Goldprodukte,
  Goldmarkt, LONG-/Hebel-Erläuterung, Mein Trade (nur Anzeige), Simulationen,
  Lernen, Recherche. Keine Bildauswahl, Einstellungen, freie URLs oder
  mehrteilige Aufträge über diesen Übertragungsweg.
- ChatGPT/Android-Teilen ist **nicht authentifiziert**. Jede solche Mitteilung
  ist nur ein Vorschlag; auch mit bekanntem Text kann kein Dritter ohne
  Benutzer-Freigabe eine Aktion starten.
- **Jede Einzelaktion**: 60 Sekunden TTL, genau ein Mal, nur unveränderte
  Whitelist-Identität, STOPP/App-Wechsel widerruft. Kein automatischer zweiter
  Schritt. Keine Echtgeldorders, keine DEGIRO-Bedienung.
- Das lokale Ereignisprotokoll nutzt ausdrücklich **SHARE_*** für importierte
  ChatGPT-Shares statt **PAIRED/APPROVED** des kryptografischen Fernkanals;
  maximal 80 kurze Ereignisse, keine Nutzinhalte oder Geheimnisse.
- In AndroidManifest weiterhin kein **INTERNET**, Accessibility-Zugriff,
  fremder App-Zugriff, Bildschirmaufzeichnung oder selbstständige Orders.
- Native Kotlin- und Android-CI-Ergebnisse sind **kein Samsung-Gerätetest**.
  Die reale Android-Teilen-Zielauswahl und der tatsächliche Browserwechsel
  müssen erst auf dem eigenen Gerät bestätigt werden.

## Zweite Entwicklungsstufe (noch nicht implementiert)

Ein direkter ChatGPT-zu-Bob-Auftragskanal ohne Kopieren/Teilen bräuchte
eine separat authentifizierte, verschlüsselte Transportstrecke sowie einen
sicheren Android-Empfangskanal. Das kann nicht durch eine bloße ChatGPT-
Antwort oder frei aufrufbare Weblinks ersetzt werden und darf **niemals**
die lokale ausdrückliche Freigabe umgehen.
