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
