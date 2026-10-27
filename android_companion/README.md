## Einmalige DEGIRO-Leseprüfung (27.10.2026)

Neu: oben in Bob Handy **DEGIRO-Produktseite lesen**. Optionaler Android-Lesedienst,
standardmäßig ausgeschaltet. Android-Bedienungshilfe und deren Taste bewusst aktivieren.
DEGIRO selbst öffnen, anmelden und Produktseite auswählen. Tastendruck liest einmal;
zurück in Bob Handy zeigt den Entwurf, **Gelesene Werte in Bob prüfen** übergibt ihn
in die bestehende lokale Prüfansicht. Keine automatische Suche, Klicks, Gesten,
Ordermasken, Hintergrundabfragen oder Übertragung. STOPP sperrt den Leser und löscht
den Entwurf. App-Text und Bilder werden nicht gespeichert. Ein strukturierter Entwurf
bleibt höchstens fünf Minuten im Arbeitsspeicher. Erfassungszeit ist keine Kurszeit;
keine Handelsfreigabe. Fremde Apps, mehrere ISINs, sensible/editierbare Felder und
erkannte Login-/Orderseiten werden abgewiesen. DEGIRO-Beschränkungen für automatisierte
Werkzeuge bleiben relevant; Entwicklung ist keine Freigabe durch den Broker.

Geräteabnahme offen: Gibt DEGIRO die Produktfelder auf dem Samsung frei? Funktioniert
die Android-Bedienungshilfe-Taste? Verweigert Android/DEGIRO den Zugriff, bleibt
Screenshot-Teilen die Alternative; keine Umgehung. Eine neue signierte APK ist nötig.
Frühere Aussagen unten über fehlende Accessibility-Berechtigungen beschreiben alte Versionen.

---

## Automatische Bob-Handy-Updates nach Android-Codeänderungen

Nach **erfolgreicher Bob CI auf dem aktuellen GitHub-`main`** überprüft GitHub
selbstständig, ob es seit der letzten signierten Bob-Handy-Version tatsächlich
Änderungen an der Android-App gab. Nur dann wird die neue Version mit derselben
permanent hinterlegten Signatur gebaut und unter
[Releases → Latest](https://github.com/ichrob/gold-dashboard1/releases/latest)
veröffentlicht. Kein Termux-Start, kein neuer Signaturschlüssel und normalerweise
kein manueller GitHub-Workflow nötig. **Die Installation auf Samsung muss der
Besitzer weiterhin bewusst bestätigen.** Die Sicherheitsgrenzen und der
separate Debug-Testmodus bleiben unverändert.
Siehe [STABLE_RELEASE.md](STABLE_RELEASE.md).

---

## Neue dauerhafte Android-App (23.10.2026)

Die bisherige `Android-Labor`-/`Paralleltest`-/`Sprachtest`-Reihe wird durch die feste, privat signierte App **Bob – Handy** ersetzt. **Neue Debug-APKs aus GitHub sind keine dauerhaften Updates.** Der stabile Release wird erst möglich, sobald der Besitzer seinen privaten Signaturschlüssel einmalig auf einem eigenen Gerät angelegt und als GitHub Actions-Secrets verschlüsselt hinterlegt hat. Diese Schlüssel oder Passwörter nie im Chat oder im Repository teilen.

Die Anleitung für den gesamten einmaligen Einrichtungsschritt, die künftige Update-APK unter **Releases → Latest**, die unveränderte Sprache sowie die Geräte- und Datenübernahmegrenzen steht unter [STABLE_RELEASE.md](STABLE_RELEASE.md).

---

## Samsung-Sprachfehler „Bob zeige mir die Goldprodukte“ (23.10.2026)

**Auf dem echten Samsung beobachtet:** Die lokale Spracheingabe schrieb „Bob zeige mir die goldprodukte“, danach „Sprachauftrag unklar oder nicht erlaubt. Nichts ausgeführt.“. Das ist kein Netz-/Render-/Loginproblem: `PhoneTaskPlanParser` erkannte zwar „Bob“ ohne Komma, kannte aber das vollständige Satzmuster „zeige mir die goldprodukte“ noch nicht.

**Gezielte Änderung:** Der vollständige exakte Satz und wenige Schreibweisen („Gold-Produkte“, „Gold Hebelprodukte“) lösen nur `OPEN_PRODUCTS` aus. Keine freie Anweisungsausführung, keine Broker-, Finanz- oder Mehrschrittaktion. Kombinierte Anweisungen mit Kauf, Login oder Ordermaske bleiben vollständig gesperrt. Positive und negative Kotlin-Tests prüfen ausdrücklich den echten Gerätewortlaut.

**Für die derzeit installierte Paralleltest-App reicht ein Webdeploy nicht:** Der Satzparser arbeitet vollständig **lokal auf dem Handy**. Die gebaute Test-APK erhält deshalb die neue temporäre App-Kennung `ch.bob.degirocompanion.voicetest` und die Beschriftung **Bob: Android-Labor (Sprachtest)**. Diese Test-App kann getrennt von der bereits installierten Bob- und Paralleltest-App installiert werden, auch wenn GitHub den Debug-Signaturschlüssel pro Build wechselt. Keine bestehende App deinstallieren. Das ist ein Testbehelf, keine dauerhafte Update-Signaturstrategie.

**Nach bestandenem Android-Workflow:** Auf dessen GitHub-Actions-Seite unter `Artifacts` **bob-android-lab-voice-test** herunterladen, die ZIP mit Samsung Eigene Dateien entpacken, `app-debug.apk` öffnen und **Bob: Android-Labor (Sprachtest)** installieren. Mikrofontaste einmal drücken; „Bob zeige mir die Goldprodukte“ sagen. Erwartet: sichere Bob-Webseite öffnet Goldproduktliste (Scrollanfang nach separater Webkorrektur). Ein bestandener CI-Build ist kein Beleg für den echten Samsung-Gerätetest. Keine Echtgeldorders.

---

## Goldprodukte öffnen am Anfang statt beim letzten Produkt (23.10.2026)

Samsung-Gerätetest: Der gesprochene Einmalauftrag „Bob zeige meine Goldprodukte“ öffnet Bob korrekt, aber Chrome zeigte eine alte Scrollposition am Ende der Produktliste. Die alte Installation muss nicht entfernt werden.

**Web-Korrektur:** Nur beim expliziten `?view=products#products` (auch LONG-/Hebel-Frage) öffnet Bob weiterhin den bestehenden Goldprodukte-Bereich und richtet dessen Anfang nach dem Seitenaufbau erneut aus. Kleine, zeitlich begrenzte Korrekturen entschärfen Androids Scroll-Wiederherstellung. Jede eigene Berührung, Wischgeste, Mausrad- oder Tasteneingabe stoppt die Nachkorrektur sofort. Andere Seitenwechsel, Order-/Handelsregeln und Produktwerte bleiben unverändert. Nach erfolgreichem Server-Deploy kann die bereits installierte App diese Web-Korrektur testen.

**Android-Korrektur für wiederholtes Öffnen:** Künftige Begleiter-APKs ergänzen bei jeder expliziten Bob-Navigation einen kurzlebigen, nur lokalen `bobvisit`-Wert in der fest vorgegebenen Bob-URL. Dadurch öffnet ein erneuter Sprachauftrag nicht einfach einen vorhandenen Browser-Tab an der letzten Produktposition. Der Wert ist kein Passwort, Token oder Brokerauftrag. Die feste Positivliste bleibt unverändert. Für **diesen zusätzlichen Teil** ist eine neue APK erforderlich; wegen der GitHub-Debug-Signatur kann ein Update der Paralleltest-APK scheitern, daher die vorhandene Bob-Haupt-App niemals deinstallieren.

**Abnahme:** JavaScript-Regression zur ursprünglichen Bottom-Scrollposition und Abbruch bei Nutzerbewegung, Android-Unit-Test zum wechselnden `bobvisit`-Wert, gesamter Bob-/Android-CI. Auf echtem Samsung Sprachauftrag mehrmals starten, zur letzten Produktkarte scrollen und erneut sprechen: erwartet ist jedes Mal der Anfang des Bereichs „Gold-Hebelprodukte“. CI-Erfolg allein bestätigt keinen Gerätetest.

---

## Samsung: Installation ohne Löschen der bisherigen Bob-App (23.10.2026)

Falls `app-debug.apk` aus GitHub mit **„App nicht installiert“** abgewiesen wird, bitte **nicht** die bisherige Bob-App deinstallieren. Die vorherige Test-APK verwendet die Paketkennung `ch.bob.degirocompanion`. GitHub-Debug-APKs werden nicht garantiert mit demselben Schlüssel signiert wie bereits installierte Versionen. Android kann deshalb ein Überschreiben ablehnen; ein unbekannter Installationsfehler ist damit noch nicht abschließend diagnostiziert.

**Lösung als separater Versuch:** Der Debug-Build erhält nun ausdrücklich die Paketkennung `ch.bob.degirocompanion.parallel` und den sichtbaren Namen **Bob: Android-Labor (Paralleltest)**. Dadurch darf diese Test-App parallel zur bisherigen App bestehen, ohne deren gespeicherte Daten oder Signatur zu überschreiben. Andere Sicherheitsgrenzen bleiben: keine Netzwerk- oder Accessibility-Berechtigung, keine DEGIRO-Fremd-App-Steuerung, keine echten Orders.

**Installation auf Samsung:** In GitHub beim *neuen* erfolgreichen Android-Lauf unter **Artifacts** die ZIP `bob-android-lab-parallel-debug` laden, in „Eigene Dateien“ entpacken und daraus `app-debug.apk` öffnen. Gegebenenfalls die Installation für die gewählte Dateiverwaltung freigeben. **Die bisherige Bob-App nicht deinstallieren.** Danach die neue App **Bob: Android-Labor (Paralleltest)** öffnen, Mikrofonknopf einmal drücken und `Bob zeige meine Goldprodukte` sprechen. Nur die sichere Bob-Website darf geöffnet werden. Falls auch diese APK nicht installiert wird, benötigen wir die konkretere Android-Installationsursache (Sperre, Speicherplatz, beschädigter Download, Geräteverwaltung usw.).

**Langfristig:** GitHub erzeugt weiterhin möglicherweise unterschiedlich signierte Debug-APKs. Eine installierte Paralleltest-Version ist deshalb nicht garantiert durch künftige CI-Downloads aktualisierbar. Für saubere Updates eine beständige, privat gespeicherte Signatur und sichere CI-Secrets einrichten – niemals private Signaturschlüssel ins öffentliche Repository legen. Ein frischer Paralleltest enthält nicht automatisch lokale Daten der alten App. Ein erfolgreicher CI-Build beweist keine erfolgreiche Geräteinstallation.

---

## Bob Produkt- und Sprachantworten – Ursache für ABWARTEN sichtbar (22.10.2026)

Die Bob-Webseite unterscheidet in **ihrer bestehenden, rechnerischen Produktauswahl** ausdrücklich:
- **Marktdaten fehlen/veraltet/nicht belegt:** keine verlässliche *aktuelle* Auswahl; Datenwarnung hat Vorrang vor jeder scheinbar neutralen Richtung oder alten Rangliste
- **Aktuelle Marktdaten, ABWARTEN:** keine bestätigte LONG-/SHORT-Richtung
- **Aktuelle Richtung, keine erfasste Liste:** erst Produktliste prüfen
- **Aktuelle Richtung, aber keine hinreichenden Produktnachweise/Pflichtdaten:** Eignung kann nicht zuverlässig beurteilt werden
- **Aktuelle Richtung und hinreichend belegte Produkte, aber keines geeignet:** kein Kandidat erfüllt sämtliche vorhandenen Auswahlkriterien
- **Bestehende rechnerische Kandidaten:** vorhandene Zahl und Richtung mit Kurszeit-/Handelsnachweiswarnung

Die Ursache wird mit `data-selection-reason` im **bestehenden DOM der berechneten Rangfolge** markiert. Die Sprachansichten für LONG-Vergleich und Hebel lesen genau diese bereits vorhandene Statusmeldung und geben bei nicht aktuellen Daten keine vermeintlich bestätigte Produktauswahl aus. Es werden keine Marktöffnungszeiten aus Uhrzeit/Wochentag geraten, keine Handelsregeln gelockert und keine Order-Aktion ausgelöst. Der Broker-/Produktzustand bleibt unangetastet.

Abnahme: vollständige Node/Python-Bob-Suite inklusive `test_bob_selection_reasons.js` prüfen; auf Samsung nach Veröffentlichung der Render-Webversion die Sprachfrage bei fehlenden/veralteten Marktdaten und später bei vollständiger Datenlage vergleichen. Keine neue Android-APK erforderlich.

## Bob Android 0.12.1 – Samsung versteht „Bob zeige meine Goldprodukte“ (ohne Komma)

Im Samsung-Echttest wurde die Äußerung **„Bob zeige meine goldprodukte“** korrekt in Text umgewandelt, aber als `Sprachauftrag unklar oder nicht erlaubt` zurückgewiesen. Ursache: Der lokale Parser akzeptierte `Bob, zeige ...` mit Komma, aber nicht `Bob zeige ...` ohne Komma. Bei Google/Samsung-Diktat wird Interpunktion häufig nicht mitgeliefert.

**Korrektur:** Die bekannte Anrede `Bob`, `Hallo Bob` oder `Hey Bob` kann am Satzanfang auch mit Leerzeichen statt Komma stehen. Danach muss der **gesamte** Rest weiterhin exakt einer erlaubten Tätigkeit entsprechen. `Bob öffnen` und `Bob starten` bleiben eigenständige Befehle. Nie Teilbefehle ausführen, niemals Käufer-/Verkäuferaktionen, Orderformulare oder Android-Drittsystemautomatisierung durchlassen.

**Regression:** Testet den echten Samsung-Wortlaut, Groß-/Kleinschreibung, Interpunktion, `Gold Hebelprodukte`, LONG-Fragen, legacy `Bob öffnen`, gefährliche gemischte Sätze und den Ausschluss der automatischen Ausführung von Mehrschrittplänen.

**Handy-Abnahme nach neuer Installation:** Bob Android-Labor öffnen → einmal Mikrofon tippen → `Bob, zeige meine Goldprodukte` sagen (oder nur `Bob zeige meine Goldprodukte`). Erwartet wird die automatische Öffnung des Produktmenüs ohne weitere Knöpfe; Bob hört nicht dauerhaft mit. Test auf echtem Gerät ist zusätzlich zum grünen Android-Build nötig.

## Bob Android 0.12 – Mikrofon aktivieren, sichere Bob-Seite öffnet von selbst

**Auslöser:** Der Nutzer drückt **einmal** den Mikrofonknopf `🎤 Bob zuhören lassen – einmal tippen` innerhalb der Samsung-App. Androids ausgewählter Spracherkennungsdienst liefert eine einzelne Äußerung zurück. Es gibt **kein permanentes Zuhören**, keine App-Mikrofon-Aufnahmeberechtigung, keinen Always-on-Dienst. Der Android-Spracherkennungsanbieter kann online verarbeiten.

**Automatik (nur bestätigte lokale Positivliste):** Genau **eine** vollständig erkannte, harmlose Bob-Anzeigenavigation (`OPEN_BOB`, `OPEN_MARKET`, `OPEN_PRODUCTS`, `OPEN_LONG_REVIEW`, `OPEN_LEVERAGE_REVIEW`, `OPEN_TRADE`, `OPEN_SIMULATION`, `OPEN_LEARNING`, `OPEN_RESEARCH`) wird ohne zweiten Knopf gestartet. Bob/Browser authentifizieren unverändert selbst. Weder eine unklare Äußerung noch irgendeine fremde App, Brokeroberfläche, Order, Datei-Auswahl, Android-Einstellung oder ein zusammengesetzter Mehrschritt-Auftrag wird automatisch ausgeführt. Bei Mehrschritt-Aufträgen bleiben Prüfung und Einzelausführung erforderlich. Der Tastatur-Mikrofon-Ersatzweg bleibt absichtlich manuell, da das Textfeld beliebig veränderbar ist. Strenge Server-Login-Whitelist inklusive `products-leverage`.

**Kontext & Antworten:** Nur die zuletzt erfolgreich geöffnete Bob-Seite im flüchtigen Speicher, maximal zwei Minuten. Nach einer LONG- oder Hebelerklärung kann `Warum?` oder `Wieso?` die vorhandene Erklärungsseite erneut öffnen. Die Frage `Welches hat den besten Hebel?` öffnet `/?view=products-leverage#products-leverage`. Dort werden ausschließlich **bereits gerenderte** Werte aus Bobs `data-risk-leverage`-Anzeige vorgelesen oder als Text dargestellt; bei ABWARTEN, unbekannten oder fehlenden Ergebnissen werden keine Hebel erfunden und es gibt keine Handelsfreigabe. Mit der **„🔊 Ergebnis vorlesen“**-Schaltfläche kann die Browser-Sprachausgabe **nach** einer Nutzerberührung starten (falls Browser-Unterstützung und Stimmen verfügbar sind).

**Grenze:** Dies ist ein sicherer, befehlsorientierter Dialog mit wenigen unterstützten Folgefragen, noch **kein** allgemeiner KI-Chat mit Zugriff auf Bobs privater Produkt-API. Eine solche Architektur braucht gesonderte Authentifizierungs-, Datenzugriffs- und Datenschutzprüfung. Eine vollintegrierte Bob-Android-App statt des Begleiter-Labors ist ein separates Entwicklungsziel.

**Samsung-Funktionsprobe:** Upgrade über die vorhandene App nur bei gleicher Signatur; Mikrofon tippen, „Zeige Goldprodukte“ sagen – direktes Öffnen ohne zweiten Knopf; erneut Mikrofon tippen, „Welches hat den besten Hebel?“ sagen – Info nur aus vorhandenem Bob-Ranking; „Warum?“ innerhalb 120 s – dieselbe Erklärungsansicht; „Öffne die Einstellungen“ oder „Zeige Goldprodukte und danach Simulationen“ – **nicht** automatisch ausführen. Android-Build und Sicherheitstest sind nicht mit einem bestätigten Samsung-Funktionstest gleichzusetzen.

## Bob Android 0.11 – ein Tipp nach einfachem Sprachauftrag + Fragen zu LONG-Produkten

**Handybedienung:** Nach `🎤 Auftrag sprechen` erkennt Bob weiterhin nur streng erlaubte Navigations-/Bildauswahl-Aufträge. Wenn genau ein bekannter, ungefährlicher Auftrag erkannt wurde, wird dieser **nach der Spracherkennung auf dem Gerät für maximal 60 Sekunden einmalig vorbereitet**. Ein deutlich beschrifteter Button **„Erkannten Sprachauftrag einmalig ausführen“** steht unmittelbar unter der Auftragsvorschau. Dieser **eine** Tipp startet die Aktion; die Spracherkennung selbst startet nichts. Bei Texteingabe-Änderung, STOPP, Ablauf, App-Wechsel oder Ausführung erlischt die Freigabe. Mehrere gesprochene Aufgaben benötigen für die jeweiligen weiteren Schritte weiterhin eine neue Prüfung und Einzelausführung. Keine Echtgeldorders, keine DEGIRO-Automatisierung.

**Produktfragen:** Gesprochene Formulierungen wie `Zeige mir die drei besten LONG-Produkte und erkläre die Unterschiede` führen ausschließlich zur **read-only** Bob-Produktauswertung unter `/?view=products-long#products-long`. Der Login bewahrt nur diesen festen UI-Schlüssel. Die Bob-Weboberfläche öffnet die existierende Produktsektion und erzeugt eine Erklärung *ausschließlich aus der bereits aktuell angezeigten Rechner-Rangfolge im DOM*. Sie zeigt niemals drei LONG-Kandidaten an, wenn nur SHORT/ABWARTEN vorliegt oder Originalwerte fehlen. Angaben zu KO-Abstand, Pufferscore und Datenhinweisen werden lediglich aus den vorhandenen Ergebnissen übernommen. Es gibt keine zusätzliche Bewertung, keine aktuellen Brokerkurs-Behauptungen, keine Handelsfreigaben und keine automatische Änderung des Rankings.

**Negativtests:** Mischsätze mit Kauf-/Verkaufs-/Stop-Änderung werden vollständig abgewiesen. Keine freie KI-Konto-/Orderbedienung, keine Internet-/Accessibility-Freigabe für den Android-Begleiter. Browser- und Unit-Tests ersetzen den echten Samsung-Funktionstest nicht.

**Benötigte Prüfung:** CI Android-APK mit vorhandenen Berechtigungs-Audit, vollständig grüne Bob CI, exakte Login-Whitelist, danach Gerätetest auf Samsung mit einfachem Goldprodukte-Sprachauftrag und LONG-Frage. Eine neue Android-APK ist für die Sprachänderung erforderlich.

## Android 0.10.3 – Google-Sprachdialog auf Samsung nicht verfügbar (22.10.2026)

Beim echten Samsung-Test erscheint über Bobs `🎤 Auftrag sprechen` der Google-Dialog **„Die Sprachsuche ist nicht verfügbar“**, während die Google-App selbst `Bereit...` anzeigt. Dies beweist weder einen Defekt des Mikrofons noch, dass die externe Android-`ACTION_RECOGNIZE_SPEECH`-Schnittstelle verfügbar ist.

**Korrektur:** Die bisherige erzwungene Offline-Präferenz `EXTRA_PREFER_OFFLINE=true` entfällt. Die Sprache wird konkret als `de-DE` angefordert; der Samsung-/Google-Sprachdienst kann dafür das Netzwerk nutzen. Das ist bewusst im bestehenden Companion kenntlich gemacht.

**Alternativer Weg:** Neuer sichtbarer Knopf **„Über Tastatur-Mikrofon sprechen (Alternative)“** fokussiert ausschließlich das vorhandene lokale Auftragsfeld. Nutzer tippt das Mikrofon auf seiner Samsung-/Google-Tastatur (falls vorhanden), diktiert z. B. `Zeige meine Goldprodukte und danach die Simulationen` und wählt danach **Handy-Auftrag prüfen**. Erst wenn *alle Satzteile* auf der bisherigen strikten Positivliste stehen, wird Schritt 1 mit klarer Gesamtplan-Vorschau freigegeben. Alle Schritte benötigen explizite Einzelausführung, STOPP verwirft Rest. Bei Fehlern, unklarer Sprache, Kauf-/Verkaufsbefehlen oder Fremd-Apps keinerlei Teilaktion.

**Nicht behaupten:** Erfolgreicher Gradle-Build bedeutet nicht, dass Google-Spracherkennung auf Samsung funktioniert. Die alternative Tastatur-Diktierfunktion hängt vom tatsächlich aktivierten Tastatur-Sprachdienst ab. Kein zusätzlicher App-Mikrofon-, Netzwerk- oder Bedienungshilfe-Zugriff, keine Broker-Steuerung.

**Samsung-Abnahme:** Upgrade ohne ungewollten Signaturwechsel; Bob-Sprachknopf testen; falls Google weiterhin „nicht verfügbar“ meldet, Zurück, „Über Tastatur-Mikrofon sprechen“, Tastatur-Mikrofon benutzen und Textvorschau + Einmalbestätigung kontrollieren. Auch verbotenen Mischsatz ausprobieren: er muss komplett gesperrt bleiben.

## Android 0.10.1 – Goldprodukte nach Anmeldung tatsächlich öffnen

Bei einem Samsung-Echttest war die Schaltfläche `Goldprodukte direkt öffnen` sichtbar und die Bob-Anmeldung erfolgreich, aber nach der Anmeldung wurde nur `Übersicht` angezeigt. Der Browser-Link nutzte nur `/#products`, dessen Fragment bei der Passwort-Weiterleitung nicht zuverlässig erhalten blieb.

Der Companion öffnet deshalb ausschließlich eine **feste, erlaubte** Bob-URL mit beiden Markern: `/?view=products#products`. Der Server akzeptiert aus `view` nur `overview`, `products`, `trade`, `simulation`, `learning`, `research` und bewahrt diese Auswahl über `/login?view=...` und das geschützte Login-Formular auf. Nach erfolgreicher Anmeldung wird nur auf `/?view=<fest-geprüfter-wert>#<fest-geprüfter-wert>` weitergeleitet. Das vorhandene OAuth-Resume hat Vorrang. Unbekannte Werte, fremde Domains und andere Ziele werden nie als Redirect akzeptiert; Passwort/CSRF-Prüfungen bleiben unverändert. Der ursprüngliche Android-Link muss die neue Query-Form enthalten – deshalb ist ein **neuer APK-Build** erforderlich; ein Server-Update allein kann Android-Links mit verlorenem Fragment nicht zurückgewinnen.

**Abnahme:** Gradle/Android Build, Python Login-Rückkehr-Regression, vollständige Bob CI und danach Samsung-Test mit abgelaufener Sitzung: `Goldprodukte direkt öffnen`, Passwort manuell eingeben, tatsächlich Goldprodukte sehen. Noch keine Aussage über erfolgreichen Gerätetest oder Render-Deployment aus einem grünen CI-Build ableiten.

## 0.10 – Geräte-Diagnose ausdrücklich an ChatGPT teilen (Testfassung)

In der bestehenden Android-Labor-App erscheint der Knopf **„🔎 Diagnose an ChatGPT teilen“**. Der Bericht enthält ausschließlich die App-Version, grobe Ergebniskennungen für den zuletzt gestarteten Handy-Auftrag, Spracherkennung und OCR-Bildserie, eine begrenzte Bildanzahl und noch offene Bestätigungsschritte. **Keine** Sprachnachricht, Abschrift, OCR-Inhalte, ISIN, Kurse, Bilder, Login-, Kontodaten oder Orderinformationen. Alles bleibt bis zu einem bewussten Tippen lokal; Android zeigt danach einen Empfänger-Auswahldialog. Erst durch Auswahl der ChatGPT-App und manuelles Senden wird der Text weitergegeben. Das ist **kein permanenter Fernzugriff, keine automatische Fehlerübertragung und keine Bestätigung, dass der Browser erfolgreich geladen hat.**

Diese Android-Änderung ist erst nach Installation einer **neuen APK** auf dem Samsung verfügbar. Die bisherige App wird nicht durch die Web-Server-Veröffentlichung aktualisiert. Version, statische Berechtigungsgrenzen und sichere Statuskennungen werden über die Android CI geprüft; die Funktion muss auf einem realen Samsung zusätzlich von Hand getestet werden.

## 0.9 (Test): deutlich weniger Tippen, natürliche Einzelaufträge

Die vier beschrifteten Schnellzugriffe **Bob direkt öffnen**, **Goldprodukte direkt öffnen**, **Mein Trade direkt öffnen** und **Simulationen direkt öffnen** öffnen ausschließlich eine feste Bob-Seite nach einem einzigen bewussten Tastendruck. Eine erfolgreiche Anzeige der Zielseite wird dadurch **nicht** bestätigt; bei Bedarf die bestehende Bob-Anmeldung im Browser durchführen. Es gibt keine verdeckten Folgeaktionen und keinen Zugriff auf andere Apps.

Im Textfeld kann man jetzt neben der bestehenden strengen `BOB-AUFTRAG: ...`-Syntax auch einfache, frei **formulierte, aber auf die Positivliste beschränkte Einzelphrasen** (z. B. `Zeige mir meine Goldprodukte`) eingeben. Ein mehrteiliger freier Text kann **nicht** über den Einzelaktionsknopf freigegeben werden; Sprachpläne werden als begrenzte Schrittfolge vorbereitet und benötigen vor jedem Schritt eine eigene Prüfung. Unbekannte und finanzielle Befehle bleiben gesperrt. Zusätzliche Unit-Tests decken diesen Schutz ab.

**Noch ausstehend:** CI für den letzten Commit; danach Samsung-Echttest samt Signaturprüfung. Diese Version führt keine echte Marktanalyse aus; sie zeigt nur Bobs schon vorhandene Übersicht. Keine automatische Broker-/DEGIRO-Bedienung.

## Ausbau 22.10.2026 – Sprachdialog, Bob-Navigation und begrenzter Kontext (0.8, vor Samsung-Gerätetest)

Die bestehende Android-App unterstützt zusätzlich zu lokalen harmless Aktionen **read-only** Navigation
zu **Goldmarkt-Übersicht, Goldprodukten, Mein Trade, Simulation, Lernen und Recherche**. Die
Ziele stammen aus einer fest codierten Allowlist und öffnen ausschließlich die vorhandene
Bob-Webseite im Browser; Bob selbst verlangt seine normale Anmeldung. Eine Marktanalyse wird
**nur angezeigt/angesteuert**, nicht vom Android-Begleiter autonom gestartet oder als
aktuelle Preisprüfung behauptet. Die App bedient weder DEGIRO noch andere Broker-Apps.

Sprachfolgen wie „Zeige meine Goldprodukte und danach die Simulationen“ werden bis zu drei
erlaubten Schritten verarbeitet. Jeder Schritt muss erneut auf dem Gerät geprüft und einmalig
freigegeben werden. „Und jetzt die Recherche“ kann als eigenständiger Anschlussbefehl
verstanden werden. „Nochmal“ wiederholt nur den letzten **tatsächlich angestoßenen**,
zulässigen Schritt, nur innerhalb von 120 Sekunden und stets nach neuer Prüfung.
Weder Kontext noch Anmeldedaten, Audio oder Screenshots werden für Sprache persistiert.

Ein zusätzlicher **„🔊 Bobs Rückmeldung vorlesen“**-Button gibt nur lokale
Auftrags-/Fehlermeldungen über die auf dem Gerät vorhandene Text-zu-Sprache-Engine aus.
Sprachdienst und Sprachausgabe können je nach Samsung-/Android-Anbieter Onlinedienste nutzen.
Keine stets aktive Mikrofonüberwachung, keine ungeprüfte KI, kein Remote-Pairing,
keine Änderung von Handelsregeln und keine Echtgeldorders.

Bis die Android- und Bob-CI sowie der echte Samsung-Test erfolgreich sind, bleibt 0.8 eine
**Testfassung auf einem Entwicklungszweig**. Der Nutzer muss die APK manuell installieren;
eventuelle Signaturkonflikte zuerst untersuchen, nicht blind deinstallieren.

## Erweiterung 22.10.2026: zusammenhängende deutsche Sprachaufträge (Entwicklungsstand)

Die bestehende Offline-Android-App kann jetzt **bis zu drei eindeutig erlaubte, unterschiedliche Schritte**
in **einem gesprochenen Satz** erkennen, z. B. „Bob, öffne zuerst Bob und danach
wähle meine Produktbilder aus“. Sie zeigt die gesamte erkannte Schrittfolge an.
**Vor jedem einzelnen Schritt** sind ausdrücklich „Handy-Auftrag prüfen“ und
„Geprüften Handy-Auftrag einmalig ausführen“ nötig. Der nächste Schritt wird
nur vorausgewählt und niemals selbst gestartet. Jede Freigabe ist einmalig
und maximal 60 Sekunden gültig; App-Wechsel widerruft eine offene Freigabe.
„STOPP“ verwirft alle noch offenen Schritte (kein Rückgängigmachen bereits
geöffneter Apps).

Die vollständige Äußerung wird abgelehnt, falls **irgendein** Teil unbekannt,
handelsbezogen, ein Login-/Passwortauftrag oder mehr als drei Schritte ist.
Keine künstliche Schätzung eines unbekannten Befehls; keine generelle
KI-Fernsteuerung, keine Dauer-Mikrofonüberwachung, keine selbstständige
DEGIRO-Bedienung. Gesprochene Stopp-Befehle wirken **nur nach Antippen des
Mikrofon-Buttons**, nicht als permanentes Hotword. Die Android-Spracherkennung
kann trotz Offline-Präferenz die Daten beim Geräte-Anbieter verarbeiten.

Automatische Gradle-Tests prüfen harmlose Verknüpfungen, verbotene Mischsätze,
Duplikate, die Einzelaktionssperre und STOPP. Ein erfolgreicher CI-Lauf
ersetzt **nicht** den Test des Sprachdienstes auf dem Samsung. Für 0.7
ist eine neu signierte APK erforderlich; ein Signaturwechsel kann bei
bestehender Testinstallation die Aktualisierung verhindern.

## Zweite sichere Ausbaustufe: schnelle Auswahl und Not-Stopp (22.10.2026)

Auftragseingabe in derselben Android-App jetzt auch über Klartext-Schaltflächen: **Bob öffnen**, **Produktbilder auswählen**, **Android-Einstellungen öffnen**. Jede Schaltfläche wählt **nur** die gewünschte Aktion aus; erst eine eigene **Prüfung** und anschließend die **einmalige Ausführung** starten etwas. Text-/Sprachänderungen verwerfen die Freigabe. Die Freigabe ist maximal **60 Sekunden** gültig, einmalig verwendbar und verfällt bei App-Wechsel, fehlgeschlagener Ausführung oder dem klar sichtbaren **STOPP – Auftrag verwerfen**. Unit-Tests decken Wiederholung, anderes Ziel, Ablauf, Zeitrücksprung und Widerruf ab.

Wichtig: Der Stoppknopf widerruft einen **noch nicht ausgeführten** Auftrag. Er kann eine bereits geöffnete fremde App oder eine bereits ausgelöste Android-Systemaktion nicht rückgängig machen. Es gibt weiterhin **keinen Bedienungshilfendienst**, keine Hintergrund-Auftragsschleife, keine DEGIRO-Bedienung und keine automatische Anmeldung.

## Ergänzung 22.10.2026: Gesprochene, ausdrücklich bestätigte Handy-Aufträge

Die bereits vorhandene Android-Labor-App (kein Zweitprojekt) erhält einen Button **„🎤 Auftrag sprechen“**. Dieser öffnet nach ausdrücklichem Tippen Androids System-Spracherkennung per `RecognizerIntent.ACTION_RECOGNIZE_SPEECH`. **Keine dauerhafte Mikrofonüberwachung**, keine App-eigene Aufnahme und keine neue Mikrofon-, Internet- oder Accessibility-Berechtigung. Die bevorzugte Offline-Erkennung ist nur eine Bitte an den auf dem Samsung installierten Sprachdienst: **Der Android-/Drittanbieter-Sprachanbieter kann Audio dennoch online verarbeiten**. Das wird in der App angezeigt; ohne installierten Dienst bleibt die bisherige Text-/Button-Bedienung möglich.

Nur eindeutige, vollständig erkannte deutsche Sätze werden interpretiert, zum Beispiel **„Bob öffnen“**, **„Produktbilder auswählen“** und **„Öffne die Einstellungen“**. Sätze mit Handel, Login, DEGIRO-Bedienung, Zusatzaufträgen oder unklarer Absicht werden abgelehnt. Nach erfolgreicher Erkennung zeigt Bob den konkret erlaubten Auftrag im Klartext als Vorschau. Erst **„Geprüften Handy-Auftrag einmalig ausführen“** startet eine einzige Aktion. Die Freigabe verfällt danach; bei Abbruch/Fehler keine Aktion. Spracheingabe innerhalb der ChatGPT-Unterhaltung wird **nicht** heimlich an die Android-App weitergeleitet. Einen Auftrag mit „Goldprodukte anzeigen“ kann diese Version noch nicht bis in die Web-App hinein navigieren.

Die neue Funktion ist erst nach Installation der **neu gebauten APK** auf dem Samsung verfügbar; GitHub CI kann Kotlin-Parser und Build prüfen, aber nicht die Verfügbarkeit des Spracherkennungsdienstes oder die Bedienung auf dem echten Gerät. Gerätetest: auf **„🎤 Auftrag sprechen“** tippen, „Bob öffnen“ sagen, Vorschau lesen, einzeln bestätigen und Browserstart prüfen; danach ein nicht unterstütztes Handelskommando sprechen und die Ablehnung kontrollieren.

# Bob Android-Begleitlabor (nicht produktiv)

## Korrektur: BOB_OEFFNEN war nur ein Platzhalter (Samsung-Test 22.10.2026)

Ein realer Gerätetest zeigte beim Tippen auf „Handy-Auftrag prüfen“ den Fehler „Nicht erlaubter Auftrag“, obwohl der Beispielbefehl grau zu sehen war: `EditText.hint` zeigt nur einen Platzhalter, `text` blieb leer.

**Neue Bedienung:** Beim Öffnen steht **„Bob öffnen“** als tatsächlich vorausgefüllter, normal lesbarer Feldinhalt (nicht grau als Platzhalter). Es ist kein Kopieren oder Eingeben erforderlich: erst **Handy-Auftrag prüfen**, dann **Geprüften Handy-Auftrag einmalig ausführen**. Danach steht „Bob öffnen“ erneut zur Auswahl bereit, die Bestätigung ist jedoch verbraucht und muss für jede weitere Aktion wieder mit „Prüfen“ eingeholt werden. Für andere erlaubte Aufträge bleibt die Texteingabe bzw. Android-Teilen erhalten; die Zulassung von externen Kommandos bleibt auf die strenge Befehlsliste beschränkt.

Zusätzlicher Android-UI-Test kontrolliert den vorausgewählten Klartext „Bob öffnen“, Prüfvorschau und dass die Vorschau **keinen** Browserstart auslöst. Die CI kompiliert diesen UI-Test, führt ihn aber nicht automatisch auf einem Samsung aus. Eine Aktualisierung der APK ist für die Korrektur erforderlich; die bereits installierte 0.5 lässt sich bis dahin nutzen, indem der Befehl **wirklich eingegeben oder eingefügt** wird.

## Ergänzung 22.10.2026: ChatGPT/Bob-Handy-Aufträge – ohne Doppelentwicklung

Diese Teilstufe **erweitert die vorhandene** App `android_companion`; sie startet **keine zweite App** und überschreibt **nicht** die separat laufende Vereinfachung von Bob in PR #728.

**Bereits funktionsfähig im Quellcode:** Ein Nutzer kann in ChatGPT/Bob einen der folgenden exakt geschriebenen Einzeiler kopieren und in der Android-Begleit-App einfügen, oder den Einzeiler ausdrücklich über Android **Teilen → Bob: Android-Labor** senden:

- `BOB-AUFTRAG: BOB_OEFFNEN` – öffnet die bestehende Bob-Web-App im Browser.
- `BOB-AUFTRAG: PRODUKTBILDER_WAEHLEN` – öffnet den bereits vorhandenen Android-Bildwähler der lokalen OCR.
- `BOB-AUFTRAG: ANDROID_EINSTELLUNGEN_OEFFNEN` – öffnet nur die Einstellungen, ändert dort aber nichts.

Die App zeigt zunächst **eine Vorschau mit Klartext**. Erst nach einer separaten Berührung auf „Geprüften Handy-Auftrag einmalig ausführen“ wird genau **eine** der drei Aktionen ausgelöst. Änderungen an der Eingabe, beliebige Sätze, längere Skripte, zusätzliche Befehle, Käufe, Verkäufe und Login-Automationen werden abgewiesen. Nach Ausführung wird die Freigabe verbraucht; keine wiederholte oder verdeckte Abarbeitung. Falls Android die Ziel-App nicht öffnen kann, erscheint eine Fehlermeldung.

Das ist eine **lokale, nutzerbestätigte Auftragsübergabe**, **noch keine ChatGPT-Fernsteuerung**: Es existiert weder ein dauerhaft gekoppelter ChatGPT-Befehlskanal zum Smartphone noch ein Android-Accessibility-Service zur Bedienung von Drittanbieter-Apps. Das Labor erhält weiterhin keine Netzwerk-, Overlay-, Bildschirmaufnahme- oder Accessibility-Berechtigungen. Besonders DEGIRO wird **nicht automatisiert bedient**, und keine Echtgeldorder wird vorbereitet/ausgeführt. Bobs bestehende Broker-/OCR-/Handelsfreigaben bleiben unverändert.

**Prüfung:** `gradle -p android_companion :app:testDebugUnitTest :app:assembleDebug` sowie GitHub Actions `android-companion.yml`. Zusätzlich auf dem Samsung die **neue APK** installieren, einmal eine gültige und einmal eine unerlaubte Textfreigabe probieren und prüfen, ob das Gerät wirklich die vorgesehenen Apps öffnet. Ein erfolgreicher APK-Build ist kein Gerätetest.


## Nachbesserung 22.10.2026: „BNP OTC“ bei erfolgreicher Kurslesung

Die reale Samsung-Prüfung von zwei DEGIRO-Bildern zeigte korrekte ISIN, Geld 7,04 EUR, Brief 7,05 EUR, Zuletzt 7,04 EUR und sichtbare Anzeigezeit 22/10/2026 10:35. **Nur der Handelsplatz fehlte**, obwohl er auf dem Detailbild steht.

ML Kit kann eine Kopfzeile als mehrere einzelne Elemente erkennen, etwa `DE000PJ9NB98`, `•`, `BNP`, `OTC`. Der neue `QuoteLayout`-Parser erkennt einen OTC-/DOT-Handelsplatz nur, wenn er rechts von einer sichtbaren ISIN auf derselben visuellen Zeile oder rechts von „Börse“/„Handelsplatz“ steht. `BNP` aus dem Produktnamen allein ist ausdrücklich kein Beleg. Werte bleiben unbestätigte OCR-Beobachtungen, niemals verifizierte Handelsplätze oder ausführbare Geld-/Briefkurse.

Der neue Build und die Regressionstests müssen bestehen. Die tatsächliche Erkennung auf dem Samsung muss mit den **bereits vorhandenen** zwei Screenshots erneut geprüft werden; neue Screenshots sind nicht nötig.


## Korrektur 22.10.2026: Produktwerte in DEGIRO-Kursspalten erkennen

Die von Samsung/ML Kit extrahierten OCR-Zeilen können `Geld`, `Brief`, `Zuletzt` und die jeweiligen Zahlen in **getrennten Textblöcken** ausgeben. Deshalb sah Bob trotz vollständig sichtbarer Kurse oft nur die ISIN.

`QuoteLayout` nutzt jetzt OCR-Wort-/Zeilenrechtecke, sucht nur **räumlich passende** Werte rechts vom jeweiligen beschrifteten Feld und akzeptiert nur klare Betragsformate. `BNP OTC` wird als ungeprüfte Handelsplatzbeobachtung nur aus einer ISIN-Kopfzeile oder expliziten Handelsplatz-Beschriftung übernommen. `22/10/2026 10:35` in der Zeile „Zuletzt“ wird als **Anzeigezeit** bezeichnet und **niemals** als originalverifizierter Geld-/Briefkurs-Zeitstempel behandelt. Die Uhr im Android-Statusbereich ist keine Kursquelle. Preis im Produktkopf (z. B. `7,02 €`) wird nicht als Geld/Brief ausgegeben. Hebel und KO bleiben bei fehlender eindeutiger Beschriftung offen.

Für einen bewusst geteilten Satz aus 1–4 Bildern prüft Bob zuerst die gemeinsame ISIN, dann die extrahierten Felder. Widersprüchliche Feldwerte zwischen Bildern führen zu einer erkennbaren Ablehnung statt zu einer stillen Überschreibung. Alle Beobachtungen bleiben ungeprüft, unveröffentlicht und ohne Einfluss auf Top-3- oder Handelsfreigaben.

Synthetische Android-Testfälle decken `Geld 7,04 €`, `Brief 7,05 €`, `Zuletzt 7,04 €`, `BNP OTC` sowie abweichende Kopf- und Tageswerte ab. Das reale Samsung-OCR-Ergebnis muss nach Installation weiterhin kontrolliert werden.


Zwei strikt getrennte Untersuchungen für Bob:

## Korrektur: Teilen von zwei oder mehr Screenshots
- Samsung Galerie kann beim Teilen mehrerer ausgewählter Bilder den Android-Intent `ACTION_SEND_MULTIPLE` verwenden. Die frühere App meldete nur `ACTION_SEND` an und erschien deshalb möglicherweise **nicht** in der App-Auswahl.
- Neu: `ACTION_SEND` und `ACTION_SEND_MULTIPLE` mit `image/*`; über **Teilen → Mehr** kann „Bob: Android-Labor“ beim Teilen von 1–4 Bildern ausgewählt werden. Aus der App selbst lassen sich ebenfalls mehrere Bilder über **Produktbilder auswählen** wählen.
- Alle Bilder werden **lokal** und nacheinander gelesen. Bei ausdrücklich gemeinsam ausgewählten Bildern genügt jetzt **eine** eindeutig erkannte und prüfziffergültige ISIN als Serienanker. Andere Bilder ohne fehlerfrei erkannte ISIN werden nur **vorläufig als Teil dieser vom Nutzer zusammengestellten Serie** zugeordnet. Eine andere erkennbare ISIN oder ein widersprechender Kennzeichentext sperrt die Serie. Die App meldet transparent, auf wie vielen Bildern die ISIN tatsächlich erkannt wurde. Alle übernommenen Werte bleiben unbestätigt und können niemals Handelbarkeit oder ausführbare Kurse nachweisen.
- OCR liest zusätzlich die beschrifteten Felder `Börse` (als ungeprüfte Handelsplatzbeobachtung) und `Zuletzt` (separater, nicht ausführbarer Preis). Fehlende Geld-/Briefkurse werden **nicht** durch `Zuletzt` ersetzt. Kein automatischer Handelsnachweis.
- Diese Intent-Korrektur behebt eine plausible Ursache des fehlenden Share-Ziels; ob die App im Samsung-Galerie-Menü erscheint, muss **am konkreten Handy** geprüft werden.
- Für die neue APK muss der Nutzer eine aktualisierte Version installieren; die alte APK bekommt die neue Mehrfachteilen-Funktion nicht allein durch Bobs Web-Update.

## Vereinfachter Ablauf (22.10.2026)
1. In DEGIRO **ein einzelnes Produkt** öffnen und bis zu vier Screenshots dieses Produkts ohne Depot-/Kontodaten aufnehmen.
2. Ein oder mehrere Bilder in Samsungs Galerie auswählen und über **Teilen → Mehr → Bob Android-Labor** ausdrücklich teilen.
3. Das Android-Labor verarbeitet das freigegebene Bild mit lokalem OCR und öffnet **Bob** über eine HTTPS-URL mit einem **Fragment** (kein HTTP-Request mit OCR-Daten). Die Web-App entfernt das Fragment unmittelbar aus dem Verlauf und zeigt den **ungeprüften** Datensatz unter **Mehr → DEGIRO** an. Keine manuelle Dateiauswahl, Zwischenablage oder Texteingabe mehr nötig. Falls Bob eine Anmeldung fordert, zuerst anmelden und anschließend die Übertragung wiederholen.
4. Alternativ im Android-Labor **Bild manuell auswählen** und **In Bob anzeigen – ohne Kopieren** drücken. Der alte Kopierknopf bleibt als Rückfalllösung erhalten.

**Sicherheit:** Die automatisch erzeugte Übergabe enthält ausschließlich eine gültige ISIN und eng begrenzte OCR-Felder; Originalbild, Benutzerkennung, Kennwörter und sonstiger OCR-Text werden nie übertragen. Daten werden nicht als verifizierter Handelsplatz, Livekurs oder Handelsfreigabe gewertet. Fragmentdaten sind kurzzeitig für den lokal öffnenden Browser sichtbar; Bob entfernt sie nach dem Laden. Keine Echt-Order- oder Bot-Funktion. Der neue Ablauf muss auf dem konkreten Android-Gerät und mit der bestehenden Bob-Anmeldesitzung überprüft werden. Der GitHub-APK-Build ist noch kein tatsächlicher Gerätetest.


1. **Lokale Bild-Erkennung**: Nutzer wählt ein bereits vorhandenes Bild bewusst über Androids Dokumentauswahl aus oder teilt ein Bild über das Android-Menü ausdrücklich mit dem Bob-Android-Labor. Google ML Kit erkennt lokal Text; ein eng begrenzter Parser zeigt prüfziffergültige ISINs und einzelne klar beschriftete Zahlen als **unbestätigte OCR-Entwürfe**. Die Übergabe erfolgt ausschließlich durch bewusstes Kopieren in die Zwischenablage und Einfügen in Bobs neuem Menü **Mehr → DEGIRO → Android-Bildschirmdaten** oder durch Auswahl eines Empfängers im Android-Teilen-Menü. Es gibt keinen automatischen Upload und keinen direkten Bob-API-Zugriff. Keine Vollständigkeits- oder Zeitgültigkeitsbehauptung.
2. **Automatisierte Bedienung – nur eigenes Mock-UI**: Android UIAutomator gibt eine ISIN ein, tippt einen Suchknopf und kontrolliert den simulierten Ergebnistext in diesem Testprogramm. Nicht die DEGIRO-App, nicht die Anmeldung und keine Ordermaske.

## Hintergrund / Integrationsgrenze

- DEGIRO selbst untersagt Drittanbieter-Automatisierung und hat keine öffentliche Entwickler-API. Für die Live-App wird deshalb **keine** Accessibility- oder UIAutomator-Steuerung ausgeliefert. Offizielle Aussage: https://www.degiro.ch/helpdesk/en/trading-platform/can-i-automate-trades-or-use-trading-bots-degiro
- SnapTrade DEGIRO bleibt read-only: https://snaptrade.com/brokerage-integrations/degiro-api
- Bob nutzt bereits eine authentifizierte, same-origin-geschützte Nachweisstrecke (`/api/degiro/candidate-proof`), die Bildprüfung und Berechtigungen nicht automatisch durch Android-OCR ersetzt. Das Labor ruft sie bewusst **nicht** auf.
- Die Android-Anwendung hat **keine INTERNET-, Accessibility-, Bildschirmerfassungs- oder sonstigen besonders sensiblen Berechtigungen**, speichert keine Kontodaten, fragt keine Zugangsdaten ab und hat keine DEGIRO-Paket- oder URL-Verweise im ausführbaren Code. Eine Bildfreigabe erfolgt durch eine bewusste Android-Aktion. Wer den OCR-Entwurf in die Zwischenablage kopiert, muss wissen, dass andere Apps vorübergehend Zugriff auf den kopierten Text bekommen könnten.
- OCR kann 0/O/9 vertauschen, Labels vertauschen, mehrere Produkte mischen und Zeitstempel falsch lesen. Gültiger ISIN-Prüfcode ist nur ein Identitäts-Plausibilitätsfilter, kein Handelsplatz- oder Kursbeleg. Die Originalbild-, Originalzeit-, Emittenten-, KO- und Brokerprüfungen in Bob bleiben vollständig bestehen.

## Android Studio – lokale Prüfung

1. `android_companion/` als Android-Studio-Projekt öffnen (Android-Gradle-Plugin 8.7.3 / Kotlin 2.0.21, Android SDK 35 erforderlich). GitHub Actions erstellt einen Debug-APK als **Testartefakt**; dies ist keine App-Store-Veröffentlichung.
2. Auf eigenem Android-Gerät oder Emulator starten. Über **Bild manuell auswählen und lokal lesen** ein Testbild wählen oder in der Galerie ausdrücklich **Teilen → Bob Android-Labor**. **Keine** Screenshots mit Login, Passwort oder Kontodaten teilen. Bei mehr als einer ISIN werden keine Produktwerte übertragen.
3. Den unbestätigten OCR-Entwurf mit dem Kopierknopf manuell in Bob unter **Mehr → DEGIRO → Android-Bildschirmdaten** einfügen und prüfen. Diese Prüfansicht sendet nichts an Bobs Server, verändert weder Prüfstatus noch Rangliste und behält die Eingabe nicht dauerhaft. Danach im Demo-Bereich die künstliche ISIN DE000FG14AV8 suchen. Es darf ausschliesslich `DEMO-TREFFER ... KEIN ECHTER HANDEL` erscheinen.
4. Den unabhängigen UI-Test über Android Studio auf einem Emulator/Gerät starten. Falls später ein Gradle Wrapper hinzugefügt wurde, kann auch `./gradlew connectedAndroidTest` genutzt werden; aktuell ist kein Wrapper eingecheckt.
5. Vor einer Verbindung zu Bob erforderlich: freigegebener Datenumfang, brokerrechtliche Zustimmung für automatischen Abruf, authentifiziertes Pairing ohne Passwort-Weitergabe, replay-sicherer Empfang, separates zeitbehaftetes Quellenschema, Einwilligung/Abbruch, lokale Redaktions- und Review-Prüfung sowie Device-Tests.

**Status**: Laborquelle / unveröffentlichter Entwurf. Weder APK-Erstellung, Gerätetest noch produktiver Betrieb sind durch das Einchecken nachgewiesen. Bestehende Bob-Builds, Datenquellen, Handelsfreigaben und Trading-Simulationen bleiben unverändert.


### Vereinfachter Start der lokalen Leseprüfung

„Prüfung starten“ öffnet DEGIRO und aktiviert einen ausschließlich im Arbeitsspeicher
liegenden Leseauftrag für maximal 60 Sekunden / 30 Versuche. Der Android-Dienst
muss vorher vom Nutzer aktiviert sein. Fensteränderungen der DEGIRO-App lösen
gedrosselte Leseversuche aus; Ereignistexte werden nicht gelesen. Nach dem ersten
lesbaren Produkt endet der Auftrag. STOPP, Dienstunterbrechung, Sperrbildschirm
oder Prozessneustart beenden ihn ebenfalls. Es gibt keine automatische Suche,
Gesten, Orders oder Übertragung. Die Männchen-Taste bleibt als Alternative erhalten.
Bei Rückkehr zu Bob Handy wird der lokale Entwurf direkt angezeigt. Das Öffnen
der Webprüfung erfolgt weiterhin ausdrücklich. Tatsächliches Verhalten auf Samsung
und zugängliche DEGIRO-Produktfelder müssen am Gerät geprüft werden.

### Wiederholung bei fehlendem Fensterinhalt

Ein expliziter Start benachrichtigt den verbundenen Dienst direkt. Auch ohne neue
Android-Fensterereignisse folgen maximal 30 Leseversuche in höchstens 60 Sekunden.
Ein vorübergehend fehlender Fensterinhalt ist kein Nachweis einer DEGIRO-Sperre.
STOPP und Sperrbildschirm beenden den Auftrag; außerhalb des Auftrags gibt es
keine regelmäßigen Leseversuche. Eindeutig beschriftete Kurse bestimmen ihre
Währung unabhängig vom Kontostand. Fehlende ISIN, geschützte Ansichten und
widersprüchliche Produktwährungen bleiben gesperrt. Getrennte Bildausschnitte
werden nicht stillschweigend miteinander verknüpft. Geräteabnahme bleibt offen.

### Fensterdiagnose und begrenzter Ersatzweg

Wenn rootInActiveWindow fehlt, wird Androids interaktive Fensterliste genutzt.
Nur genau ein aktives, fokussiertes Anwendungsfenster ist zulässig; dessen
Paket muss DEGIRO entsprechen. Hintergrundfenster, Systemfenster und mehrdeutige
Auswahl werden nicht gelesen. Schutzprüfungen bleiben bestehen.

BOB-LESEDIAGNOSE/1 zeigt ausschließlich feste Statuswerte/Zähler: Dienstverbindung,
Text-/Fensterfähigkeit, direkter/alternativer Fensterzugriff, fehlende Wurzel,
fremde App, geschützte Ansicht, fehlende Felder, Entwurf oder Fehler. Keine
Paketnamen, Fenstertitel, Kontodaten, ISINs oder Bildschirmtexte. Nur Arbeitsspeicher,
Löschung nach fünf Minuten/STOPP; Kopieren nur per Taste, keine Übertragung.
Android-Geräteabnahme ist weiterhin offen.
