// Copyright (C) 2026 Markus Wilhelm, mw-research
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// window.TapinionApp for the offline pages (kiosk.html, results.html, shared with Android).
// The pages call the bridge synchronously; WKWebView only talks to the app asynchronously.
// So the app injects the event data before the page loads (window.__tapinionData), answers
// from it here and reports actions (rating, start, exit) to the app.
(function () {
  "use strict";
  var data = window.__tapinionData || { bundle: "{}", votes: [] };
  var votes = data.votes || [];
  function post(message) {
    try { window.webkit.messageHandlers.tapinion.postMessage(message); } catch (e) { /* not in the app */ }
  }

  function sha256(text) {
    var bytes = unescape(encodeURIComponent(text));
    var K = [
      0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
      0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
      0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
      0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
      0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
      0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
      0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
      0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2];
    var H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19];
    var l = bytes.length, n = ((l + 8) >> 6) + 1, words = [], i, j;
    for (i = 0; i < n * 16; i++) words[i] = 0;
    for (i = 0; i < l; i++) words[i >> 2] |= bytes.charCodeAt(i) << (24 - (i % 4) * 8);
    words[l >> 2] |= 0x80 << (24 - (l % 4) * 8);
    words[n * 16 - 1] = l * 8;
    var w = new Array(64);
    for (j = 0; j < n * 16; j += 16) {
      var a = H[0], b = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7];
      for (i = 0; i < 64; i++) {
        if (i < 16) {
          w[i] = words[j + i];
        } else {
          var x = w[i - 15], y = w[i - 2];
          var s0 = ((x >>> 7) | (x << 25)) ^ ((x >>> 18) | (x << 14)) ^ (x >>> 3);
          var s1 = ((y >>> 17) | (y << 15)) ^ ((y >>> 19) | (y << 13)) ^ (y >>> 10);
          w[i] = (w[i - 16] + s0 + w[i - 7] + s1) | 0;
        }
        var S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
        var t1 = (h + S1 + ((e & f) ^ (~e & g)) + K[i] + w[i]) | 0;
        var S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
        var t2 = (S0 + ((a & b) ^ (a & c) ^ (b & c))) | 0;
        h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
      }
      H[0] = (H[0] + a) | 0; H[1] = (H[1] + b) | 0; H[2] = (H[2] + c) | 0; H[3] = (H[3] + d) | 0;
      H[4] = (H[4] + e) | 0; H[5] = (H[5] + f) | 0; H[6] = (H[6] + g) | 0; H[7] = (H[7] + h) | 0;
    }
    var hex = "";
    for (i = 0; i < 8; i++) hex += ("00000000" + (H[i] >>> 0).toString(16)).slice(-8);
    return hex;
  }

  window.__tapinionSha256 = sha256;
  // after a sync the app hands over the new state of the ratings (sent or not)
  window.__tapinionSetVotes = function (v) { votes = v || []; };

  window.TapinionApp = {
    bundle: function () { return data.bundle; },
    votes: function () { return JSON.stringify(votes); },
    pending: function () { return votes.filter(function (v) { return !v.sent; }).length; },
    checkPin: function (token, pin) {
      try {
        var p = JSON.parse(data.bundle).event.pin || {};
        return !!(p.sha256 && pin) && sha256((p.salt || "") + pin) === p.sha256;
      } catch (e) { return false; }
    },
    vote: function (token, value, lang) {
      votes.push({ value: value, lang: lang, sent: false });
      post({ op: "vote", token: token, value: value, lang: lang });
    },
    kioskStarted: function (token) { post({ op: "kioskStarted", token: token }); },
    exitKiosk: function (token) { post({ op: "exitKiosk", token: token }); },
    close: function () { post({ op: "close" }); }
  };
})();
