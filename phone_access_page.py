"""Authenticated, owner-driven access prompt. No phone action from a browser GET."""
HTML = r'''<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bob Handy · DEGIRO-Zugriff</title>
<style>
:root{color-scheme:light}body{font:17px/1.5 system-ui,sans-serif;color:#172a3a;max-width:560px;margin:40px auto;padding:0 20px}
section{border:1px solid #bfcdd6;border-radius:14px;padding:20px}button,a.action{display:block;font:inherit;font-weight:700;
border:0;border-radius:11px;background:#145cb1;color:white;padding:14px;text-align:center;width:100%;box-sizing:border-box;margin:13px 0;text-decoration:none}
button.secondary{background:#e9eff5;color:#172a3a}small{display:block;color:#566775;margin-top:15px}
#reader{display:none}#choices{display:none}
</style></head><body><main><h1>Bob benötigt DEGIRO-Zugriff</h1><section>
<p id="status" role="status" aria-live="polite">Anfrage wird geprüft …</p>
<div id="choices">
<button id="approve">Jetzt freigeben</button>
<button class="secondary" id="later">Später · in 20 Minuten erneut fragen</button></div>
<div id="reader"><p><strong>Jetzt das Samsung entsperrt lassen und Bob Handy öffnen.</strong>
Bestätige die lokale Produktlesung und lege das Handy kurz weg. Du kannst es danach wieder benutzen.</p>
<a class="action" href="bobhandy://access/READ_PRODUCTS">Bob Handy öffnen und Lesung bestätigen</a>
<p>Falls Android den Link nicht öffnet: Bob Handy manuell starten und
„Bob starten · DEGIRO, Gold und fehlende Werte“ drücken.</p></div>
<small>Werktags 08:00–22:00 Uhr (Zürich). Keine PIN-Umgehung und keine Handelsorder.
Die Push-Nachricht ist nur eine Zugriffsbitte. Die lokale Freigabe bleibt notwendig.</small>
</section></main><script>
'use strict';
const status=document.getElementById('status');
const choices=document.getElementById('choices');
const reader=document.getElementById('reader');
let requestId=null;
async function api(value){
 const res=await fetch('/api/push/phone-access',{method:'POST',credentials:'same-origin',
  cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)});
 if(!res.ok)throw Error('Bob-Server nicht erreichbar ('+res.status+').');
 return res.json();
}
async function refresh(){
 try{
  const s=await api({action:'status'});requestId=s.requestId;
  choices.style.display=s.status==='pending'?'block':'none';
  reader.style.display=s.status==='approved'?'block':'none';
  const label={
   pending:'Bob möchte die aktuellen DEGIRO-Produktdaten lesen. Du entscheidest, wann der Bildschirm frei ist.',
   approved:'Freigabe im Browser bestätigt. Der eigentliche Lesestart benötigt noch deinen lokalen Tipp in Bob Handy.',
   completed:'DEGIRO-Produktliste wurde erfolgreich übernommen. Du kannst das Handy wieder benutzen.',
   snoozed:'Zurückgestellt. Bob darf später erneut fragen.',
   expired:'Die Anfrage ist abgelaufen. Es wurde keine Lesung gestartet.',
   none:'Momentan gibt es keine offene Zugriffsanfrage.'
  };
  status.textContent=label[s.status]||'Status: '+s.status;
 }catch(e){status.textContent=e.message;choices.style.display='none';}
}
async function choose(choice){
 choices.style.display='none';
 try{
  const r=await api({action:'decide',requestId,choice});
  if(!r.ok)throw Error('Anfrage ist nicht mehr aktuell.');
  await refresh();
 }catch(e){status.textContent=e.message;await refresh();}
}
document.getElementById('approve').onclick=()=>choose('approve');
document.getElementById('later').onclick=()=>choose('later');
refresh();
</script></body></html>'''.encode('utf-8')


def send(handler):
    handler.send_response(200)
    for k, v in [
        ('Content-Type', 'text/html; charset=utf-8'),
        ('Cache-Control', 'no-store'),
        ('X-Content-Type-Options', 'nosniff'),
        ('X-Frame-Options', 'DENY'),
        ('Referrer-Policy', 'no-referrer'),
        ('Content-Security-Policy',
         "default-src 'none'; connect-src 'self'; script-src 'unsafe-inline'; "
         "style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"),
        ('Content-Length', str(len(HTML)))
    ]:
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(HTML)
