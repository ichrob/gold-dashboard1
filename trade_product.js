/* Product-specific scenarios for active trades. No executable broker quotes. */
(function(root){
 const positive=v=>typeof v==='number'&&Number.isFinite(v)&&v>0;
 function model(values){
  if(!values||values.simpleSpotTurbo!==true||values.referenceConfirmed!==true)throw Error('Produktbedingungen und zusammengehörige Referenzwerte bestätigen. Unterstützt: einfaches Gold-Spot-Turbo in EUR.');
  if(!/^[A-Z]{2}[A-Z0-9]{9}[0-9]$/.test(values.isin||'')||!['LONG','SHORT'].includes(values.direction))throw Error('Produkt-ISIN oder Richtung fehlt.');
  const x={isin:values.isin,direction:values.direction,simpleSpotTurbo:true,referenceConfirmed:true,currency:'EUR'};
  for(const k of ['bid','goldReference','fxReference','fxScenario','ratio','strike','ko','entry','quantity']){x[k]=Number(values[k]);if(!positive(x[k]))throw Error('Produktwert fehlt: '+k);}
  if(!Number.isInteger(x.quantity))throw Error('Stückzahl muss ganzzahlig sein.');
  for(const k of ['source','referenceAt']){x[k]=String(values[k]||'').trim();if(!x[k])throw Error('Produktnachweis fehlt: '+k);}
  if((x.direction==='LONG'&&x.goldReference<=x.ko)||(x.direction==='SHORT'&&x.goldReference>=x.ko))throw Error('Referenz liegt an oder jenseits der KO-Barriere.');
  return x;
 }
 function price(m,gold){
  if(!m||!positive(gold))return {available:false,reason:'Produktnachweis fehlt'};
  const d=m.direction==='LONG'?1:-1;
  if(d*(gold-m.ko)<=0)return {available:false,reason:'KO-Barriere erreicht; kein regulärer Verkaufskurs'};
  const eur=m.bid+d*m.ratio*((gold-m.strike)*m.fxScenario-(m.goldReference-m.strike)*m.fxReference);
  return positive(eur)?{available:true,price:eur,pnl:(eur-m.entry)*m.quantity}:{available:false,reason:'Kein positiver Modellkurs'};
 }
 function withFx(m,spots,now=Date.now()){
  const fx=spots?.usd_eur_meta,rate=Number(fx?.rate),at=Date.parse(fx?.fetchedAt);
  if(!m||!positive(rate)||!Number.isFinite(at)||at>now)return m;
  return {...m,fxScenario:rate,fxDetails:{...fx,delayed:!!fx.error||now-at>90000}};
 }
 function label(m,gold){const x=price(m,gold);return x.available?'≈ '+x.price.toFixed(4)+' EUR/Stück (geschätzt) · Gold '+gold.toFixed(2)+' USD/oz'+(m.fxDetails?.delayed?' · FX-Aktualisierung verzögert':''):x.reason;}
 root.BobTradeProduct={model,price,label,withFx};
 if(typeof module!=='undefined')module.exports=root.BobTradeProduct;
})(typeof window!=='undefined'?window:globalThis);

