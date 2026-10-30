"""Static public OAuth information; no account, credential or database access."""
from urllib.parse import urlsplit

STYLE = '<style>body{font:18px/1.6 system-ui,sans-serif;color:#203047;background:#f4f6fa;margin:0}main{max-width:760px;margin:32px auto;padding:28px;background:white;border-radius:16px}a{color:#254e99}h1,h2{line-height:1.25}nav{display:flex;gap:24px;flex-wrap:wrap}@media(max-width:600px){main{margin:12px;padding:22px}}</style>'
HOME = '''<h1>Bob Archiv privat</h1>
<p>Bob ist ein privater Assistent zur Beobachtung von Goldmärkten, zur Auswertung von Hebelprodukten und für Simulationen. Bob führt keine Echtgeldorders aus.</p>
<p>Bob Archiv sichert ausgewählte historische Daten und Prüfnachweise aus Bob im Google Drive des Nutzers. Die Google-Verbindung dient dem Erstellen und Prüfen dieser Archive. Wiederherstellungstests prüfen, ob die gesicherten Daten lesbar sind.</p>
<p>Die Nutzung der privaten Anwendung erfordert eine Anmeldung. Diese Informationsseite und die Datenschutzerklärung sind öffentlich zugänglich.</p>
<nav><a href="/archive/privacy">Datenschutzerklärung</a><a href="/login">Bei Bob anmelden</a></nav>'''
PRIVACY = '''<h1>Datenschutzerklärung für Bob Archiv privat</h1>
<p>Stand: 30. Oktober 2026. Diese Erklärung beschreibt die Google-Drive-Anbindung von Bob Archiv.</p>
<h2>Verantwortlicher und Kontakt</h2>
<p>Robert Simon · <a href="mailto:robsimon85@gmail.com">robsimon85@gmail.com</a>. Bei Fragen zur Verarbeitung oder zur Löschung gespeicherter Verbindungsdaten ist dies die Kontaktadresse.</p>
<h2>Welche Daten verarbeitet werden</h2>
<p>Nach deiner Zustimmung speichert Bob die für die Google-Verbindung erforderlichen OAuth-Zugangsdaten verschlüsselt auf der Serverinfrastruktur. Dazu gehört ein Aktualisierungstoken, mit dem Bob auch ohne erneute Anmeldung Archive erstellen und prüfen kann. Dein Google-Passwort wird nicht an Bob übermittelt.</p>
<p>Bob verarbeitet Kennungen und technische Metadaten des freigegebenen Archivordners und der Archivdateien, etwa Namen, Größe und Prüfsummen. Archive enthalten ausgewählte historische Markt-, Produkt-, Simulations- und Prüfdaten aus Bob. Sie sind keine vollständige Sicherung aller Datenbankeinstellungen.</p>
<h2>Zweck und Umfang des Google-Zugriffs</h2>
<p>Die Berechtigung „drive.file“ erlaubt den Zugriff auf Dateien, die Bob erstellt oder die du ausdrücklich für die Anwendung freigibst. Bob beantragt keinen allgemeinen Zugriff auf sämtliche Inhalte deines Google Drive. Die Verbindung wird zum Erstellen, Hochladen, erneuten Herunterladen und Prüfen der Archive sowie zur Verwaltung des ausgewählten Archivordners verwendet.</p>
<h2>Speicherung und Empfänger</h2>
<p>Die Anwendung und ihre Datenbank laufen bei Render. Archivdateien und Prüfbelege werden in deinem Google Drive gespeichert; für Wiederherstellungsprüfungen werden Archivdaten auf der Serverinfrastruktur verarbeitet. Google und Render verarbeiten dabei Daten im Rahmen ihrer jeweiligen Dienste. Die Archivfunktion veröffentlicht deine Archive nicht und erteilt keine öffentlichen Freigaben.</p>
<p>Google-Nutzerdaten werden nicht verkauft, nicht für Werbung verwendet und nicht zum Trainieren allgemeiner KI-Modelle eingesetzt. Die Verwendung von Informationen aus Google APIs richtet sich nach der <a href="https://developers.google.com/terms/api-services-user-data-policy">Google API Services User Data Policy</a>, einschließlich ihrer Limited-Use-Anforderungen.</p>
<h2>Aufbewahrung, Widerruf und Löschung</h2>
<p>Die gespeicherte Verbindung bleibt für die eingerichtete Archivierung erhalten, bis sie entfernt oder ungültig wird. Du kannst den Zugriff jederzeit in den <a href="https://myaccount.google.com/connections">Verbindungen deines Google-Kontos</a> widerrufen. Danach kann Bob ohne erneute Freigabe nicht weiter auf Google Drive zugreifen.</p>
<p>Ein Widerruf löscht bereits gespeicherte Archive und lokale Verbindungsdaten nicht automatisch. Archivdateien kannst du in Google Drive löschen; für die Entfernung serverseitiger Verbindungsdaten wende dich an den oben genannten Verantwortlichen. Archive und Originaldaten werden durch die bloße Google-Verbindung nicht automatisch gelöscht.</p>
<h2>Diese öffentlichen Seiten</h2>
<p>Diese Informationsseiten verwenden keine Analyse- oder Werbeskripte und setzen selbst keine Cookies. Beim Abruf können beim Hostinganbieter technisch notwendige Verbindungsdaten wie IP-Adresse, Zeitpunkt und angeforderte Adresse anfallen.</p>
<nav><a href="/archive/about">Über Bob Archiv</a><a href="/login">Bei Bob anmelden</a></nav>'''
PAGES = {'/archive/about': ('Bob Archiv privat', HOME), '/archive/privacy': ('Datenschutzerklärung · Bob Archiv privat', PRIVACY)}


def route(handler, head=False):
    page = PAGES.get(urlsplit(handler.path).path)
    if page is None:
        return False
    title, content = page
    body = ('<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + title + '</title>' + STYLE + '</head><body><main>' + content + '</main></body></html>').encode('utf-8')
    handler.send_response(200)
    for key, value in [('Content-Type', 'text/html; charset=utf-8'), ('Content-Length', str(len(body))), ('Cache-Control', 'public, max-age=300'), ('X-Content-Type-Options', 'nosniff'), ('Referrer-Policy', 'no-referrer'), ('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")]:
        handler.send_header(key, value)
    handler.end_headers()
    if not head:
        handler.wfile.write(body)
    return True
