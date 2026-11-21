// Runs src/qs.js in a fake browser and checks what it sends. `node --test`, no dependencies.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const SOURCE = readFileSync(new URL("../src/qs.js", import.meta.url), "utf8");
const SCHEMA = JSON.parse(readFileSync(new URL("../schema/event.v1.json", import.meta.url), "utf8"));

function browser({ url = "https://www.example.com/pricing?utm_source=hn&email=a@b.c#top", attrs = {}, referrer = "https://news.ycombinator.com/", webdriver = false, storage = {}, prerendering = false } = {}) {
  const sent = [];
  const listeners = {};
  const docListeners = {};
  const parsed = new URL(url);
  const location = {
    protocol: parsed.protocol, host: parsed.host, hostname: parsed.hostname,
    pathname: parsed.pathname, search: parsed.search, hash: parsed.hash,
  };
  const allAttrs = { site: "k3x9mpq2wa", ...attrs };
  const document = {
    currentScript: { getAttribute: (name) => allAttrs[name.replace(/^data-/, "")] ?? null },
    referrer,
    prerendering,
    visibilityState: prerendering ? "hidden" : "visible",
    documentElement: { scrollHeight: 2000, scrollTop: 0 },
    body: { scrollHeight: 2000 },
    addEventListener: (type, fn) => { (docListeners[type] ||= []).push(fn); },
    removeEventListener: () => {},
  };
  const history = {
    pushState(_state, _title, next) {
      const u = new URL(next, `${location.protocol}//${location.host}`);
      location.pathname = u.pathname; location.search = u.search; location.hash = u.hash;
    },
  };
  const window = {
    innerWidth: 1440, innerHeight: 800, scrollY: 0,
    localStorage: { getItem: (k) => storage[k] ?? null },
    addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); },
    console,
  };
  const navigator = {
    webdriver,
    sendBeacon: (endpoint, data) => { sent.push({ endpoint, body: JSON.parse(data) }); return true; },
  };
  const context = vm.createContext({ window, document, navigator, location, history, Date, Math, JSON, RegExp, Object, isFinite, URL });
  window.document = document;
  return {
    sent, window, document, location, history,
    run() { vm.runInContext(SOURCE, context); return this; },
    hide() { document.visibilityState = "hidden"; (docListeners.visibilitychange || []).forEach((fn) => fn()); },
    activate() {
      document.prerendering = false; document.visibilityState = "visible";
      (docListeners.prerenderingchange || []).forEach((fn) => fn());
    },
    docListeners,
    fire(type) { (listeners[type] || []).forEach((fn) => fn()); },
  };
}

function matchesSchema(body) {
  const allowed = new Set(Object.keys(SCHEMA.properties));
  for (const key of Object.keys(body)) assert.ok(allowed.has(key), `field ${key} is not in schema/event.v1.json`);
  for (const key of SCHEMA.required) assert.ok(key in body, `missing ${key}`);
}

test("sends one page view with only the allowed query parameters", () => {
  const b = browser().run();
  assert.equal(b.sent.length, 1);
  const { endpoint, body } = b.sent[0];
  assert.equal(endpoint, "https://a.quickstatus.dev/e");
  assert.deepEqual(body, { s: "k3x9mpq2wa", n: "pageview", u: "https://www.example.com/pricing?utm_source=hn", r: "https://news.ycombinator.com/", w: 1440 });
  matchesSchema(body);
});

test("data-api, hash mode and SPA navigations", () => {
  const b = browser({ attrs: { api: "https://stats.example.com/qs/e", hash: "true" } }).run();
  b.window.history = b.history;
  b.history.pushState({}, "", "/docs");
  b.window.qs("pageview");
  assert.equal(b.sent[0].endpoint, "https://stats.example.com/qs/e");
  // Hash mode sends "#/route" fragments only; "#top" is an anchor, not a route.
  assert.equal(b.sent[0].body.u, "https://www.example.com/pricing?utm_source=hn");
  assert.equal(b.sent.at(-1).body.u, "https://www.example.com/docs");
});

test("pushState counts a new page and not the same page twice", () => {
  const b = browser();
  b.run();
  // qs.js wrapped history.pushState on load.
  b.history.pushState({}, "", "/a");
  b.history.pushState({}, "", "/a");
  const views = b.sent.filter((s) => s.body.n === "pageview").map((s) => new URL(s.body.u).pathname);
  assert.deepEqual(views, ["/pricing", "/a"]);
});

test("custom events send value in minor units", () => {
  const b = browser().run();
  b.window.qs("Signup", { value: 49, currency: "eur" });
  const { body } = b.sent.at(-1);
  assert.equal(body.n, "Signup"); assert.equal(body.v, 4900); assert.equal(body.c, "EUR");
  matchesSchema(body);
});

test("queued calls made before load are replayed", () => {
  const b = browser();
  b.window.qs = function () { (b.window.qs.q ||= []).push(arguments); };
  b.window.qs("Download");
  b.run();
  assert.deepEqual(b.sent.map((s) => s.body.n), ["pageview", "Download"]);
});

test("engaged time is sent when the tab is hidden", () => {
  const b = browser();
  let now = 1_000_000;
  const realNow = Date.now;
  Date.now = () => now;
  try {
    b.run();
    now += 12_500;
    b.hide();
  } finally {
    Date.now = realNow;
  }
  const engage = b.sent.find((s) => s.body.n === "engage");
  assert.ok(engage);
  assert.equal(engage.body.e, 12_500);
  matchesSchema(engage.body);
});

for (const [name, options] of [
  ["localhost", { url: "http://localhost:3000/" }],
  ["*.test hosts", { url: "https://shop.test/" }],
  ["automation", { webdriver: true }],
  ["owner opt-out", { storage: { qs_ignore: "1" } }],
  ["excluded paths", { attrs: { exclude: "/pricing, /admin/**" } }],
  ["missing site", { attrs: { site: null } }],
]) {
  test(`does not count: ${name}`, () => {
    const b = browser(options).run();
    b.window.qs("Signup");
    assert.equal(b.sent.length, 0);
  });
}

test("data-local counts localhost for testing", () => {
  const b = browser({ url: "http://localhost:3000/", attrs: { local: "true" } }).run();
  assert.equal(b.sent.length, 1);
});

function withClock(fn) {
  let now = 1_000_000;
  const realNow = Date.now;
  Date.now = () => now;
  try { return fn((ms) => { now += ms; }); } finally { Date.now = realNow; }
}

test("engaged time on SPA navigation belongs to the page that was left", () => {
  for (const navigate of [
    (b) => b.history.pushState({}, "", "/docs"),
    (b) => { b.location.pathname = "/docs"; b.location.search = ""; b.fire("popstate"); },
  ]) {
    const b = browser({ url: "https://www.example.com/pricing" });
    withClock((tick) => { b.run(); tick(5000); navigate(b); });
    const seen = b.sent.map((x) => [x.body.n, new URL(x.body.u).pathname, x.body.e]);
    assert.deepEqual(seen, [["pageview", "/pricing", undefined], ["engage", "/pricing", 5000], ["pageview", "/docs", undefined]]);
  }
});

test("a prerendered page counts only when it is opened", () => {
  const b = browser({ prerendering: true }).run();
  assert.equal(b.sent.length, 0);
  b.activate();
  assert.deepEqual(b.sent.map((x) => x.body.n), ["pageview"]);
});

test("a bad currency or negative value is left out, and the event still counts", () => {
  const b = browser().run();
  for (const options of [{ value: 10, currency: "euro" }, { value: 10, currency: "€" }, { value: -5, currency: "EUR" }]) {
    b.window.qs("Purchase", options);
  }
  const events = b.sent.filter((x) => x.body.n === "Purchase").map((x) => [x.body.v, x.body.c]);
  assert.deepEqual(events, [[1000, undefined], [1000, undefined], [undefined, undefined]]);
});

test("the referrer is sent as its origin only", () => {
  const b = browser({ referrer: "https://www.example.com/account?email=a@b.c&token=SECRET" }).run();
  assert.equal(b.sent[0].body.r, "https://www.example.com/");
  assert.equal(browser({ referrer: "android-app://com.google.android.gm/x?y=1" }).run().sent[0].body.r, "android-app://com.google.android.gm/");
  assert.equal(browser({ referrer: "" }).run().sent[0].body.r, null);
});

test("long URLs are cut to 2000 characters, query first", () => {
  const long = "https://www.example.com/p?utm_source=" + "x".repeat(2100);
  const b = browser({ url: long }).run();
  assert.equal(b.sent[0].body.u, "https://www.example.com/p");
  const path = "https://www.example.com/" + "y".repeat(2100);
  assert.equal(browser({ url: path }).run().sent[0].body.u.length, 2000);
});

test("loading the script twice counts once", () => {
  const b = browser().run();
  b.run();
  b.history.pushState({}, "", "/a");
  assert.deepEqual(b.sent.map((x) => new URL(x.body.u).pathname), ["/pricing", "/a"]);
});

test("engage is reserved", () => {
  const b = browser().run();
  b.window.qs("engage");
  assert.equal(b.sent.length, 1);
});

test("hash mode sends the route with its query filtered, and no other fragment", () => {
  const urls = {
    "https://www.example.com/#/reset?token=SECRET&utm_source=x": "https://www.example.com/#/reset?utm_source=x",
    "https://www.example.com/#!/docs": "https://www.example.com/#!/docs",
    "https://www.example.com/#access_token=ya29.SECRET&token_type=Bearer": "https://www.example.com/",
    "https://www.example.com/pricing#faq": "https://www.example.com/pricing",
    "https://www.example.com/#/callback#access_token=SECRET": "https://www.example.com/#/callback",
    "https://www.example.com/#/a?utm_source=x#t=1": "https://www.example.com/#/a?utm_source=x",
  };
  for (const [url, sent] of Object.entries(urls)) {
    assert.equal(browser({ url, attrs: { hash: "true" } }).run().sent[0].body.u, sent);
  }
});

test("calls during prerender wait until the page is opened", () => {
  const b = browser({ prerendering: true });
  b.window.qs = function () { (b.window.qs.q ||= []).push(arguments); };
  b.window.qs("Purchase", { value: 10 });
  b.run();
  b.window.qs("Signup");
  assert.equal(b.sent.length, 0);
  b.activate();
  assert.deepEqual(b.sent.map((x) => x.body.n), ["pageview", "Purchase", "Signup"]);
});

test("navigation during prerender sends nothing; opening counts the current page once", () => {
  const b = browser({ prerendering: true }).run();
  b.history.pushState({}, "", "/y");
  b.location.pathname = "/z"; b.fire("popstate");
  assert.equal(b.sent.length, 0);
  b.activate();
  assert.deepEqual(b.sent.map((x) => [x.body.n, new URL(x.body.u).pathname]), [["pageview", "/z"]]);
});

test("event names are trimmed before the reserved check", () => {
  const b = browser().run();
  b.window.qs(" engage ");
  b.window.qs("  Sign   up ");
  assert.deepEqual(b.sent.map((x) => x.body.n), ["pageview", "Sign up"]);
});
