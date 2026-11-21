/*! QuickStatus.dev analytics v0.1.0 | MIT | github.com/QuickStatusHQ/quickstatus-analytics */
// Cookieless page views, custom events and engaged time. No cookies, no localStorage ids, no
// fingerprinting. Every field sent is listed in PAYLOAD.md; what the server does with it is in
// PRIVACY.md.
(function () {
  "use strict";

  var w = window;
  var d = document;
  var nav = navigator;
  var loc = location;
  var script = d.currentScript;
  var attr = function (name) {
    return script ? script.getAttribute("data-" + name) : null;
  };

  var site = attr("site");
  var api = attr("api") || "https://a.quickstatus.dev/e";
  var hashMode = attr("hash") === "true";
  var manual = attr("manual") === "true";
  var allowLocal = attr("local") === "true";
  var exclude = (attr("exclude") || "")
    .split(",")
    .map(function (p) { return p.trim(); })
    .filter(Boolean)
    .map(function (p) {
      // "/admin/*" style globs: * matches anything except "/", ** anything.
      var re = p.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*\*/g, "\u0000").replace(/\*/g, "[^/]*").replace(/\u0000/g, ".*");
      return new RegExp("^" + re + "$");
    });
  // Only these query parameters leave the browser; everything else in the URL query is dropped.
  var KEEP = /^(utm_(source|medium|campaign|content|term)|ref|source)$/;

  function ignored() {
    if (!site) return "missing data-site";
    if (loc.protocol === "file:") return "file";
    if (!allowLocal && /^(localhost|127(\.\d+){3}|\[::1\])$|\.(localhost|local|test)$/.test(loc.hostname)) return "localhost";
    if (nav.webdriver || w.__nightmare || w._phantom || w.Cypress) return "automation";
    try {
      if (w.localStorage && w.localStorage.getItem("qs_ignore") === "1") return "qs_ignore";
    } catch (e) { /* storage blocked */ }
    for (var i = 0; i < exclude.length; i++) if (exclude[i].test(loc.pathname)) return "excluded";
    return null;
  }

  function pageUrl() {
    var query = [];
    var search = loc.search.replace(/^\?/, "");
    if (search) {
      search.split("&").forEach(function (pair) {
        if (KEEP.test(pair.split("=")[0])) query.push(pair);
      });
    }
    var url = loc.protocol + "//" + loc.host + loc.pathname + (query.length ? "?" + query.join("&") : "");
    return hashMode && loc.hash ? url + loc.hash : url;
  }

  function send(body) {
    var data = JSON.stringify(body);
    // A string body goes out as text/plain, so there is no CORS preflight.
    if (nav.sendBeacon) {
      try {
        if (nav.sendBeacon(api, data)) return;
      } catch (e) { /* fall through */ }
    }
    if (w.fetch) {
      w.fetch(api, { method: "POST", body: data, keepalive: true, credentials: "omit", headers: { "Content-Type": "text/plain" } })
        .catch(function () {});
    }
  }

  function payload(name, extra) {
    var body = { s: site, n: name, u: pageUrl(), r: d.referrer || null, w: w.innerWidth };
    if (extra) for (var k in extra) if (Object.prototype.hasOwnProperty.call(extra, k)) body[k] = extra[k];
    return body;
  }

  // --- engaged time and scroll depth, per page ---------------------------------------------
  var engaged = 0;
  var visibleSince = d.visibilityState === "visible" ? Date.now() : 0;
  var maxScroll = 0;
  var currentPage = null;

  function scrollDepth() {
    var root = d.documentElement;
    var height = Math.max(root.scrollHeight, d.body ? d.body.scrollHeight : 0);
    if (!height) return 0;
    return Math.min(100, Math.round(((w.scrollY || root.scrollTop) + w.innerHeight) / height * 100));
  }

  function flushEngagement() {
    if (visibleSince) {
      engaged += Date.now() - visibleSince;
      visibleSince = d.visibilityState === "visible" ? Date.now() : 0;
    }
    if (currentPage && engaged >= 1000 && !ignored()) {
      send(payload("engage", { e: engaged, d: Math.max(maxScroll, scrollDepth()) }));
    }
    engaged = 0;
  }

  d.addEventListener("visibilitychange", function () {
    if (d.visibilityState === "hidden") flushEngagement();
    else visibleSince = Date.now();
  });
  w.addEventListener("pagehide", flushEngagement);
  w.addEventListener("scroll", function () {
    var depth = scrollDepth();
    if (depth > maxScroll) maxScroll = depth;
  }, { passive: true });

  // --- page views ------------------------------------------------------------------------
  function pageview() {
    var page = pageUrl();
    if (page === currentPage) return;
    if (currentPage) flushEngagement();
    currentPage = page;
    engaged = 0;
    maxScroll = 0;
    visibleSince = d.visibilityState === "visible" ? Date.now() : 0;
    if (ignored()) return;
    send(payload("pageview"));
  }

  function track(name, options) {
    if (!name || typeof name !== "string") return;
    if (name === "pageview") return pageview();
    if (ignored()) return;
    var extra = {};
    if (options && typeof options.value === "number" && isFinite(options.value)) {
      // Minor units (cents): qs("Purchase", { value: 49.0, currency: "EUR" }) sends 4900.
      extra.v = Math.round(options.value * 100);
      if (typeof options.currency === "string") extra.c = options.currency.toUpperCase();
    }
    send(payload(name, extra));
  }

  if (!manual) {
    var push = history.pushState;
    if (push) {
      history.pushState = function () {
        push.apply(this, arguments);
        pageview();
      };
      w.addEventListener("popstate", pageview);
    }
    if (hashMode) w.addEventListener("hashchange", pageview);
  }

  // Calls made before the script loaded: window.qs = window.qs || function () { (qs.q = qs.q || []).push(arguments) }
  var queued = (w.qs && w.qs.q) || [];
  w.qs = track;
  if (!manual) {
    if (d.visibilityState === "prerender") {
      d.addEventListener("visibilitychange", function once() {
        if (d.visibilityState === "visible") {
          d.removeEventListener("visibilitychange", once);
          pageview();
        }
      });
    } else {
      pageview();
    }
  }
  for (var i = 0; i < queued.length; i++) track.apply(null, queued[i]);

  var reason = ignored();
  if (reason && w.console && attr("debug") === "true") w.console.info("[qs] not counting: " + reason);
})();
