"use strict";
(() => {
  const byId = (id) => document.getElementById(id);
  const status = byId("status");
  const button = byId("refresh");
  let snapshot = null;
  const stateNames = Object.freeze({
    observed:"Zuletzt beobachtet", checked:"Zuletzt geprüft", paused:"Pausiert",
    unavailable:"Nicht verfügbar", unknown:"Unbekannt", ok:"OK",
    complete:"Vollständig (beobachtet)", incomplete:"Unvollständig", conflict:"Quellenkonflikt",
    "differences-explained":"Abweichungen dokumentiert", "in-progress":"In Bearbeitung",
    running:"Läuft (zuletzt gemeldet)", waiting:"Wartet", idle:"Kein Leselauf gemeldet", testing:"In Prüfung", "needs-user":"Deine Hilfe benötigt", blocked:"Nachweis fehlt",
    review:"Prüfung ausstehend", new:"Offen"
  });
  const nameOf = (state) => stateNames[state] || "Unbestätigt";
  function clock(value) {
    if (value === null || value === undefined || value === "") return "Zeitpunkt unbekannt";
    const date = new Date(typeof value === "number" && value < 1e11 ? value * 1000 : value);
    return Number.isFinite(date.getTime()) ? date.toLocaleString("de-CH", {timeZone:"Europe/Zurich"}) + " (Schweiz)" : "Zeitpunkt unbekannt";
  }
  function bytes(value) {
    return typeof value === "number" && Number.isFinite(value) && value >= 0 ?
      (value / 1048576).toLocaleString("de-CH", {maximumFractionDigits:1}) + " MiB" : "Nicht gemessen";
  }
  function list(id, rows, empty, render) {
    const target = byId(id); target.replaceChildren();
    for (const row of (rows.length ? rows : [null])) {
      const li = document.createElement("li"); li.textContent = row === null ? empty : render(row); target.append(li);
    }
  }
  function reset() {
    snapshot = null;
    list("job-times", [], "Keine aktuelle Abfrage verfügbar.", () => "");
    for (const id of ["simulation", "monitor", "problems", "products", "research", "disk", "database", "archive", "problem-age", "overall", "open-count", "help-count", "next-action", "phone-state", "phone-step", "phone-progress", "phone-import", "phone-details", "phone-ocr"]) byId(id).textContent = "Nicht aktuell bestätigt";
    byId("observed").textContent = "Datenstand unbekannt";
    list("tests", [], "Keine aktuelle Abfrage verfügbar.", () => "");
    list("cases", [], "Keine aktuelle Abfrage verfügbar.", () => "");
  }
  function show(data) {
    snapshot = data;
    const jobs = Array.isArray(data.jobs) ? data.jobs : [];
    const job = (id) => jobs.find((entry) => entry && entry.id === id) || {};
    byId("observed").textContent = "Statusaufnahme: " + clock(data.observedAt);
    byId("simulation").textContent = nameOf(job("simulation").state) + " · kein Laufzeitbeweis";
    byId("monitor").textContent = nameOf(job("background").state) + " · " + clock(job("background").lastObservedAt);
    byId("research").textContent = nameOf(job("research").state) + " · " + clock(job("research").lastObservedAt);
    const indexed = data.problemIndexFresh === true;
    const cases = (Array.isArray(data.cases) ? data.cases : []).filter(x => x && typeof x === "object").slice(0,100);
    byId("problems").textContent = indexed ? cases.length + " Problemgruppen erfasst" : "Problemstand nicht aktuell bestätigt";
    byId("problem-age").textContent = indexed ? "Aktuell erfasste Problemgruppen; Reparaturerfolg separat prüfen." : "Problemindex veraltet oder unbekannt; Einträge sind keine aktuelle Entwarnung.";
    const help = indexed ? cases.filter(item => item.state === "needs-user").length : null;
    byId("open-count").textContent = indexed ? String(cases.length) : "Unbekannt";
    byId("help-count").textContent = help === null ? "Unbekannt" : help ? String(help) + " Fälle" : "Keine Anforderung im aktuellen Index";
    const background = job("background");
    byId("overall").textContent = background.state === "observed" ? "Letzte Überwachung bestätigt" : background.state === "paused" ? "Überwachung pausiert" : "Überwachung nicht bestätigt";
    byId("next-action").textContent = !indexed ? "Problemstand nicht aktuell bestätigt. Bei Bedarf erneut aktualisieren." : help ? "Öffne Probleme & Wartung: Dort ist deine Hilfe angefordert." : cases.length ? "Offene Fälle unter Probleme & Wartung ansehen." : "Keine offenen Problemgruppen erfasst. Das bestätigt nicht automatisch alle Funktionen.";
    list("job-times", jobs.filter(j => j && typeof j === "object").slice(0,10), "Keine Ausführungsnachweise verfügbar.", j =>
      String(j.label || "Dienst").slice(0,80) + ": " + nameOf(j.state) + " · Letzter Erfolg: " + clock(j.lastSuccessAt));
    if (!byId("maintenance").hidden) list("cases", cases, indexed ? "Keine Problemgruppen im aktuellen Index erfasst." : "Keine aktuellen Problemnachweise verfügbar.", item =>
      String(item.code || "Unbekannter Fall").slice(0,120) + " · " + nameOf(item.state) + " · Reparatur nicht bestätigt");
    const phone = data.phone || {};
    byId("phone-state").textContent = "Bob Handy: " + nameOf(phone.state) + " · Version " + (Number.isInteger(phone.appVersion) ? phone.appVersion : "unbekannt");
    byId("phone-step").textContent = "Letzter gemeldeter Schritt: " + (phone.step || "Unbekannt") + " · " + clock(phone.stepAt) + ". " + (phone.nextAction || "Noch keine belastbare Handy-Meldung.");
    byId("phone-progress").textContent = Number.isInteger(phone.requested) && Number.isInteger(phone.complete) ?
      "Letzter gespeicherter Leselauf: " + phone.complete + " von " + phone.requested + " vollständig erfasst, " + (phone.partial || 0) + " teilweise · " + clock(phone.runAt) + ". Kein Live-Fortschritt und keine Handelsfreigabe." : "Noch kein auswertbarer Leselauf gemeldet.";
    byId("phone-import").textContent = "Letzter Importstatus: " + (phone.importState || "Unbekannt") + " · " + clock(phone.importAt) + ". Letzte erfolgreiche Listenübernahme im verfügbaren Verlauf: " + clock(phone.lastSuccessfulImportAt);
    byId("phone-details").textContent = "Meldung vom Handy: " + clock(phone.observedAt) + " · Serverempfang: " + clock(phone.receivedAt) + (phone.multipleDevices ? ". Mehrere Geräte gekoppelt; gezeigt wird das zuletzt meldende Gerät." : "") + " Gespeicherte Leseläufe und Listenimporte werden separat angezeigt; eine Zuordnung zum aktuellen Gerät ist hier nicht bestätigt.";
    const count = value => Number.isInteger(value) && value >= 0 ? String(value) : "unbekannt";
    byId("phone-ocr").textContent = "Letzte Listenübertragung: " + count(phone.localOcrImages) + " Bilder mit lokaler OCR, " + count(phone.appTextImages) + " mit App-Text, " + count(phone.imageOnly) + " ohne Textbeilage. Dies belegt die mitgelieferten Daten, nicht erfolgreiche Erkennung oder tatsächlich ausgeführte Server-OCR.";
    byId("products").textContent = nameOf(data.productStatus && data.productStatus.state) + " · keine Handelsfreigabe";
    const tests = data.testOverview && Array.isArray(data.testOverview.items) ? data.testOverview.items.filter(x => x && typeof x === "object").slice(0,30) : [];
    if (!byId("studies").hidden) list("tests", tests, "Keine überprüfbaren Studiendaten verfügbar.", item =>
      (typeof item.label === "string" ? item.label.slice(0,100) : "Unbenannter Test") + " – " + nameOf(item.state) + (item.completed === true ? " (Abschluss berichtet)" : " (Abschluss nicht bestätigt)"));
    const storage = data.storage || {};
    byId("disk").textContent = bytes(storage.diskUsedBytes) + " · Messung: " + clock(storage.diskObservedAt);
    byId("database").textContent = bytes(storage.databaseBytes) + " · Messung: " + clock(storage.databaseObservedAt);
    byId("archive").textContent = (storage.restoreVerified === true ? "Gespeicherter Wiederherstellungsnachweis" : "Wiederherstellung nicht bestätigt") + " · " + clock(storage.archiveVerifiedAt);
  }
  const panels = Array.from(document.querySelectorAll("[data-panel]"));
  function navigate(focus) {
    const key = location.hash.slice(1);
    const selected = panels.find(panel => panel.id === key) || byId("overview");
    for (const panel of panels) panel.hidden = panel !== selected;
    for (const link of document.querySelectorAll("nav a")) {
      if (link.hash === "#" + selected.id) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
    if (snapshot) show(snapshot);
    if (focus) selected.querySelector("h2").focus();
  }
  window.addEventListener("hashchange", () => navigate(true)); navigate(false);
  async function refresh() {
    if (button.disabled) return;
    button.disabled = true; status.classList.remove("error"); reset();
    status.textContent = "Vorhandene Bob-Statusdaten werden abgefragt …";
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch("/api/operations-summary", {signal:controller.signal, credentials:"same-origin", cache:"no-store", headers:{"Accept":"application/json"}});
      if (!response.ok) throw new Error("HTTP " + response.status);
      const data = await response.json();
      if (!data || data.readOnly !== true || data.realOrders !== false) throw new Error("Unerwartetes Antwortformat");
      show(data); status.textContent = "Status geladen. Alle Bereiche verwenden dieselbe Aufnahme.";
    } catch (error) {
      reset(); status.textContent = "Status nicht verifizierbar. Bitte erneut aktualisieren."; status.classList.add("error");
    } finally { clearTimeout(timeout); button.disabled = false; }
  }
  button.addEventListener("click", refresh);
  refresh();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/zentrale/sw.js", {scope:"/zentrale/"}).catch(() => {});
})();
