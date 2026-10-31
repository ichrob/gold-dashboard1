"use strict";
(() => {
  const byId = (id) => document.getElementById(id);
  const status = byId("status");
  const button = byId("refresh");
  const stateNames = Object.freeze({
    observed:"Zuletzt beobachtet", checked:"Zuletzt geprüft",
    paused:"Pausiert", unavailable:"Nicht verfügbar",
    unknown:"Unbekannt", ok:"OK", complete:"Vollständig (beobachtet)",
    incomplete:"Unvollständig", conflict:"Quellenkonflikt",
    "differences-explained":"Abweichungen dokumentiert"
  });
  const nameOf = (state) => stateNames[state] || "Unbestätigt";
  function show(data) {
    const jobs = Array.isArray(data.jobs) ? data.jobs : [];
    const job = (id) => jobs.find((entry) => entry && entry.id === id) || {};
    byId("simulation").textContent = nameOf(job("simulation").state) + " (kein Laufzeitbeweis)";
    byId("monitor").textContent = nameOf(job("background").state);
    const indexed = data.problemIndexFresh === true;
    const cases = Array.isArray(data.cases) ? data.cases : [];
    byId("problems").textContent = indexed ? String(cases.length) + " Problemgruppen erfasst" : "Problemstand nicht aktuell bestätigt";
    byId("products").textContent = nameOf(data.productStatus && data.productStatus.state) + " (keine Handelsfreigabe)";
    const list = byId("tests");
    list.replaceChildren();
    const tests = data.testOverview && Array.isArray(data.testOverview.items) ? data.testOverview.items : [];
    if (!tests.length) {
      const li = document.createElement("li");
      li.textContent = "Keine überprüfbaren Studiendaten verfügbar.";
      list.append(li);
    }
    for (const item of tests.slice(0, 30)) {
      if (!item || typeof item !== "object") continue;
      const li = document.createElement("li");
      const title = typeof item.label === "string" ? item.label.slice(0, 100) : "Unbenannter Test";
      const st = typeof item.state === "string" ? item.state : "unknown";
      li.textContent = title + " – " + nameOf(st) + (item.completed === true ? " (Abschluss berichtet)" : " (nicht als abgeschlossen bestätigt)");
      list.append(li);
    }
  }
  button.addEventListener("click", async () => {
    button.disabled = true;
    status.textContent = "Bestehende Bob-Statusdaten werden abgefragt …";
    try {
      const response = await fetch("/api/operations-summary", {credentials:"same-origin", cache:"no-store", headers:{"Accept":"application/json"}});
      if (!response.ok) throw new Error("HTTP " + response.status);
      const data = await response.json();
      if (!data || data.readOnly !== true || data.realOrders !== false) throw new Error("Unerwartetes Antwortformat");
      show(data);
      status.textContent = "Statusabfrage abgeschlossen. Nur vorhandene Beobachtungen; keine Reparatur oder Änderung ausgeführt.";
    } catch (error) {
      status.textContent = "Aktueller Status nicht verifizierbar (" + (error && error.message || "Verbindungsproblem") + ").";
      status.classList.add("error");
    } finally {
      button.disabled = false;
    }
  });
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/zentrale/sw.js", {scope:"/zentrale/"}).catch(() => {});
  }
})();
