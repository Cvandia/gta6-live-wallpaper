"use strict";

// Node.js assertions for the cursor effect's behavior and the wallpaper lifecycle.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const webRoot = process.env.WEB_ROOT || path.resolve(__dirname, "../web");
const appPath = path.join(webRoot, "app.js");
const api = require(appPath);
let checks = 0;
function eq(value, expected, message) { assert.deepEqual(value, expected, message); checks++; }
function ok(value, message) { assert.ok(value, message); checks++; }
function near(value, expected, message) { ok(Math.abs(value - expected) < .000001, message); }

function browser(systemReduced = false) {
  const nodes = {}, styles = {}, classes = new Map(), events = new Map(), rootEvents = new Map();
  const timers = new Map(), frames = new Map(), images = [];
  let nextId = 0, clock = 0, now = Date.parse("2026-10-15T13:00:00Z"), mediaListener;
  class FixedDate extends Date { static now() { return now; } }
  class FakeImage {
    set src(source) { this.source = source; images.push(this); }
  }
  const document = {
    readyState: "loading", hidden: false,
    getElementById(id) { return nodes[id] ||= { style: {}, setAttribute(name, value) { this[name] = value; } }; },
    documentElement: { style: { setProperty(name, value) { styles[name] = value; } } },
    body: { classList: { toggle(name, value) { classes.set(name, value); } } },
    addEventListener(name, callback) { events.set(name, callback); }
  };
  const window = {
    innerWidth: 1920, Image: FakeImage,
    setTimeout(callback, delay) { timers.set(++nextId, { callback, delay }); return nextId; },
    clearTimeout(id) { timers.delete(id); },
    requestAnimationFrame(callback) { frames.set(++nextId, callback); return nextId; },
    cancelAnimationFrame(id) { frames.delete(id); },
    addEventListener(name, callback) { rootEvents.set(name, callback); },
    matchMedia() { return { matches: systemReduced, addEventListener(name, callback) { mediaListener = callback; } }; }
  };
  vm.runInNewContext(fs.readFileSync(appPath, "utf8"), { window, document, Date: FixedDate, module: { exports: {} } });
  return {
    window, document, nodes, styles, classes, timers, frames, images,
    listener: window.wallpaperPropertyListener,
    initialize() { events.get("DOMContentLoaded")(); },
    move(x) { events.get("mousemove")({ clientX: x }); },
    leave() { events.get("mouseleave")(); },
    resize(width) { window.innerWidth = width; rootEvents.get("resize")(); },
    hidden(value) { document.hidden = value; events.get("visibilitychange")(); },
    reduce(value) { mediaListener({ matches: value }); },
    now(value) { now = value; },
    frame(elapsed = 1000 / 60) {
      clock += elapsed;
      const callbacks = [...frames.values()];
      frames.clear();
      callbacks.forEach(callback => callback(clock));
    },
    settle() { for (let i = 0; i < 250 && frames.size; i++) this.frame(); },
    async load(width = 3840, height = 2160, mismatch = false) {
      images.forEach((image, index) => { image.naturalWidth = mismatch && index === 1 ? width * .9 : width; image.naturalHeight = height; image.onload(); });
      await Promise.resolve(); await Promise.resolve();
    }
  };
}

async function main() {
  eq(api.pointerRatio(0, 1920), -1);
  eq(api.pointerRatio(960, 1920), 0);
  eq(api.pointerRatio(1920, 1920), 1);
  eq(api.pointerRatio(5000, 1920), 1, "cursor values outside the viewport are clamped");
  eq(api.pointerRatio(NaN, 1920), 0);
  eq(api.pointerRatio(100, 0), 0, "a minimized viewport is safe");
  eq(api.parallaxOffset(-1, 1920, 12), -12);
  eq(api.parallaxOffset(1, 3840, 12), 24, "movement scales consistently with display resolution");
  eq(api.parallaxOffset(1, 1920, 100), 25, "strength cannot exceed the advertised limit");
  eq(api.parallaxOffset(1, 1920, -1), 0);
  const first = api.easeParallax(0, 12, 1000 / 60);
  ok(first > 0 && first < 12, "movement eases toward the pointer instead of jumping");
  near(api.easeParallax(first, 12, 1000 / 60), api.easeParallax(0, 12, 1000 / 30), "easing is independent of refresh rate");
  let eased = 0;
  for (let index = 0; index < 100; index++) {
    const next = api.easeParallax(eased, 12, 1000 / 60);
    ok(next >= eased && next <= 12, "easing never overshoots");
    eased = next;
  }
  eq(eased, 12, "easing stops at the exact destination to avoid a permanent animation loop");

  const page = browser();
  page.initialize();
  eq(page.images.length, 3, "only the complete foreground/background/logo set enables layering");
  page.move(1920);
  eq(page.frames.size, 0, "fallback remains static while layer assets are loading");
  ok(!page.classes.get("is-layered"), "the original characters stay visible until all replacement layers are ready");
  await page.load();
  eq(page.classes.get("is-layered"), true);
  eq(page.classes.get("has-logo-mask"), true);
  eq(page.frames.size, 1);
  page.frame();
  ok(parseFloat(page.styles["--parallax-x"]) > 0 && parseFloat(page.styles["--parallax-x"]) < 12);
  page.move(1800); page.move(1920);
  eq(page.frames.size, 1, "rapid mouse events share one animation frame");
  page.settle();
  eq(page.styles["--parallax-x"], "12.000px");
  eq(page.frames.size, 0, "a still cursor does not keep consuming animation frames");
  eq(page.nodes.seconds["data-text"], page.nodes.seconds.textContent, "the glow copies the current countdown digit");
  eq(page.nodes["clock-time"]["data-text"], page.nodes["clock-time"].textContent);

  page.move(0); page.frame();
  const frozen = page.styles["--parallax-x"];
  page.listener.setPaused(true);
  eq(page.frames.size, 0, "host pause cancels cursor animation");
  eq(page.timers.size, 0, "host pause cancels clock work");
  page.move(1920); page.frame();
  eq(page.styles["--parallax-x"], frozen, "cursor movement does not move the paused foreground");
  page.now(Date.parse("2026-10-15T15:12:34Z"));
  page.listener.setPaused(false);
  eq(page.nodes["clock-time"].textContent, "23:12", "resume calculates current Beijing time immediately");
  eq(page.timers.size, 1);
  page.settle();
  eq(page.styles["--parallax-x"], "12.000px");
  page.hidden(true);
  eq(page.frames.size, 0);
  eq(page.timers.size, 0);
  page.move(0);
  eq(page.frames.size, 0, "hidden wallpaper stays suspended");
  page.hidden(false); page.settle();
  eq(page.styles["--parallax-x"], "-12.000px");

  page.listener.applyUserProperties({ effects: { value: false } });
  eq(page.styles["--parallax-x"], "0.000px", "the effects master switch recenters characters");
  eq(page.classes.get("effects-off"), true);
  page.listener.applyUserProperties({ effects: { value: true }, parallaxstrength: { value: 100 }, neon: { value: false }, glowstrength: { value: -1 } });
  page.settle();
  eq(page.styles["--parallax-x"], "-25.000px", "user properties clamp cursor amplitude");
  eq(page.styles["--glow-opacity"], "0");
  eq(page.classes.get("neon-off"), true);
  page.listener.applyUserProperties({ parallax: { value: false }, glowstrength: { value: 150 } });
  eq(page.styles["--parallax-x"], "0.000px");
  eq(page.styles["--glow-opacity"], "1");
  page.listener.applyUserProperties({ parallax: { value: true }, parallaxstrength: { value: 12 } });
  page.reduce(true);
  eq(page.classes.get("reduced-motion"), false, "wallpaper animation remains enabled unless following the system is explicitly selected");
  page.listener.applyUserProperties({ respectreducedmotion: { value: true } });
  eq(page.classes.get("reduced-motion"), true);
  eq(page.styles["--parallax-x"], "0.000px", "opting into the system reduced-motion preference disables movement");
  eq(page.frames.size, 0);
  page.reduce(false); page.settle();
  eq(page.styles["--parallax-x"], "-12.000px");
  page.resize(3840); page.settle();
  eq(page.styles["--parallax-x"], "-24.000px");
  page.leave(); page.settle();
  eq(page.styles["--parallax-x"], "0.000px", "leaving the desktop gently recenters the artwork");

  const defaultReduced = browser(true);
  defaultReduced.initialize(); await defaultReduced.load(); defaultReduced.move(1920); defaultReduced.settle();
  eq(defaultReduced.classes.get("reduced-motion"), false, "system reduce present at startup does not override explicitly requested dynamic wallpaper");
  eq(defaultReduced.styles["--parallax-x"], "12.000px", "the default remains animated in browsers that emulate reduced motion");
  defaultReduced.listener.applyUserProperties({ respectreducedmotion: { value: true } });
  eq(defaultReduced.classes.get("reduced-motion"), true);
  eq(defaultReduced.styles["--parallax-x"], "0.000px");
  defaultReduced.listener.applyUserProperties({ respectreducedmotion: { value: false } }); defaultReduced.settle();
  eq(defaultReduced.classes.get("reduced-motion"), false);
  eq(defaultReduced.styles["--parallax-x"], "12.000px", "turning off system preference following restores animation immediately");

  const mismatch = browser(); mismatch.initialize(); await mismatch.load(3840, 2160, true);
  ok(!mismatch.classes.get("is-layered"), "mismatched asset coordinates preserve the original instead of ghosting");
  const rounded = browser(); rounded.initialize(); await rounded.load(1672, 941);
  eq(rounded.classes.get("is-layered"), true, "rounded 16:9 extracted images use the original shared canvas");
  const missing = browser(); missing.initialize();
  missing.images[1].onerror(new Error("missing layer"));
  await Promise.resolve(); await Promise.resolve();
  ok(!missing.classes.get("is-layered"), "a missing foreground leaves the complete fallback visible");
  const preinit = browser();
  preinit.listener.applyUserProperties({ parallax: { value: false }, neon: { value: false }, glowstrength: { value: 40 } });
  preinit.initialize(); await preinit.load(); preinit.move(1920);
  eq(preinit.frames.size, 0, "properties arriving before the DOM are preserved");
  eq(preinit.classes.get("neon-off"), true);
  eq(preinit.styles["--glow-opacity"], "0.4");

  const project = JSON.parse(fs.readFileSync(path.join(webRoot, "project.json"), "utf8"));
  for (const name of ["parallax", "parallaxstrength", "neon", "glowstrength", "respectreducedmotion"]) ok(project.general.properties[name], `Wallpaper Engine exposes ${name}`);
  eq(project.general.properties.respectreducedmotion.value, false);
  const css = fs.readFileSync(path.join(webRoot, "style.css"), "utf8");
  ok(css.includes('mask: url("assets/logo-mask.png") var(--scene-position) / var(--scene-width) var(--scene-height) no-repeat'), "logo color and blur follow the actual VI outline in the shared canvas");
  ok(css.includes("prefers-reduced-motion: reduce"));
  ok(css.includes("animation-play-state: paused !important"), "all CSS animations respect host pause");
  console.log(`PASS: ${checks} web effect, pointer, pause, fallback and property assertions`);
}

main().catch(error => { console.error(error); process.exitCode = 1; });
