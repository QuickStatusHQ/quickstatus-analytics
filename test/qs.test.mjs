// Runs src/qs.js in a fake browser and checks what it sends. `node --test`, no dependencies.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const SOURCE = readFileSync(new URL("../src/qs.js", import.meta.url), "utf8");
const SCHEMA = JSON.parse(readFileSync(new URL("../schema/event.v1.json", import.meta.url), "utf8"));

function browser({ url = "https://www.example.com/pricing?utm_source=hn&email=a@b.c#top", attrs = {}, referrer = "https://news.ycombinator.com/", webdriver = false, storage = {} } = {}) {
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
    visibilityState: "visible",
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
  assert.equal(b.sent[0].body.u, "https://www.example.com/pricing?utm_source=hn#top");
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
