# Recherche: MCO Markets / Gold

Seit dieser Änderung gilt ausschließlich der YouTube-Kanal `UCsl6Z6p7GOkczo8Cv-GH6Dg` (MCO Markets). Andere Quellen und manuell eingelesene Fremdkanäle werden aus dem Bericht ausgeschlossen. Gold muss im Videotitel stehen, eine allgemeine Erwähnung in der Kanalbeschreibung genügt nicht.

Der vorhandene Serverjob prüft alle 15 Minuten den Atom-Feed. Falls dieser ausfällt, wird die öffentliche Kanal-Videoseite gelesen: Kanal-ID bestätigen, nur das ausgewählte Upload-Raster auswerten. Relative Altersangaben werden angezeigt, aber nicht in erfundene genaue Veröffentlichungszeiten umgewandelt. Gleichnamige Videos bleiben über ihre Video-ID getrennt.

Je Lauf werden maximal drei neueste gefundene Videos auf direkt öffentlich abrufbare englische oder deutsche Untertitel geprüft. Bei leerer erster Spur wird eine zweite angebotenene Spur versucht. Alle leeren Antworten führen ausdrücklich zu „Untertitel vorhanden, aber kein Text abrufbar“, niemals zu einer vorgetäuschten Analyse. Keine Authentifizierungs-, Challenge- oder Proxy-Umgehung.

Bei Erfolg werden bis zu drei ganze relevante Originalsätze (maximal 90 Wörter) als Kontext und eine konservative regelbasierte Richtungsbewertung gezeigt. Bedingungen und Negationen bleiben erhalten. Dies ist noch keine generative deutschsprachige Zusammenfassung; ein englisches Transkript hat englische Originalaussagen. Unvollständige oder bedingte Signale bleiben UNKLAR. Eine einzelne Anbietermeinung ersetzt keinen unabhängigen Quellenkonsens und ändert keine Handelsfreigabe.

Offene Grenze: Beim real geprüften Video GB1n0fEkfn4 liefert der direkte Serverabruf weiterhin leere Antworten. Das vollständige Transkript ließ sich separat mit der ChatGPT-Browserfunktion exportieren; diese Funktion ist nicht Bestandteil des Render-Servers. Eine serverseitige Integration dieses Browserexports wurde nicht behauptet und kein funktionierender Ersatz vorgetäuscht.

Tests decken Kanal-/Themenfilter, gleichnamige Videos, Kanal-Fallback ohne Empfehlungen, Ausschluss alter Fremdquellen, Alternativspur, leere Antworten und Erhalt von Bedingungen im Kontext ab.

## Optionaler zusätzlicher Transkript-Zugang (vorbereitet, noch kein Live-Nachweis)

`research_transcript_provider.py` bindet Supadata über dessen dokumentierten nativen Transkript-Endpunkt an. Der Schlüssel `SUPADATA_API_KEY` gehört ausschließlich in die Umgebung des bestehenden Push-/Speicherdiensts. Keine Schlüssel im Browser, Repository oder Chat. Ohne Schlüssel bleibt der Dienst deaktiviert.

Die bestehende interne Tokenprüfung schützt den neuen Endpunkt. Die Hauptanwendung bestätigt zuvor Kanal-ID und Gold-Titel. Übermittelt werden nur öffentliche MCO-Video-IDs. Bei leerem Direktabruf fragt Bob vorhandene Untertitel mit `mode=native` an; keine Audio-Generierung, Übersetzung, automatische Aufladung oder Tarifänderung. Die Datenbank reserviert jeden Versuch vor der Anfrage, begrenzt auf 90 Versuche in rollenden 31 Tagen, speichert erfolgreiche Texte dauerhaft und pausiert fehlgeschlagene Videoabrufe 24 Stunden. Auch fehlgeschlagene Versuche zählen lokal. Das Limit bezieht sich nur auf Bob; weitere Nutzer desselben API-Schlüssels teilen das Anbieterkontingent.

Aktivierung: kostenlosen Supadata-Zugang anlegen, Schlüssel im Render-Pushdienst hinterlegen, dann das Beispiel GB1n0fEkfn4 und ein neues MCO-Gold-Video vollständig testen. Der Free-Tarif weist derzeit 100 monatliche Credits ohne Kreditkarte aus. Das ist keine Erfolgsgarantie für konkrete Videos. Ohne diesen Live-Test ist die automatische Inhaltsanalyse nicht als behoben zu melden.

Dokumentation: https://supadata.ai/pricing und https://github.com/supadata-ai/skills/blob/main/skills/supadata/references/video.md

## Fehlerbehebung 8. Oktober 2026

Fehlerhafte Untertitelspuren überspringen und anschließend den vorhandenen Ersatzdienst nutzen. Interne Fehlercodes unterscheiden Zugang, Kontingent, Video, temporäre Verfügbarkeit und Wiederholungspause ohne Schlüssel oder fremde Fehlertexte auszugeben. Fehlversuche pausieren eine Stunde, maximal drei neue Versuche je Video innerhalb von 24 Stunden; das globale Limit von 90 Versuchen in 31 Tagen bleibt bestehen. Bereits gespeicherte Transkripte benötigen keinen erneuten Anbieterabruf. Alte Versuche ohne Videozuordnung bleiben im globalen Limit gezählt.

Der automatische Lauf verwendet seine bereits bestätigte Kanalliste für den Ersatzabruf weiter. Unabhängige manuelle Abrufe prüfen weiterhin selbst die Kanalzuordnung. Relative Altersangaben werden als ungefähr mit Abrufzeit angezeigt, ohne einen exakten Veröffentlichungszeitpunkt oder aktuelle Richtungsstimme zu erfinden. Video-IDs unterscheiden gleichnamige Uploads.

## Strukturierter Überblick und Videostellen

`research_overview.py` durchsucht sämtliche gelieferten Transkriptsegmente, verbindet Satzteile über Segmentgrenzen und wählt vollständige Originalsätze zu Einordnung, bullischen/bärischen Aussagen, Kursmarken, Bedingungen und Zeithorizont. Zahlen, Negationen und Bedingungen bleiben im Satz erhalten. Nicht gefundene Themen werden als nicht eindeutig erkannt angezeigt. Das ist eine extraktive Themenübersicht, keine generative Gesamtzusammenfassung; sie garantiert keine Vollständigkeit. Die Richtungsbewertung bleibt unabhängig.

Originalaussagen sind aufklappbar und mit dem Beginn ihres Untertitelsegments verlinkt. Bis zu drei Textstellen öffnen auf ausdrücklichen Klick einen YouTube-NoCookie-Player mit Startzeit; keine externen Playeranfragen beim bloßen Anzeigen des Berichts. Die Einbettung zeigt echte Videobilder, aber keine exportierten Standbilder; der konkrete Chartinhalt wurde nicht visuell geprüft. Falls der Anbieter Einbettungen sperrt, bleibt ein direkter YouTube-Zeitlink verfügbar. Eingefügte Transkripte ohne verlässliche Zeitmarken erhalten keine erfundenen Belegzeiten oder Playerstellen.

Ergänzung: Die Anbindung für freie KI-Zusammenfassungen und gespeicherte Zeitleisten-Vorschaubilder ist implementiert; Aktivierung und erfolgreicher Live-Abruf sind getrennt nachzuweisen. Die dokumentierte Supadata-Extraktion kostet 5 Credits pro angefangener Videominute und wird wegen des bestehenden kostenlosen Kontingents nicht aktiviert. Referenzen: https://docs.supadata.ai/get-extract und https://developers.google.com/youtube/player_parameters .



## KI-Zusammenfassung und gespeicherte Videobilder (8. Oktober, abends)

`research_enhancements.py` ergänzt den regelbasierten Überblick, ohne dessen Richtungsstimme zu ändern. Der interne token-geschützte Endpunkt `/research-enhancement/read` erhält nur das bereits dem öffentlichen MCO-Gold-Video zugeordnete Transkript und seine Videostellen. Manuell eingefügte, ungeprüfte Texte werden nicht übertragen.

Die Gemini-Anbindung über `generateContent` verwendet `gemini-2.5-flash-lite`, das am 8. Oktober 2026 im Standard-Free-Tier mit kostenlosem Text-Eingang/Ausgang dokumentiert ist. Voraussetzung: **ein Google-AI-Studio-Projekt ohne aktivierte Abrechnung**. Ein API-Schlüssel allein beweist den Tarif nicht. Deshalb bleiben externe KI-Anfragen aus, bis im bestehenden Render-Pushdienst beides hinterlegt ist:

- `GEMINI_API_KEY`: Schlüssel ausschließlich serverseitig als Geheimnis hinterlegen.
- `BOB_GEMINI_FREE_PROJECT=confirmed-no-billing`: erst setzen, nachdem fehlende Abrechnung beim Projekt bestätigt wurde. Nicht auf einem abgerechneten Projekt aktivieren.

Bob aktiviert weder Abrechnung noch automatische Aufladung und verwendet keine kostenpflichtigen Ersatzanbieter. Es gibt keine allgemeine API-Option „nur kostenlos“: Die entscheidende Kostensperre ist das Projekt ohne Abrechnung. Zusätzlich reserviert PostgreSQL maximal zehn Versuche pro rollenden 24 Stunden und einen pro Minute; Fehlschläge zählen mit. Pro Video gilt nach einem Versuch eine 24-Stunden-Pause. Bei Quotenfehlern, unvollständigen Antworten oder fehlenden Belegen bleibt der Originalsatz-Überblick erhalten. Keine automatischen Wiederholungen innerhalb desselben Aufrufs. Erfolgreiche Zusammenfassungen werden nach Transkript-Hash wiederverwendet. Google kann Daten im kostenlosen Tarif zur Produktverbesserung verwenden; übertragen werden hier ausschließlich die öffentlichen Video-Untertitel, keine Produkt-, Konto- oder Trade-Daten.

Die gesamte übermittelte Segmentliste wird in einer Anfrage verarbeitet. Deutschsprachige Abschnitte referenzieren Originalsegmente; neue numerische Tokens außerhalb ihrer Belegstellen werden verworfen. Das beweist keine semantische Fehlerfreiheit oder lückenlose Videodeckung. Aussagen gelten als Autorensicht, nicht als aktuelle Goldkurse. Charts werden nicht von der KI ausgewertet.

Standbilder stammen ausschließlich aus öffentlich bereitgestellten YouTube-Storyboard-Spezifikationen des überprüften Videos. Sie sind niedrig aufgelöste Zeitleisten-Vorschaubilder, keine sekundengenauen HD-Frames. Bob verwendet deren deklariertes Zeitintervall, lädt höchstens drei benötigte JPEG-Tafeln von `i.ytimg.com/sb/<videoId>/` ohne Weiterleitungen und speichert die ausgeschnittenen Originalbilder als JSONB in PostgreSQL. Keine Video-Downloads, Anmeldedaten, Umgehungsdienste oder generierten Ersatzbilder. Bei nicht lesbaren Metadaten, fehlender Zeitzuordnung oder Bildern bleibt der Player erhalten; ein Fehlschlag pausiert 24 Stunden. Der Bildinhalt wird nicht als Chartanalyse ausgegeben. Zusammenfassungen/Bilder werden 32 Tage nach letzter Speicherung bereinigt.

Tests: vollständige Segmentübertragung einschließlich später Aussagen, Pflichtbelege, Zahlenprüfung, unvollständige Antworten, Kostensperre ohne bestätigtes Free-Projekt, Kontingentsperre, Cache-Wiederverwendung, keine Geheimnisse in Fehlern, Host-/Video-Zuordnung und richtige Bildzelle/Zeit.

Quellen: https://ai.google.dev/gemini-api/docs/pricing und https://ai.google.dev/api/generate-content
