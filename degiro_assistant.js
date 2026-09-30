/* Bob DEGIRO assistant: deterministic risk math and product-fit checks. No order execution. */
(function(){
  function n(v){const x=Number(v);return Number.isFinite(x)?x:null;}
  function koDistancePct(spot,ko){spot=n(spot);ko=n(ko);if(spot===null||ko===null||spot<=0)return null;return Math.abs((spot-ko)/spot)*100;}
  function directionOf(spot,ko){spot=n(spot);ko=n(ko);if(spot===null||ko===null)return null;return ko<spot?"LONG":ko>spot?"SHORT":null;}
  function riskModel(p){
    const spot=n(p.spot),stop=n(p.stop),riskEur=n(p.riskEur),fx=n(p.fxUsdEur),lev=Math.max(1,n(p.leverage)||1);
    if(spot===null||stop===null||riskEur===null||riskEur<=0)return {ok:false,reason:"Ungültige Eingabedaten für Risiko."};
    if(fx===null||fx<=0)return {ok:false,reason:"Keine gültige USD→EUR-FX-Rate."};
    const dist=Math.abs(spot-stop); if(dist<=0)return {ok:false,reason:"Stop-Distanz ist null."};
    const maxLossUsd=riskEur/fx,approxNotionalUsd=maxLossUsd/(dist/spot),approxNotionalEur=approxNotionalUsd*fx,marginEur=approxNotionalEur/lev;
    const ko=n(p.ko),koPct=koDistancePct(spot,ko),warnings=[];
    if(ko!==null&&((spot>stop&&ko>=spot)||(spot<stop&&ko<=spot)))warnings.push("KO-Level liegt auf der falschen Seite des aktuellen Goldpreises.");
    if(koPct!==null&&koPct<2)warnings.push("KO-Abstand liegt unter 2%.");
    return {ok:true,maxLossUsd,approxNotionalUsd,approxNotionalEur,marginEur,stopDistance:dist,koDistancePct:koPct,warnings};
  }
  function evaluateProduct(p){
    const spot=n(p.spot),ko=n(p.ko),lev=Math.max(1,n(p.leverage)||1),spread=Math.max(0,n(p.spread)||0);
    const requested=String(p.direction||"NEUTRAL").toUpperCase(),productDirection=String(p.productDirection||directionOf(spot,ko)||"").toUpperCase(),reasons=[],warnings=[];
    if(spot===null||spot<=0)return {ok:false,fit:false,score:0,reasons:["Kein gültiger XAU/USD-Preis."],warnings:[]};
    if(!productDirection||!["LONG","SHORT"].includes(productDirection))reasons.push("Richtung des Produkts fehlt.");
    if(requested!=="NEUTRAL"&&productDirection&&requested!==productDirection)reasons.push("Produkt-Richtung passt nicht zum aktuellen Bob-Szenario.");
    if(ko===null)warnings.push("KO-Level fehlt – KO-Abstand kann nicht geprüft werden.");
    const koPct=koDistancePct(spot,ko);
    if(koPct!==null&&koPct<2)warnings.push("KO-Abstand unter 2%.");
    if(koPct!==null&&koPct<1)warnings.push("KO-Abstand unter 1% – sehr enger Puffer.");
    if(lev>10)warnings.push("Hebel über 10× – sehr hohe Empfindlichkeit.");
    if(spread>0)reasons.push("Spread wurde berücksichtigt.");
    let score=100;
    score-=reasons.filter(x=>x.includes("passt nicht")).length*55;
    score-=reasons.filter(x=>x.includes("fehlt")).length*15;
    if(koPct!==null&&koPct<2)score-=25;
    if(koPct!==null&&koPct<1)score-=20;
    if(lev>10)score-=15;
    if(spread>0)score-=Math.min(10,spread);
    const fit=score>=60&&!reasons.some(x=>x.includes("passt nicht"));
    return {ok:true,fit,score:Math.max(0,Math.round(score)),direction:productDirection,koDistancePct:koPct,leverage:lev,reasons,warnings};
  }
  window.BobDegiro={riskModel,koDistancePct,evaluateProduct};
})();