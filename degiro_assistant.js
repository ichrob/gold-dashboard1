/* Bob DEGIRO assistant: deterministic risk math only. No order execution and no product ranking. */
(function(){
  function n(v){const x=Number(v);return Number.isFinite(x)?x:null;}
  function koDistancePct(spot,ko){spot=n(spot);ko=n(ko);if(spot===null||ko===null||spot<=0)return null;return Math.abs((spot-ko)/spot)*100;}
  function riskModel(p){
    const spot=n(p.spot),stop=n(p.stop),riskEur=n(p.riskEur),fx=n(p.fxUsdEur),lev=Math.max(1,n(p.leverage)||1);
    if(spot===null||stop===null||riskEur===null||riskEur<=0)return {ok:false,reason:"Ungültige Eingabedaten für Risiko."};
    if(fx===null||fx<=0)return {ok:false,reason:"Keine gültige USD→EUR-FX-Rate."};
    const dist=Math.abs(spot-stop);
    if(dist<=0)return {ok:false,reason:"Stop-Distanz ist null."};
    const maxLossUsd=riskEur/fx;
    const approxNotionalUsd=maxLossUsd/(dist/spot);
    const approxNotionalEur=approxNotionalUsd*fx;
    const marginEur=approxNotionalEur/lev;
    const ko=n(p.ko);
    const koPct=koDistancePct(spot,ko);
    const warnings=[];
    if(ko!==null && ((spot>stop&&ko>=spot)||(spot<stop&&ko<=spot)))warnings.push("KO-Level liegt auf der falschen Seite des aktuellen Goldpreises.");
    if(koPct!==null&&koPct<2)warnings.push("KO-Abstand liegt unter 2%.");
    return {ok:true,maxLossUsd,approxNotionalUsd,approxNotionalEur,marginEur,stopDistance:dist,koDistancePct:koPct,warnings};
  }
  window.BobDegiro={riskModel,koDistancePct};
})();