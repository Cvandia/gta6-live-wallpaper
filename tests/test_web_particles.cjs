"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const webRoot = process.env.WEB_ROOT || path.resolve(__dirname, "../web");
const appPath = path.join(webRoot, "app.js");
const api = require(appPath);
const spec = JSON.parse(fs.readFileSync(path.resolve(__dirname, "../assets/effects-spec.json"), "utf8"));
let checks = 0;
function eq(value, expected, message) { assert.deepEqual(value, expected, message); checks++; }
function ok(value, message) { assert.ok(value, message); checks++; }
function near(value, expected, message) { ok(Math.abs(value - expected) < 1e-9, message); }
function plain(value) { return JSON.parse(JSON.stringify(value)); }

function browser(search = "") {
  const events = new Map(), rootEvents = new Map(), frames = new Map(), timers = new Map(), classes = new Map(), nodes = {}, sprites = [], images = [];
  let nextId = 0, timestamp = 0, preferenceCallback;
  const animation = { currentTime: 0, pauses: 0, pause() { this.pauses++; } };
  function context() {
    return { draws: [], strokes: [], clears: 0,
      setTransform() {}, clearRect() { this.clears++; }, beginPath() {}, arc() {}, fill() {},
      createRadialGradient() { return { addColorStop() {} }; },
      moveTo(x, y) { this.start = [x, y]; }, lineTo(x, y) { this.end = [x, y]; },
      stroke() { this.strokes.push({ alpha: this.globalAlpha, color: this.strokeStyle, width: this.lineWidth, start: this.start, end: this.end }); },
      drawImage(...args) { this.draws.push({ args, alpha: this.globalAlpha, composition: this.globalCompositeOperation }); }
    };
  }
  const particleContext = context();
  const canvas = { width: 0, height: 0, getContext() { return particleContext; } };
  const document = {
    readyState: "loading", hidden: false,
    getElementById(id) { return id === "particles" ? canvas : (nodes[id] ||= { style: {}, setAttribute(name, value) { this[name] = value; } }); },
    createElement(name) { assert.equal(name, "canvas"); const element = { width: 0, height: 0, getContext() { return this.context ||= context(); } }; sprites.push(element); return element; },
    body: { classList: { toggle(name, value) { classes.set(name, value); } } },
    documentElement: { style: { setProperty() {} } },
    addEventListener(name, callback) { events.set(name, callback); },
    getAnimations() { return [animation]; }
  };
  class FakeImage { set src(value) { this.source = value; images.push(this); } }
  const window = {
    innerWidth: 1920, innerHeight: 1080, devicePixelRatio: 1, location: { search }, Image: FakeImage,
    requestAnimationFrame(callback) { frames.set(++nextId, callback); return nextId; }, cancelAnimationFrame(id) { frames.delete(id); },
    setTimeout(callback, delay) { timers.set(++nextId, { callback, delay }); return nextId; }, clearTimeout(id) { timers.delete(id); },
    addEventListener(name, callback) { rootEvents.set(name, callback); },
    matchMedia() { return { matches: false, addEventListener(name, callback) { preferenceCallback = callback; } }; }
  };
  const sandbox = vm.createContext({ window, document });
  vm.runInContext(fs.readFileSync(path.join(webRoot, "effects-data.js"), "utf8"), sandbox);
  vm.runInContext(fs.readFileSync(appPath, "utf8"), sandbox);
  return { window, document, frames, timers, canvas, particleContext, sprites, classes, animation,
    listener: window.wallpaperPropertyListener,
    initialize() { events.get("DOMContentLoaded")(); },
    frame(elapsed = 1000 / 60) { timestamp += elapsed; const callbacks = [...frames.values()]; frames.clear(); callbacks.forEach(callback => callback(timestamp)); },
    hidden(value) { document.hidden = value; events.get("visibilitychange")(); },
    reduce(value) { preferenceCallback({ matches: value }); },
    resize(width, height, dpr) { window.innerWidth = width; window.innerHeight = height; window.devicePixelRatio = dpr; rootEvents.get("resize")(); },
    async layers() { images.forEach(image => { image.naturalWidth = 3840; image.naturalHeight = 2160; image.onload(); }); await Promise.resolve(); await Promise.resolve(); }
  };
}

function keyframeRules(css, name) {
  const start = css.indexOf(`@keyframes ${name}`);
  ok(start >= 0, `${name} is present`);
  const open = css.indexOf("{", start);
  let depth = 1, end = open + 1;
  for (; depth && end < css.length; end++) { if (css[end] === "{") depth++; if (css[end] === "}") depth--; }
  const result = [];
  for (const match of css.slice(open + 1, end - 1).matchAll(/([\d.,%\s]+)\{([^}]+)\}/g)) {
    match[1].split(",").forEach(at => result.push({ at: parseFloat(at) / 100, body: match[2] }));
  }
  return result.sort((a, b) => a.at - b.at);
}

async function main() {
  eq(spec.particles.count, 64);
  eq(spec.particles.seeds.length, 64);
  eq(new Set(spec.particles.seeds.map(seed => seed[2])).size, 3);
  eq(new Set(spec.particles.seeds.map(seed => seed[3])).size, 4);
  for (const phase of [0, 2, 6.8, 13.7, 900]) {
    for (const [width, height] of [[1920, 1080], [3840, 2160], [900, 1200]]) {
      for (const seed of spec.particles.seeds) {
        const state = api.particleState(seed, width, height, phase, undefined, spec.particles);
        ok(state.x >= 0 && state.x < width && state.y >= 0 && state.y < height, "Python-style modulo keeps upward trajectories inside the viewport");
        ok(state.alpha >= .43 * .85 && state.alpha <= .85 * .85, "particle opacity uses the original native breathing range");
        near(state.tail.alpha, state.alpha * .75 * 83 / 255, "trail alpha includes its own tint and opacity");
      }
    }
  }
  const seed = spec.particles.seeds[0];
  const state = api.particleState(seed, 1920, 1080, 2, .85, spec.particles);
  near(state.x, ((seed[0] + .01 * Math.sin(2 * .24 + seed[5])) % 1) * 1920, "horizontal sinusoid matches EXE");
  near(state.y, ((seed[1] - 2 * seed[4] * .34) % 1 + 1) % 1 * 1080, "vertical rise matches EXE");
  eq(api.particleState(seed, 1920, 1080, 2, 0, spec.particles).alpha, 0);
  eq(api.particleState(seed, 0, 1080, 2, .85, spec.particles), null);
  for (const [width, height, dpr] of [[1920, 1080, 1], [1920, 1080, 3], [3840, 2160, 2], [7680, 4320, 4], [900, 1200, 2]]) {
    const size = api.particleCanvasSize(width, height, dpr);
    ok(size.width * size.height <= 3686400, "the display canvas has one bounded RGBA surface");
    ok(size.ratio <= 2, "canvas DPR cannot exceed two");
  }
  eq(api.parsePreviewPhase("?previewPhase=2"), 2);
  eq(api.parsePreviewPhase("?other=1&previewPhase=6.8"), 6.8);
  for (const value of ["", "?previewPhase=", "?previewPhase=NaN", "?previewPhase=-1", "?previewPhase=%zz"]) eq(api.parsePreviewPhase(value), null);

  const page = browser(); page.initialize();
  eq(page.sprites.length, 12, "only four colors times three small sprites are cached");
  eq(page.particleContext.draws.length, 64, "the initial canvas draws exactly the native's 64 particles");
  eq(page.particleContext.strokes.length, 64, "each particle gets the same short tail");
  ok(page.particleContext.draws.every(draw => draw.composition === "lighter"), "additive canvas blending matches Qt Plus");
  eq(page.frames.size, 1, "one rAF chain drives the particle canvas");
  page.frame(); page.frame();
  eq(page.sprites.length, 12, "ordinary animation reuses sprites without allocating new canvases");
  ok(page.window.GTAVIWallpaper.getParticlePhase() > spec.initial_phase);
  const stopped = page.window.GTAVIWallpaper.getParticlePhase();
  page.listener.setPaused(true); eq(page.frames.size, 0); eq(page.timers.size, 0);
  page.frame(20000); near(page.window.GTAVIWallpaper.getParticlePhase(), stopped, "host pause freezes the exact visual phase");
  page.listener.setPaused(false); eq(page.frames.size, 1);
  page.frame(20000); near(page.window.GTAVIWallpaper.getParticlePhase(), stopped, "resume excludes time spent paused");
  page.frame(); ok(page.window.GTAVIWallpaper.getParticlePhase() > stopped);
  page.hidden(true); eq(page.frames.size, 0); page.hidden(false); eq(page.frames.size, 1);
  page.listener.applyUserProperties({ effects: { value: false } }); eq(page.frames.size, 0);
  const clearCount = page.particleContext.clears;
  page.frame(); eq(page.particleContext.clears, clearCount, "disabled effects do not redraw the hidden canvas");
  page.listener.applyUserProperties({ effects: { value: true }, respectreducedmotion: { value: true } });
  page.reduce(true); eq(page.frames.size, 0); eq(page.classes.get("reduced-motion"), true);
  page.listener.applyUserProperties({ respectreducedmotion: { value: false } }); eq(page.frames.size, 1);
  page.resize(7680, 4320, 4);
  ok(page.canvas.width * page.canvas.height <= 3686400);
  eq(page.sprites.length, 24, "resize replaces the twelve cached sprites once");
  page.frame(); eq(page.sprites.length, 24);

  const preview = browser("?previewPhase=2"); preview.initialize(); await preview.layers();
  eq(preview.window.GTAVIWallpaper.getParticlePhase(), 2);
  eq(preview.frames.size, 0, "fixed-phase preview renders particles once without an animation loop");
  eq(preview.animation.currentTime, 2000);
  ok(preview.animation.pauses > 0, "fixed-phase preview also freezes CSS animations after logo loading");
  preview.frame(9000); eq(preview.window.GTAVIWallpaper.getParticlePhase(), 2);
  const normal = browser(); normal.initialize(); eq(normal.animation.pauses, 0, "ordinary wallpaper URLs do not freeze CSS effects");

  const generated = { window: {} };
  vm.runInNewContext(fs.readFileSync(path.join(webRoot, "effects-data.js"), "utf8"), generated);
  eq(plain(generated.window.GTA6_EFFECTS_SPEC), spec, "the tracked offline script is synchronized with the shared source JSON");
  eq(JSON.parse(fs.readFileSync(path.join(webRoot, "assets/effects-spec.json"), "utf8")), spec);
  const html = fs.readFileSync(path.join(webRoot, "index.html"), "utf8"), css = fs.readFileSync(path.join(webRoot, "style.css"), "utf8");
  ok(html.indexOf('src="effects-data.js"') < html.indexOf('src="app.js"'), "the local effect parameters load before the renderer");
  eq((html.match(/id="particles"/g) || []).length, 1);
  eq((html.match(/<i\s/g) || []).length, 0, "the original 36 CSS particles are fully removed");
  ok(css.includes("mix-blend-mode: plus-lighter"), "the transparent particle surface adds its light to the wallpaper like Qt Plus");
  const actualPoints = [...html.matchAll(/class="logo-sparkle" transform="translate\(([\d.]+) ([\d.]+)\)" style="--delay:([-\d.]+)s"/g)].map(match => ({ x: +match[1], y: +match[2], delay: +match[3] }));
  eq(actualPoints, spec.logo.sparkles.points, "all sixteen existing Web star slots and delays match the shared spec");
  const breathe = keyframeRules(css, "neon-breathe").map(frame => ({ at: frame.at, opacity: frame.body.includes("calc(") ? +frame.body.match(/\*\s*([\d.]+)/)[1] : 1 }));
  eq(breathe, spec.logo.breathe.keyframes, "native logo breathing parameters retain the actual Web keyframes");
  const sparkle = keyframeRules(css, "outline-sparkle").map(frame => ({ at: frame.at, opacity: +frame.body.match(/opacity:\s*([\d.]+)/)[1], scale: +frame.body.match(/scale\(([\d.]+)\)/)[1], rotate_deg: +frame.body.match(/rotate\(([\d.]+)deg\)/)[1] }));
  eq(sparkle, spec.logo.sparkles.keyframes, "native star glimmer parameters retain the Web keyframes");
  ok(css.includes(`neon-flow ${spec.logo.flow.duration}s ease-in-out infinite alternate, neon-breathe ${spec.logo.breathe.duration}s linear infinite`));
  ok(css.includes(`outline-sparkle ${spec.logo.sparkles.duration}s ease-in-out var(--delay) infinite`));
  for (const layer of spec.logo.layers) {
    const rule = [...css.matchAll(new RegExp(`\\.logo-glow__${layer.name}\\s*\\{([^}]+)\\}`, "g"))].map(match => match[1]).find(body => body.includes("filter:"));
    const blur = rule.match(/blur\(max\(([\d.]+)px,\s*([\d.]+)vw\)\)/);
    near(+blur[1], layer.blur_min); near(+blur[2] / 100, layer.blur_width);
    const delayRule = css.match(new RegExp(`\\.logo-glow__${layer.name}::before\\s*\\{[^}]*animation-delay:\\s*([-\\d.]+)s,\\s*([-\\d.]+)s`));
    near(delayRule ? +delayRule[1] : 0, layer.flow_delay);
    near(delayRule ? +delayRule[2] : 0, layer.breathe_delay);
  }
  console.log(`PASS: ${checks} shared particle, bounded canvas, lifecycle, phase-preview and CSS/spec assertions`);
}

main().catch(error => { console.error(error); process.exitCode = 1; });
