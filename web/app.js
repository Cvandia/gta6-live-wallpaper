(function (root) {
  "use strict";

  const DEFAULT_TARGET = "2026-11-19T00:00:00+08:00";
  const WAIT_START = Date.parse("2023-12-04T18:00:00-05:00");
  const DEFAULT_TARGET_MS = Date.parse(DEFAULT_TARGET);
  const BEIJING_OFFSET = 8 * 60 * 60 * 1000;
  const WEEKDAYS = ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"];
  const pad2 = value => String(value).padStart(2, "0");
  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

  /** No-zone custom dates are interpreted in Beijing, never in the PC's timezone. */
  function parseTarget(value, fallback = DEFAULT_TARGET_MS) {
    if (typeof value !== "string" || !value.trim()) return fallback;
    let normalized = value.trim().replace(/\//g, "-").replace(/\s+/, "T");
    if (/^\d{4}-\d{2}-\d{2}$/.test(normalized)) normalized += "T00:00:00+08:00";
    else if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?$/.test(normalized)) normalized += "+08:00";
    // Requiring an ISO date prevents locale-dependent month/day interpretations.
    const match = normalized.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d{1,3})?)?(?:Z|[+-]\d{2}:\d{2})$/i);
    if (!match) return fallback;
    const [, yearText, monthText, dayText, hourText, minuteText, secondText = "0"] = match;
    const [year, month, day, hour, minute, second] = [yearText, monthText, dayText, hourText, minuteText, secondText].map(Number);
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const monthDays = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    if (month < 1 || month > 12 || day < 1 || day > monthDays[month - 1] || hour > 23 || minute > 59 || second > 59) return fallback;
    const parsed = Date.parse(normalized);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function beijingParts(now) {
    const date = new Date(Number(now) + BEIJING_OFFSET);
    return {
      year: date.getUTCFullYear(), month: date.getUTCMonth() + 1, day: date.getUTCDate(),
      hour: date.getUTCHours(), minute: date.getUTCMinutes(), second: date.getUTCSeconds(),
      weekday: WEEKDAYS[date.getUTCDay()]
    };
  }

  function formatTarget(target) {
    const p = beijingParts(target);
    return `${p.year}年${p.month}月${p.day}日 — ${pad2(p.hour)}:${pad2(p.minute)} GMT+8`;
  }

  /** Pure state calculation, exported for unit tests and external previews. */
  function calculateState(now, target = DEFAULT_TARGET_MS, start = WAIT_START) {
    const current = Number(now);
    const deadline = Number(target);
    if (![current, deadline, Number(start)].every(Number.isFinite)) throw new TypeError("Expected finite epoch milliseconds");
    const totalSeconds = Math.max(0, Math.ceil((deadline - current) / 1000));
    const duration = deadline - Number(start);
    const progress = duration > 0 ? clamp((current - Number(start)) / duration, 0, 1) : (current >= deadline ? 1 : 0);
    const clock = beijingParts(current);
    return {
      days: Math.floor(totalSeconds / 86400),
      hours: Math.floor(totalSeconds / 3600) % 24,
      minutes: Math.floor(totalSeconds / 60) % 60,
      seconds: totalSeconds % 60,
      totalSeconds, progress, released: current >= deadline,
      clockTime: `${pad2(clock.hour)}:${pad2(clock.minute)}`,
      clockDate: `${clock.month}月${clock.day}日 ${clock.weekday}`,
      targetLabel: formatTarget(deadline)
    };
  }

  function parseAccent(value) {
    if (typeof value !== "string") return null;
    if (/^#[0-9a-f]{6}$/i.test(value.trim())) return value.trim();
    const parts = value.trim().split(/\s+/).map(Number);
    if (parts.length !== 3 || !parts.every(Number.isFinite)) return null;
    return `rgb(${parts.map(component => Math.round(clamp(component, 0, 1) * 255)).join(", ")})`;
  }

  /** Horizontal movement is measured in pixels at 1920px, scaled with the viewport. */
  function pointerRatio(clientX, viewportWidth) {
    if (!Number.isFinite(clientX) || !Number.isFinite(viewportWidth) || viewportWidth <= 0) return 0;
    return clamp(clientX / viewportWidth * 2 - 1, -1, 1);
  }

  function parallaxOffset(ratio, viewportWidth, strength = 12) {
    if (![ratio, viewportWidth, strength].every(Number.isFinite) || viewportWidth <= 0) return 0;
    return clamp(ratio, -1, 1) * clamp(strength, 0, 25) * viewportWidth / 1920;
  }

  /** Exponential easing gives the same movement at 30, 60 and 144Hz. */
  function easeParallax(current, desired, elapsedMs) {
    if (![current, desired, elapsedMs].every(Number.isFinite)) return 0;
    const next = current + (desired - current) * (1 - Math.exp(-clamp(elapsedMs, 0, 100) / 145));
    return Math.abs(next - desired) < .015 ? desired : next;
  }

  const api = { DEFAULT_TARGET, DEFAULT_TARGET_MS, WAIT_START, BEIJING_OFFSET, pad2, clamp, parseTarget, beijingParts, formatTarget, calculateState, parseAccent, pointerRatio, parallaxOffset, easeParallax };
  root.GTAVIWallpaper = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof document === "undefined") return;

  let target = DEFAULT_TARGET_MS;
  let usesCustomTarget = false;
  let pausedByHost = false;
  let timer = null;
  let elements = null;
  let layersReady = false;
  let systemReducedMotion = false;
  let reducedMotion = false;
  let frame = null;
  let previousFrame = null;
  let mouseRatio = 0;
  let currentOffset = 0;
  const options = { effects: true, showclock: true, accent: "#ff25c2", textscale: 100, parallax: true, parallaxstrength: 12, neon: true, glowstrength: 65, respectreducedmotion: false };

  function cacheElements() {
    elements = {};
    ["days", "hours", "minutes", "seconds", "clock", "clock-time", "clock-date", "intro", "progress", "progress-fill", "progress-text", "target-date", "target-note"].forEach(id => {
      elements[id] = document.getElementById(id);
    });
  }

  function tick() {
    if (!elements) return;
    const state = calculateState(Date.now(), target);
    ["days", "hours", "minutes", "seconds"].forEach(key => {
      const text = pad2(state[key]);
      elements[key].textContent = text;
      elements[key].setAttribute("data-text", text);
    });
    // Large day counts remain legible when a custom release date is far away.
    const dayDigits = String(state.days).length;
    elements.days.style.fontSize = dayDigits > 2 ? `calc(var(--number-size) * ${2 / dayDigits})` : "";
    elements["clock-time"].textContent = state.clockTime;
    elements["clock-time"].setAttribute("data-text", state.clockTime);
    elements["clock-date"].textContent = state.clockDate;
    elements["progress-fill"].style.width = `${state.progress * 100}%`;
    elements.progress.setAttribute("aria-valuenow", (state.progress * 100).toFixed(1));
    elements["progress-text"].textContent = `已完成 ${(state.progress * 100).toFixed(1)}%`;
    elements["target-date"].textContent = state.targetLabel;
    elements.intro.textContent = state.released ? "欢迎来到莱昂尼达" : "欢迎来到莱昂尼达，还有";
    elements["target-note"].textContent = state.released
      ? "计划发售日已到 · 以商店实际解锁为准"
      : (usesCustomTarget ? "自定义目标 · 北京时间" : "港区 PS5 · PS Store 列示时间");
    document.body.classList.toggle("is-released", state.released);
  }

  function scheduleTick() {
    if (timer !== null) root.clearTimeout(timer);
    timer = null;
    const paused = pausedByHost || document.hidden;
    document.body.classList.toggle("is-paused", paused);
    syncMotion();
    if (paused) return;
    tick();
    timer = root.setTimeout(scheduleTick, 1000 - (Date.now() % 1000) + 8);
  }

  function applyOptions() {
    if (!elements) return;
    reducedMotion = options.respectreducedmotion && systemReducedMotion;
    document.body.classList.toggle("effects-off", !options.effects);
    document.body.classList.toggle("neon-off", !options.neon);
    document.body.classList.toggle("reduced-motion", reducedMotion);
    elements.clock.hidden = !options.showclock;
    document.documentElement.style.setProperty("--accent", options.accent);
    document.documentElement.style.setProperty("--text-scale", String(options.textscale / 100));
    document.documentElement.style.setProperty("--glow-opacity", String(options.glowstrength / 100));
    syncMotion();
    tick();
  }

  function canMove() {
    return layersReady && options.effects && options.parallax && options.parallaxstrength > 0 && !reducedMotion;
  }

  function renderOffset(value) {
    currentOffset = value;
    document.documentElement.style.setProperty("--parallax-x", `${value.toFixed(3)}px`);
  }

  function animateParallax(timestamp) {
    frame = null;
    if (!canMove() || pausedByHost || document.hidden) return;
    const desired = parallaxOffset(mouseRatio, Number(root.innerWidth), options.parallaxstrength);
    const elapsed = previousFrame === null ? 1000 / 60 : timestamp - previousFrame;
    previousFrame = timestamp;
    renderOffset(easeParallax(currentOffset, desired, elapsed));
    if (currentOffset !== desired) frame = root.requestAnimationFrame(animateParallax);
    else previousFrame = null;
  }

  function syncMotion() {
    if (!elements) return;
    if (!canMove()) {
      if (frame !== null) root.cancelAnimationFrame(frame);
      frame = null;
      previousFrame = null;
      renderOffset(0);
      return;
    }
    if (pausedByHost || document.hidden || typeof root.requestAnimationFrame !== "function") {
      if (frame !== null) root.cancelAnimationFrame(frame);
      frame = null;
      previousFrame = null;
      return;
    }
    const desired = parallaxOffset(mouseRatio, Number(root.innerWidth), options.parallaxstrength);
    if (currentOffset !== desired && frame === null) frame = root.requestAnimationFrame(animateParallax);
  }

  function loadSceneLayers() {
    if (typeof root.Image !== "function") return;
    const sources = ["assets/scene-background.jpg", "assets/characters.png", "assets/logo-mask.png"];
    const load = source => new Promise((resolve, reject) => {
      const image = new root.Image();
      image.onload = () => resolve(image);
      image.onerror = reject;
      image.src = source;
    });
    Promise.all(sources.map(load)).then(images => {
      // Full-canvas assets share original 16:9 coordinates, with slight rounding allowed for extracted images.
      // CSS gives every layer exactly the same target rectangle instead of covering from its own natural size.
      if (!images.every(image => image.naturalWidth > 0 && image.naturalHeight > 0 && Math.abs(image.naturalWidth / image.naturalHeight / (16 / 9) - 1) < .01)) return;
      layersReady = true;
      document.body.classList.toggle("is-layered", true);
      document.body.classList.toggle("has-logo-mask", true);
      syncMotion();
    }).catch(() => {
      // The static original is already visible, so missing layers never create a blank wallpaper.
    });
  }

  function applyUserProperties(properties) {
    if (!properties || typeof properties !== "object") return;
    if (properties.effects) options.effects = Boolean(properties.effects.value);
    if (properties.showclock) options.showclock = Boolean(properties.showclock.value);
    if (properties.parallax) options.parallax = Boolean(properties.parallax.value);
    if (properties.neon) options.neon = Boolean(properties.neon.value);
    if (properties.respectreducedmotion) options.respectreducedmotion = Boolean(properties.respectreducedmotion.value);
    if (properties.accent) options.accent = parseAccent(properties.accent.value) || options.accent;
    if (properties.textscale) {
      const value = Number(properties.textscale.value);
      if (Number.isFinite(value)) options.textscale = clamp(value, 70, 125);
    }
    for (const [name, maximum] of [["parallaxstrength", 25], ["glowstrength", 100]]) {
      if (properties[name]) {
        const value = Number(properties[name].value);
        if (Number.isFinite(value)) options[name] = clamp(value, 0, maximum);
      }
    }
    if (properties.targetdate) {
      const custom = parseTarget(properties.targetdate.value, null);
      usesCustomTarget = custom !== null;
      target = usesCustomTarget ? custom : DEFAULT_TARGET_MS;
    }
    applyOptions();
  }

  // Wallpaper Engine delivers properties and pause notifications through this API.
  function setPaused(value) {
    pausedByHost = Boolean(value);
    if (elements) scheduleTick();
  }

  root.wallpaperPropertyListener = {
    applyUserProperties,
    setPaused,
    applyGeneralProperties(properties) {
      if (properties && typeof properties.isPaused === "boolean") setPaused(properties.isPaused);
    }
  };

  function initialize() {
    cacheElements();
    if (typeof root.matchMedia === "function") {
      const preference = root.matchMedia("(prefers-reduced-motion: reduce)");
      systemReducedMotion = preference.matches;
      const updateMotionPreference = event => { systemReducedMotion = event.matches; applyOptions(); };
      if (typeof preference.addEventListener === "function") preference.addEventListener("change", updateMotionPreference);
      else if (typeof preference.addListener === "function") preference.addListener(updateMotionPreference);
    }
    applyOptions();
    document.addEventListener("visibilitychange", scheduleTick);
    document.addEventListener("mousemove", event => {
      mouseRatio = pointerRatio(event.clientX, Number(root.innerWidth));
      syncMotion();
    }, { passive: true });
    document.addEventListener("mouseleave", () => { mouseRatio = 0; syncMotion(); });
    if (typeof root.addEventListener === "function") root.addEventListener("resize", syncMotion, { passive: true });
    loadSceneLayers();
    scheduleTick();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize, { once: true });
  else initialize();
})(typeof window !== "undefined" ? window : globalThis);
