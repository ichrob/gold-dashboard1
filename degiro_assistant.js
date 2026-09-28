/* Bob DEGIRO assistant: pure, deterministic calculations. No order execution. */
(function(){
  function num(v){const n=Number(v);return Number.isFinite(n)?n:null;}
  function koDistancePct(spot,ko){spot=num(spot);ko=num(ko);if(spot===null||ko===null||spot===0)return null;return Math.abs((spot-ko)/spot)*100;}
  function productRisk(p){
    const spot=num(p.spot), ko=num(p.ko), productPrice=num(p.productPrice), ratio=num(p.ratio)||1, spread=num(p.spread)||0;
    const fx=num(p.fx)||1, riskEur=num(p.riskEur), stop=num(p.stop);
    const distance=koDistancePct(spot,ko);
    const stopDistance=spot!==null&&stop!==null?Math.abs(spot-stop):null;
    const riskPerUnit=productPrice!==null?productPrice*ratio+spread:null;
    const units=riskPerUnit&&riskEur!==null?Math.floor(riskEur/(riskPerUnit*fx)):null;
    return {koDistancePct:distance,stopDistance,riskPerUnit,units};
  }
  function rankProducts(products,criteria){
    return (products||[]).map(p=>({...p,_risk:productRisk(p)})).sort((a,b)=>{
      const ak=a._risk.koDistancePct??-Infinity,bk=b._risk.koDistancePct??-Infinity;
      if(criteria&&criteria.minKoPct){const aa=ak>=criteria.minKoPct?1:0,bb=bk>=criteria.minKoPct?1:0;if(aa!==bb)return bb-aa;}
      const as=Number(a.spread);const bs=Number(b.spread);if(Number.isFinite(as)&&Number.isFinite(bs)&&as!==bs)return as-bs;
      return (Number(a.leverage)||0)-(Number(b.leverage)||0);
    });
  }
  window.BobDegiro={productRisk,rankProducts,koDistancePct};
})();
