"use strict";

// Run with Node.js: node work/tests/test_web.cjs
// WEB_ROOT may point to the web package inside the final deliverable.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const webRoot = process.env.WEB_ROOT || path.resolve(__dirname, "../web");
const appPath = path.join(webRoot, "app.js");
const api = require(appPath);
let checks = 0;
function eq(actual, expected, message) { assert.deepEqual(actual, expected, message); checks++; }
function ok(value, message) { assert.ok(value, message); checks++; }

const target = api.DEFAULT_TARGET_MS;
eq(new Date(target).toISOString(), "2026-11-18T16:00:00.000Z", "PS Store UTC time converts to Beijing midnight");
eq(new Date(api.WAIT_START).toISOString(), "2023-12-04T23:00:00.000Z", "progress starts at the actual early trailer premiere");
for (const value of ["2026-11-19", "2026-11-19 00:00:00", "2026/11/19 00:00", "2026-11-18T16:00Z", "2026-11-19T00:00:00+08:00"]) {
  eq(api.parseTarget(value), target, `timezone-independent parsing: ${value}`);
}
for (const value of ["", "invalid", "2026-02-30", "2026-01-01 24:00", "2026-00-01", "2026-13-01", "2026-11-19T00:60:00+08:00"]) {
  eq(api.parseTarget(value), target, `invalid or empty input restores the default: ${value}`);
  eq(api.parseTarget(value, null), null, "optional null fallback distinguishes invalid input from a valid custom target");
}
eq(api.parseTarget("2028-02-29T00:00:00+08:00"), Date.parse("2028-02-28T16:00:00Z"), "valid leap day");
eq(api.calculateState(target - 1).totalSeconds, 1, "no premature zero in the final millisecond");
eq(api.calculateState(target).released, true, "exact target reaches completion");
eq([api.calculateState(target).days, api.calculateState(target).seconds], [0, 0]);
eq(api.calculateState(target + 50000).progress, 1, "progress cannot exceed 100%");
eq(api.calculateState(api.WAIT_START - 1).progress, 0, "progress cannot become negative");
eq(api.calculateState(target - 86400000).days, 1);
eq(api.calculateState(target).clockTime, "00:00");
eq(api.calculateState(target).clockDate, "11月19日 星期四");
eq(api.calculateState(target - 1000).clockTime, "23:59");
eq(api.calculateState(target - 1000).clockDate, "11月18日 星期三");
eq(api.parseAccent("1 0.5 0"), "rgb(255, 128, 0)");
eq(api.parseAccent("bad color"), null);

function createBrowser() {
  const nodes = {};
  const classes = new Map();
  const events = new Map();
  const pendingTimers = new Map();
  let timerId = 0;
  let now = Date.parse("2026-10-15T13:00:00Z");
  class FixedDate extends Date { static now() { return now; } }
  const fakeDocument = {
    readyState: "loading", hidden: false,
    getElementById(id) {
      return nodes[id] ||= { style: {}, setAttribute(key, value) { this[key] = value; } };
    },
    documentElement: { style: { setProperty(key, value) { this[key] = value; } } },
    body: { classList: { toggle(key, value) { classes.set(key, value); } } },
    addEventListener(name, callback) { events.set(name, callback); }
  };
  const fakeWindow = {
    setTimeout(callback, delay) { pendingTimers.set(++timerId, { callback, delay }); return timerId; },
    clearTimeout(id) { pendingTimers.delete(id); }
  };
  vm.runInNewContext(fs.readFileSync(appPath, "utf8"), {
    window: fakeWindow, document: fakeDocument, Date: FixedDate, Math, String, Number, TypeError,
    module: { exports: {} }
  });
  return {
    nodes, classes, events, pendingTimers, document: fakeDocument,
    listener: fakeWindow.wallpaperPropertyListener,
    initialize() { events.get("DOMContentLoaded")(); },
    setNow(value) { now = value; }
  };
}

const browser = createBrowser();
// Wallpaper Engine may deliver the first properties before DOMContentLoaded.
browser.listener.applyUserProperties({
  effects: { value: false }, showclock: { value: false }, accent: { value: "0.2 0.4 1" },
  textscale: { value: 90 }, targetdate: { value: "2026-12-01 08:30" }
});
browser.initialize();
eq(browser.classes.get("effects-off"), true);
eq(browser.nodes.clock.hidden, true);
eq(browser.document.documentElement.style["--text-scale"], "0.9");
eq(browser.document.documentElement.style["--accent"], "rgb(51, 102, 255)");
eq(browser.nodes["target-note"].textContent, "自定义目标 · 北京时间", "custom properties received before initialization persist");
eq(browser.nodes["target-date"].textContent, "2026年12月1日 — 08:30 GMT+8");
eq(browser.nodes["clock-time"].textContent, "21:00", "clock remains in Beijing");
eq(browser.pendingTimers.size, 1, "one timer only");
browser.listener.setPaused(true);
eq(browser.classes.get("is-paused"), true);
eq(browser.pendingTimers.size, 0, "host pause cancels timer");
browser.listener.applyGeneralProperties({ isPaused: false });
eq(browser.classes.get("is-paused"), false);
eq(browser.pendingTimers.size, 1, "resume schedules one timer");
browser.document.hidden = true;
browser.events.get("visibilitychange")();
eq(browser.pendingTimers.size, 0, "hidden document suspends timer");
browser.document.hidden = false;
browser.events.get("visibilitychange")();
eq(browser.pendingTimers.size, 1);
browser.listener.applyUserProperties({ targetdate: { value: "" } });
eq(browser.nodes["target-note"].textContent, "港区 PS5 · PS Store 列示时间");
browser.listener.applyUserProperties({ targetdate: { value: "2026-02-30" } });
eq(browser.nodes["target-note"].textContent, "港区 PS5 · PS Store 列示时间", "invalid custom input restores source note");
browser.listener.applyUserProperties({ targetdate: { value: api.DEFAULT_TARGET } });
eq(browser.nodes["target-note"].textContent, "自定义目标 · 北京时间", "explicitly setting the default date is still a valid custom target");
browser.setNow(target);
browser.listener.applyUserProperties({ targetdate: { value: "" } });
eq(browser.nodes.intro.textContent, "欢迎来到莱昂尼达");
eq(browser.nodes["target-note"].textContent, "计划发售日已到 · 以商店实际解锁为准");
eq(browser.nodes["progress-fill"].style.width, "100%");

const pausedBeforeInit = createBrowser();
pausedBeforeInit.listener.setPaused(true);
pausedBeforeInit.initialize();
eq(pausedBeforeInit.classes.get("is-paused"), true, "host pause before DOM initialization persists");
eq(pausedBeforeInit.pendingTimers.size, 0);

// Static integration checks catch mismatched DOM IDs and missing local references.
const html = fs.readFileSync(path.join(webRoot, "index.html"), "utf8");
for (const id of ["days", "hours", "minutes", "seconds", "clock", "clock-time", "clock-date", "intro", "progress", "progress-fill", "progress-text", "target-date", "target-note"]) {
  eq((html.match(new RegExp(`id="${id}"`, "g")) || []).length, 1, `DOM id must appear once: ${id}`);
}
const project = JSON.parse(fs.readFileSync(path.join(webRoot, "project.json"), "utf8"));
eq(project.type, "web");
ok(fs.existsSync(path.join(webRoot, project.file)), "project points to an existing entry point");
for (const key of ["effects", "showclock", "accent", "textscale", "targetdate"]) ok(project.general.properties[key], `Wallpaper Engine property exists: ${key}`);
ok(!/<script[^>]+src=["']https?:/i.test(html), "scripts are local and offline");
console.log(`PASS: ${checks} web countdown, Wallpaper Engine, and static integration assertions`);
