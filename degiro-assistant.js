(() => {
  "use strict";
  const $ = id => document.getElementById(id);
  const KEY = "bobDegiroAssistantV1";
  const state = (() => { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (_) { return {}; } })();

  const style = document.createElement("style");
  style.textContent = ".bob-dg-panel{margin-top:12px;padding:12px;border-radius:12px;background:#f7f7f8}.bob-dg-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}.bob-dg-chip{padding:9px;border-radius:10px;background:#fff;border:1px solid #e5e7eb}.bob-dg-chip b{display:block;margin-top:3px}.bob-dg-note{font-size:12px;color:#666;margin-top:8px}";
  document.head.appendChild(style);

  function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (_) {} }
  function num(id) { const v = parseFloat($(id)?.value); return Number.isFinite(v) ? v : null; }
  function price() { return Number.isFinite(window.lastPrice) && window.lastPrice > 0 ? window.lastPrice : num("tradePrice") || num("dgKo"); }

  function renderPanel() {
    const host = $("dgOut");
    if (!host || $("bobDegiroAssistantPanel")) return;
    const panel = document.createElement("div");
    panel.id = "bobDegiroAssistantPanel";
    panel.className = "bob-dg-panel";
    panel.innerHTML = `
      <b>DEGIRO-Assistent · Produktdaten</b>
      <div class="bob-dg-grid" style="margin-top:8px">
        <div class="bob-dg-chip">ISIN<b id="dgIsin">—</b></div>
        <div class="bob-dg-chip">Produktkurs<b id="dgProductPrice">—</b></div>
        <div class="bob-dg-chip">Bezugsverhältnis<b id="dgRatio">—</b></div>
        <div class="bob-dg-chip">Währung<b id="dgCurrency">—</b></div>
        <div class="bob-dg-chip">KO-Abstand<b id="dgKoDistance">—</b></div>
        <div class="bob-dg-chip">Max. Risiko<b id="dgMaxRisk">—</b></div>
      </div>
      <div class="grid" style="margin-top:8px">
        <div><label>ISIN</label><input id="dgIsinInput" placeholder="z. B. aus DEGIRO-Screenshot"></div>
        <div><label>Produktkurs</label><input id="dgProductInput" type="number" step=".0001"></div>
        <div><label>Bezugsverhältnis</label><input id="dgRatioInput" type="number" step=".0001" value="1"></div>
        <div><label>Produktwährung</label><select id="dgCurrencyInput"><option>EUR</option><option>USD</option><option>CHF</option></select></div>
      </div>
      <button id="dgSaveProduct" style="margin-top:8px">Produktdaten übernehmen</button>
      <div class="bob-dg-note">Bob verwendet nur Werte, die tatsächlich vorliegen. Fehlende ISIN, Produktkurs, Bezugsverhältnis, Spread oder Finanzierung werden nicht erfunden. Eine DEGIRO-Order wird nicht automatisch platziert.</div>`;
    host.appendChild(panel);

    $("dgIsinInput").value = state.isin || "";
    $("dgProductInput").value = state.productPrice || "";
    $("dgRatioInput").value = state.ratio || 1;
    $("dgCurrencyInput").value = state.currency || "EUR";
    $("dgSaveProduct").addEventListener("click", () => {
      state.isin = $("dgIsinInput").value.trim().toUpperCase();
      state.productPrice = num("dgProductInput");
      state.ratio = num("dgRatioInput") || 1;
      state.currency = $("dgCurrencyInput").value;
      save(); update();
      if (typeof window.calcDgTrade === "function") window.calcDgTrade();
    });
    update();
  }

  function update() {
    const p = price();
    const ko = num("dgKo");
    const dist = p && ko ? Math.abs(p - ko) : null;
    $("dgIsin") && ($("dgIsin").textContent = state.isin || "nicht hinterlegt");
    $("dgProductPrice") && ($("dgProductPrice").textContent = state.productPrice != null ? String(state.productPrice) : "nicht hinterlegt");
    $("dgRatio") && ($("dgRatio").textContent = state.ratio || "—");
    $("dgCurrency") && ($("dgCurrency").textContent = state.currency || "—");
    $("dgKoDistance") && ($("dgKoDistance").textContent = dist != null ? `${dist.toFixed(2)} USD/oz` : "nicht berechenbar");
    const account = num("account") || 0, risk = num("risk") || 0;
    $("dgMaxRisk") && ($("dgMaxRisk").textContent = account && risk ? `${(account * risk / 100).toFixed(2)} EUR` : "—");
  }

  function scoreProduct() {
    const lev = num("dgLev"), spread = num("dgSpread"), ko = num("dgKo"), p = price();
    const riskPct = num("risk") || num("risk2") || 1;
    const account = num("account") || 500;
    const maxRisk = account * riskPct / 100;
    const distance = p && ko ? Math.abs(p - ko) : null;
    const score = [];
    if (lev != null) score.push(lev >= 2 && lev <= 8 ? 2 : 0);
    if (spread != null) score.push(spread >= 0 ? (spread === 0 ? 1 : Math.max(0, 2 - spread)) : 0);
    if (distance != null && p) score.push(distance / p > 0.01 ? 2 : 0);
    const total = score.reduce((a,b) => a+b, 0);
    state.lastEvaluation = { timestamp: new Date().toISOString(), leverage: lev, spread, koDistance: distance, maxRisk, score: total };
    save(); update();
    const out = $("dgOut");
    if (out) out.insertAdjacentHTML("beforeend", `<div class="research" style="margin-top:10px"><b>Produktprüfung:</b> ${total.toFixed(1)} Kriterienpunkte erfasst. ${distance == null ? "KO-Abstand fehlt – keine belastbare Risikoaussage." : `KO-Abstand: ${distance.toFixed(2)} USD/oz.`} Maximal vorgesehenes Kontorisiko: ${maxRisk.toFixed(2)} EUR. Das ist eine regelbasierte Prüfung, keine Gewinnprognose.</div>`);
  }

  const oldCalc = window.calcDgTrade;
  window.calcDgTrade = function() {
    if (typeof oldCalc === "function") oldCalc();
    scoreProduct();
  };

  function init() { renderPanel(); update(); setInterval(update, 5000); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
