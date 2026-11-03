# Bob Handy: Bildaufbewahrung ohne Beweisverlust

## Grundregel

Bob behält **nicht** jedes Bild dauerhaft. Er trennt:
- **Aktuell gebraucht**: aktiver Goldlistenlauf, unverifizierte Originale, noch lesbare Werte,
  Preis-/KO-/Emittentenbelege, neueste gültige DEGIRO-Liste, aktive Restore-/Rollback-Beweise.
  Diese Bilder werden nicht automatisch gelöscht.
- **Ausgewertet und separat gespeichert**: eindeutige ISINs, Richtung, KO-/Basisangaben,
  Bezugsverhältnis, Quelle, Originalzeit, Prüfcode und alte/neue Datensatzidentität.
  Ein kompaktes Endresultat ersetzt aber den unverzichtbaren Originalnachweis nicht.
- **Abgelaufen und tatsächlich überflüssig**: mehr als 48 Stunden alte, nie erfolgreich
  geparste Zwischenaufnahmen, **nur** wenn eine spätere, vollständige zehnzeilige
  Liste **desselben gekoppelten Geräts und desselben Zürcher Kalendertags** vorliegt.
  Zusätzlich muss der Bildinhalt im neu bestätigten Stapel **bytegleich**
  vorhanden sein. Eine neue Tagesliste mit anderen Produkten oder Preisen
  ersetzt niemals den einzigartigen alten Beleg.
  Diese vom aktuellen Lesefluss nicht mehr verwendeten Fehlaufnahmen dürfen in
  höchstens acht Datensätzen pro Bereinigungslauf aus dem temporären
  Android-Listenpuffer entfernt werden.

## Sicherheitsgrenzen

Die automatische Bereinigung startet im vorhandenen OCR-Worker höchstens einmal
je zehn Minuten und läuft in kleinen kurzen Datenbanktransaktionen. Sie verlangt
vor dem Löschen gleichzeitig:
- `parsed_items IS NULL` – keine einzige bestätigte Zeile aus dieser Aufnahme,
- explizit fehlgeschlagene/wegen Speicher zurückgestellte Bilderkennung,
- Aufnahme mindestens 48 Stunden alt, keine jüngere laufende OCR-Lease,
- **spätere** `synced`-Tagesliste mit genau zehn geparsten Produktzeilen,
- gleicher kryptographisch gebundener Gerätebesitzer und gleicher Schweizer Tag,
- **exakte Gleichheit sämtlicher gespeicherter PNG-Base64-Inhalte in derselben Reihenfolge**
  mit der später erfolgreich bestätigten Liste, keine bloße ISIN-Übereinstimmung,
- keine gespeicherten privaten Bildreferenzen in dem zu löschenden Payload.

Fehlt ein einziger Nachweis, bleiben die Bilder erhalten. Insbesondere werden
**niemals** durch diese Routine `synced`-/`superseded`-Batches, Produktnachweise,
aktueller Tageslisten-Input, referenzierte Bildobjekte, neuere Fehlerbilder oder
unbestätigte Originale ohne sichere Ersatzliste gelöscht.

Die vorherige Löschung sämtlicher Bilder über 24 Stunden bei beliebigen
Android-API-Aufrufen ist abgeschaltet: Sie konnte auch noch benötigte,
bereits erfolgreich ausgewertete Originalbelege entfernen. Diese werden
später erst nach **batch-genauem verschlüsseltem Remote-Backup und unabhängig
bestandener Wiederherstellung**, mit rückgängig machbarem Zeigerpfad, freigegeben.
Der bisherige einzelne Test-Backupnachweis ist dafür **keine Pauschalfreigabe**.

Das Ergebnis der Bereinigung meldet nur entfernte Zeilen und ihre logische
Payload-Größe, **niemals** PNGs, Gerätekennungen, ISINs oder Anbieterpreise.
PostgreSQL-Löschungen können TOAST-/Tabellenseiten erst für interne Wiederverwendung
freigeben; freier physischer Render-Datenträger ist danach **separat zu messen**.
Kein `VACUUM FULL`, kein Tabellen-Rewrite und kein Upgrade/Kostenwechsel.

## Noch offen

1. Sichere lokale Bilderkennung auf dem Samsung (ML Kit statt großer
   Server-OCR-Modelle) mit unabhängigen Format-/ISIN-Prüfungen.
2. Automatische Verschlüsselung/Archivierung aller noch benötigten, vollständig
   belegten Originalbilder in das private Langzeitarchiv, mit echter
   Schlüssel-Wiederherstellbarkeit, unabhängigem Restore und späteren
   rückgängig machbaren Quellenreferenzen.
3. Pro-Bild-Prüfbeleg, letzter Nachweis je ISIN, Budget-/Reparaturprotokolle
   und physische Vorher/Nachher-Speichermessung vor einer erweiterten Freigabe.

**Keine Orderautomatik, keine neuen Berechtigungen, keine erzwungenen Tests,
keine Pauschallöschung.**
