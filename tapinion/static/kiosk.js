// Copyright (C) 2026 Markus Wilhelm, mw-research
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Kiosk helpers: keeps votes when the network drops (e.g. laptop Wi-Fi) and sends them
// later with their original time; never gets stuck on a screen when the server is away;
// keeps the screen awake where the browser allows it.
(function () {
  "use strict";
  const shell = document.querySelector(".kiosk-shell[data-token]");
  if (!shell) return;
  const token = shell.dataset.token;
  const KEY = "tapinion-queue-" + token;
  const RESUME = "tapinion-resume-" + token;
  // Device key: votes are accepted with it even after days without a connection, and the
  // device can continue the kiosk after a restart without the PIN.
  let device = shell.dataset.device || "";
  try {
    if (device) localStorage.setItem(RESUME, device);
    else device = localStorage.getItem(RESUME) || "";
  } catch (e) { /* storage blocked */ }
  const stage = document.getElementById("stage");
  const pending = document.querySelector(".kiosk-pending");
  let voteHtml = null;     // last voting form, to restore it without the server
  let lastValue = null;    // value of the last tapped button
  let flushing = false;

  function remember() {
    if (stage.querySelector("form.vote")) voteHtml = stage.innerHTML;
  }
  function restore() {
    if (!voteHtml) return;
    stage.innerHTML = voteHtml;
    stage.querySelectorAll("button").forEach((b) => b.removeAttribute("disabled"));
    htmx.process(stage);
  }
  function load() {
    try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (e) { return []; }
  }
  function save(items) {
    try { localStorage.setItem(KEY, JSON.stringify(items)); } catch (e) { /* storage full or blocked */ }
    if (pending) {
      pending.hidden = items.length === 0;
      pending.textContent = items.length ? "⟳ " + items.length : "";
    }
  }
  function localTime() {
    const d = new Date(), p = (n) => String(n).padStart(2, "0");
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) +
      "T" + p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds());
  }

  async function flush() {
    if (flushing) return;
    flushing = true;
    try {
      let items = load();
      while (items.length) {
        const item = items[0];
        const body = new FormData();
        body.append("value", item.value);
        body.append("lang", item.lang);
        body.append("ts", item.ts);
        body.append("queued", "1");
        if (item.device || device) body.append("device", item.device || device);
        let res;
        try {
          res = await fetch("/k/" + token + "/vote", {
            method: "POST", body: body, credentials: "same-origin",
            headers: (item.device || device) ? { "X-Kiosk-Device": item.device || device } : {},
          });
        } catch (e) {
          break; // still offline
        }
        if (res.status >= 500) break;
        items.shift(); // stored, or rejected for good (4xx): drop it either way
        save(items);
      }
    } finally {
      flushing = false;
    }
  }

  document.addEventListener("click", function (ev) {
    const btn = ev.target.closest && ev.target.closest("form.vote button[name=value]");
    if (btn) lastValue = btn.value;
  }, true);

  document.body.addEventListener("htmx:afterSwap", remember);
  document.body.addEventListener("htmx:configRequest", function (ev) {
    if (device && ev.detail.path.indexOf("/k/") === 0) ev.detail.headers["X-Kiosk-Device"] = device;
  });

  document.body.addEventListener("htmx:sendError", function (ev) {
    const elt = ev.detail.elt;
    const form = elt.closest && elt.closest("form.vote");
    if (form && lastValue !== null) {
      // the vote did not reach the server: keep it and thank the visitor anyway
      const items = load();
      items.push({ value: String(lastValue), lang: form.querySelector("[name=lang]").value, ts: localTime(), device: device });
      lastValue = null;
      save(items);
      const tpl = document.getElementById("thanks-tpl");
      if (tpl) stage.innerHTML = tpl.innerHTML;
      setTimeout(restore, 4000);
    } else if (stage.contains(elt) || elt === stage) {
      // e.g. the voting form could not be reloaded after the thank-you screen
      setTimeout(restore, 500);
    }
  });

  // Heartbeat: the device list shows which kiosks are alive. A device switched off by an
  // administrator goes back to the PIN screen.
  async function ping() {
    try {
      const res = await fetch("/k/" + token + "/ping", {
        method: "POST", credentials: "same-origin", headers: device ? { "X-Kiosk-Device": device } : {},
      });
      if (res.status === 403 && load().length === 0) {
        try { localStorage.removeItem(RESUME); } catch (e) {}
        location.reload();
      }
    } catch (e) { /* offline */ }
  }
  setInterval(ping, 60000);

  window.addEventListener("online", flush);
  setInterval(flush, 15000);
  remember();
  save(load());
  flush();

  const full = document.querySelector(".kiosk-full");
  if (full && document.fullscreenEnabled && !window.matchMedia("(display-mode: fullscreen)").matches) full.hidden = false;
  document.addEventListener("fullscreenchange", function () { if (full) full.classList.toggle("on", !!document.fullscreenElement); });

  // Keep the screen on (HTTPS or localhost only; the Android app does this natively).
  async function wake() {
    try { if ("wakeLock" in navigator) await navigator.wakeLock.request("screen"); } catch (e) { /* not allowed */ }
  }
  document.addEventListener("visibilitychange", function () { if (!document.hidden) wake(); });
  wake();
})();
