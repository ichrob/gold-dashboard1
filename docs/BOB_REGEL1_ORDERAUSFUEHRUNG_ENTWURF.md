# Bob – Regel 1: Besitzerauftrag und reale Orderausführung (Entwurf)

**Vorgabe:** Bob soll den ausdrücklich gewollten Bedienauftrag möglichst vollständig erledigen. Reine Fehlklassifikationen ("PROTECTED_ORDER_CONFIRM" für eine Suche, globale Order-Schaltflächen auf einer Gold-Liste usw.) dürfen Gold-Suche, ISIN-Recherche, Produktlesen und Navigation nicht blockieren.

## Implementierter, aber NICHT ausgerollter erster Orderpfad
1. Der Besitzer kopiert einen frischen Bob-Entwurf `BOB-STOP/1` für **VERKAUF Stop Loss** einer bestehenden Position.
2. Die nicht exportierte lokale Bob-Handy-Ansicht bestätigt die gehaltene ISIN und Stückzahl. Bob darf die DEGIRO-Verkaufsmaske öffnen, Stop Loss auswählen und **Stopp (€)** sowie **Anzahl** schreiben.
3. Bob liest beide Felder exakt zurück. Ohne Erfolg gibt es **keine** Orderfreigabe.
4. Der Besitzer kehrt zu Bob Handy zurück, kontrolliert die Order und kreuzt eine **separate reale Transaktionsfreigabe** an. Ein zweiter Dialog zeigt ISIN, VERKAUF, Stückzahl und Stopp und fragt ausdrücklich nach einer echten Order.
5. Nur nach diesem lokalen Bestätigen öffnet Bob DEGIRO erneut und prüft ISIN, VERKAUF, Stop Loss und beide Felder nochmals. Er darf **ein einziges Mal** das exakte Bedienelement `Order platzieren` antippen.
6. Berechtigt eine DEGIRO-Seite danach eine zusätzliche `Order bestätigen`-Schaltfläche, bleibt sie zur manuellen Prüfung beim Besitzer. Bob behauptet **keinen Ausführungserfolg** ohne Broker-Quittung; der tatsächliche Orderstatus muss bei DEGIRO kontrolliert werden.

**Keine Dauerfreigabe:** Die Berechtigung gilt nur für diesen einen frischen, lokalen Entwurf, in RAM, maximal innerhalb der 120-Sekunden-Sitzung. Beim Klickversuch wird sie unwiderruflich verbraucht, auch bei Android-Fehlern. Kein Wiederholen, keine entfernte Freigabe über Server, Push, Chat oder Automation. Andere Ordertypen (Kauf, Market, Limit, Schließen ohne Stop) sind NICHT implementiert.

**Unverändert notwendige Prüfungen:** Geräteentsperrung/Anmeldung durch den Besitzer, eindeutige ISIN, tatsächliche aktuelle Broker-Maske, korrekter Stopp und Stückzahl, genau ein sichtbarer Absende-Button. Kein Eingriff bei PIN/TAN/Passwort, gesperrtem Samsung, mehreren ISINs, abweichenden Feldern, unklaren Orderansichten oder mehreren Klickzielen. Die im Projekt geführten Prüfungen 17 (`IDENTITY_CHANGED`) und 18 (`INVALID_QUOTES`) bleiben aktiv.

## Rollout-Grenze
**DRAFT: niemals ungeprüft auf dem echten DEGIRO-Konto ausprobieren.** Eine Android-Kompilierung, vollständige CI/Tests, CodeQL/Risiko-Prüfung, ein echter Samsung-UI-Durchlauf ohne Absenden und ein freigegebener kontrollierter Echtauftrag sind noch nachzuweisen. Besonders die tatsächliche Bedeutung von `Order platzieren` und eine mögliche zweite Bestätigungsstufe hängen von der installierten DEGIRO-Version ab.

Bis dahin bleibt der vorhandene veröffentlichte Bob-Handy-Leser unverändert. Die neue Stufe ist nur Quellcode in einem Entwurfs-Branch und **noch keine installierbare, freigegebene App**.
