(function (root) {
  "use strict";

  const DEFAULT_TARGET = "2026-11-19T00:00:00+08:00";
  const WAIT_START = Date.parse("2023-12-04T18:00:00-05:00");
  const DEFAULT_TARGET_MS = Date.parse(DEFAULT_TARGET);
  const BEIJING_OFFSET = 8 * 60 * 60 * 1000;
  const PARALLAX_SMOOTH_MS = 145;
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

  /** Keep the original easing response independent of frame timing. */
  function easeParallax(current, desired, elapsedMs) {
    if (![current, desired, elapsedMs].every(Number.isFinite)) return 0;
    const next = current + (desired - current) * (1 - Math.exp(-clamp(elapsedMs, 0, 100) / PARALLAX_SMOOTH_MS));
    return Math.abs(next - desired) < .015 ? desired : next;
  }

  /** Crop only the logo's effect surfaces while retaining the original cover coordinates. */
  function logoGeometry(viewportWidth, viewportHeight) {
    if (![viewportWidth, viewportHeight].every(Number.isFinite) || viewportWidth <= 0 || viewportHeight <= 0) return null;
    const aspect = viewportWidth / viewportHeight;
    const anchorX = aspect <= 1 ? .57 : (aspect <= 1.5 ? .43 : .5);
    const anchorY = aspect >= 2 ? .4 : .5;
    const scale = Math.max(viewportWidth / 3840, viewportHeight / 2160);
    const sceneWidth = 3840 * scale, sceneHeight = 2160 * scale;
    return {
      left: (viewportWidth - sceneWidth) * anchorX + 180 * scale,
      top: (viewportHeight - sceneHeight) * anchorY + 140 * scale,
      width: 1255 * scale, height: 980 * scale,
      maskX: -180 * scale, maskY: -140 * scale
    };
  }

  function parsePreviewPhase(search) {
    if (typeof search !== "string") return null;
    const match = search.match(/(?:^\?|&)previewPhase=([^&]*)/);
    if (!match) return null;
    try {
      const text = decodeURIComponent(match[1]);
      const phase = Number(text);
      return text.trim() && Number.isFinite(phase) && phase >= 0 ? phase : null;
    } catch (_) { return null; }
  }

  /** Same seed tuple and formulas as effects_spec.particle_state on the native side. */
  function particleState(seed, width, height, phase, strength, spec = root.GTA6_EFFECTS_SPEC && root.GTA6_EFFECTS_SPEC.particles) {
    if (!spec || !Array.isArray(seed) || seed.length !== 7 || ![width, height, phase].every(Number.isFinite) || width <= 0 || height <= 0) return null;
    const amount = Number.isFinite(strength) ? clamp(strength, 0, 1) : spec.default_strength;
    const [x, y, size, color, speed, offset, twinkle] = seed;
    const motion = spec.trajectory, alphaSpec = spec.alpha, trail = spec.trail;
    const wrap = value => value - Math.floor(value);
    const scale = Math.max(spec.scale.minimum, Math.min(width / spec.scale.reference[0], height / spec.scale.reference[1]));
    const px = wrap(x + motion.sway_amplitude * Math.sin(phase * motion.sway_frequency + offset)) * width;
    const py = wrap(y - phase * speed * motion.rise_multiplier) * height;
    const alpha = (alphaSpec.base + alphaSpec.amplitude * (alphaSpec.sine_base + alphaSpec.sine_amplitude * Math.sin(phase * twinkle + offset))) * amount;
    return { x: px, y: py, size, color, alpha, scale, tail: {
      x1: px, y1: py + trail.start_y * scale,
      x2: px + trail.end_x * scale * Math.cos(phase * trail.cos_frequency + offset),
      y2: py + (trail.end_y_base + size * trail.end_y_step) * scale,
      width: Math.max(trail.width_min, (trail.width_base + size * trail.width_step) * scale),
      alpha: alpha * trail.opacity_multiplier * trail.alpha / 255
    } };
  }

  /** One bounded display canvas; the only other buffers are twelve tiny particle sprites. */
  function particleCanvasSize(width, height, devicePixelRatio = 1) {
    if (![width, height].every(Number.isFinite) || width <= 0 || height <= 0) return null;
    const requested = Number.isFinite(devicePixelRatio) && devicePixelRatio > 0 ? devicePixelRatio : 1;
    const ratio = Math.min(2, requested, Math.sqrt(3686400 / (width * height)));
    return { width: Math.max(1, Math.floor(width * ratio)), height: Math.max(1, Math.floor(height * ratio)), ratio };
  }

  const api = { DEFAULT_TARGET, DEFAULT_TARGET_MS, WAIT_START, BEIJING_OFFSET, PARALLAX_SMOOTH_MS, pad2, clamp, parseTarget, beijingParts, formatTarget, calculateState, parseAccent, pointerRatio, parallaxOffset, easeParallax, logoGeometry, parsePreviewPhase, particleState, particleCanvasSize };
  root.GTAVIWallpaper = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof document === "undefined") return;

  let target = DEFAULT_TARGET_MS;
  let usesCustomTarget = false;
  let pausedByHost = false;
  let timer = null;
  let elements = null;
  let layersReady = false;
  let characterMotion = null;
  api.getCharacterPhase = () => characterMotion ? characterMotion.getPhase() : null;
  let systemReducedMotion = false;
  let reducedMotion = false;
  let frame = null;
  let previousFrame = null;
  let mouseRatio = 0;
  let currentOffset = 0;
  const previewPhase = parsePreviewPhase(root.location && root.location.search);
  let particleCanvas = null, particleContext = null, particleSpec = null;
  let particleFrame = null, particlePrevious = null, particlePhase = 0;
  let particleWidth = 0, particleHeight = 0, particleRatio = 1;
  let spriteKey = null, particleSprites = [];
  api.getParticlePhase = () => particlePhase;
  const options = { effects: true, showclock: true, accent: "#ff25c2", textscale: 100, parallax: true, parallaxstrength: 12, neon: true, glowstrength: 85, respectreducedmotion: false, charactermotion: true, charactermotionstrength: 55, particles: true, particlecount: 64, particlebrightness: 85, particlespeed: 100 };

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
    syncParticles();
    syncCharacterMotion();
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
    syncParticles();
    syncCharacterMotion();
    tick();
    freezePreviewEffects();
  }

  function freezePreviewEffects() {
    if (previewPhase === null || typeof document.getAnimations !== "function") return;
    for (const animation of document.getAnimations()) {
      animation.currentTime = previewPhase * 1000;
      animation.pause();
    }
  }

  function rgba(value, alpha) {
    if (Array.isArray(value)) return `rgba(${value[0]},${value[1]},${value[2]},${value[3] / 255})`;
    const color = value.replace("#", "");
    return `rgba(${parseInt(color.slice(0, 2), 16)},${parseInt(color.slice(2, 4), 16)},${parseInt(color.slice(4, 6), 16)},${alpha / 255})`;
  }

  function buildParticleSprites(scale) {
    const key = `${scale}:${particleRatio}`;
    if (spriteKey === key) return;
    // Drop old canvas references before rebuilding for another monitor size.
    particleSprites = [];
    const appearance = particleSpec.sprite;
    particleSprites = particleSpec.colors.map(color => Array.from({ length: appearance.size_count }, (_, size) => {
      const radius = (appearance.radius_base + size * appearance.radius_step) * scale;
      const core = (appearance.core_base + size * appearance.core_step) * scale;
      const half = radius + appearance.padding;
      const sprite = document.createElement("canvas");
      sprite.width = Math.max(1, Math.round(half * 2 * particleRatio));
      sprite.height = sprite.width;
      const painter = sprite.getContext("2d", { alpha: true });
      painter.setTransform(particleRatio, 0, 0, particleRatio, 0, 0);
      const gradient = painter.createRadialGradient(half, half, 0, half, half, radius);
      appearance.stops.forEach(stop => gradient.addColorStop(stop.at, stop.color ? rgba(stop.color) : rgba(color, stop.tint_alpha)));
      painter.fillStyle = gradient;
      painter.beginPath(); painter.arc(half, half, radius, 0, Math.PI * 2); painter.fill();
      painter.fillStyle = rgba(appearance.core_color);
      painter.beginPath(); painter.arc(half, half, core, 0, Math.PI * 2); painter.fill();
      return { canvas: sprite, half, width: sprite.width / particleRatio, height: sprite.height / particleRatio };
    }));
    spriteKey = key;
  }

  function clearParticles() {
    if (particleContext) particleContext.clearRect(0, 0, particleWidth, particleHeight);
  }

  function drawParticles() {
    if (!particleContext || !particleSpec || !particleWidth || !particleHeight) return;
    const scale = Math.max(particleSpec.scale.minimum, Math.min(particleWidth / particleSpec.scale.reference[0], particleHeight / particleSpec.scale.reference[1]));
    buildParticleSprites(scale);
    clearParticles();
    particleContext.globalCompositeOperation = particleSpec.composition === "plus" ? "lighter" : particleSpec.composition;
    particleContext.lineCap = particleSpec.trail.cap;
    for (let index = 0; index < options.particlecount; index++) {
      const seed = particleSpec.seeds[index];
      const state = particleState(seed, particleWidth, particleHeight, particlePhase, options.particlebrightness / 100, particleSpec);
      const tail = state.tail;
      particleContext.globalAlpha = tail.alpha;
      particleContext.strokeStyle = particleSpec.colors[state.color];
      particleContext.lineWidth = tail.width;
      particleContext.beginPath(); particleContext.moveTo(tail.x1, tail.y1); particleContext.lineTo(tail.x2, tail.y2); particleContext.stroke();
      const sprite = particleSprites[state.color][state.size];
      particleContext.globalAlpha = state.alpha;
      particleContext.drawImage(sprite.canvas, state.x - sprite.half, state.y - sprite.half, sprite.width, sprite.height);
    }
    particleContext.globalAlpha = 1;
    particleContext.globalCompositeOperation = "source-over";
  }

  function resizeParticles() {
    if (!particleCanvas) return;
    const width = Number(root.innerWidth), height = Number(root.innerHeight);
    const size = particleCanvasSize(width, height, Number(root.devicePixelRatio));
    if (!size) return;
    if (particleWidth === width && particleHeight === height && particleCanvas.width === size.width && particleCanvas.height === size.height) return;
    particleWidth = width; particleHeight = height; particleRatio = size.ratio;
    particleCanvas.width = size.width; particleCanvas.height = size.height;
    particleContext.setTransform(size.width / width, 0, 0, size.height / height, 0, 0);
    spriteKey = null;
    if (particlesVisible()) drawParticles();
  }

  function particlesVisible() {
    return options.effects && options.particles && options.particlecount > 0 && options.particlebrightness > 0 && !reducedMotion;
  }

  function canAnimateParticles() {
    return particleContext && particlesVisible() && !pausedByHost && !document.hidden;
  }

  function animateParticles(timestamp) {
    particleFrame = null;
    if (!canAnimateParticles() || previewPhase !== null || options.particlespeed === 0) return;
    if (particlePrevious !== null) particlePhase += Math.min(.1, Math.max(0, (timestamp - particlePrevious) / 1000)) * options.particlespeed / 100;
    particlePrevious = timestamp;
    drawParticles();
    particleFrame = root.requestAnimationFrame(animateParticles);
  }

  function syncParticles() {
    if (!particleContext) return;
    if (!canAnimateParticles() || previewPhase !== null || options.particlespeed === 0) {
      if (particleFrame !== null) root.cancelAnimationFrame(particleFrame);
      particleFrame = null; particlePrevious = null;
      if (!particlesVisible()) clearParticles();
      else if (!pausedByHost && !document.hidden) drawParticles();
      return;
    }
    if (particleFrame === null && typeof root.requestAnimationFrame === "function") particleFrame = root.requestAnimationFrame(animateParticles);
  }

  function initializeParticles() {
    const spec = root.GTA6_EFFECTS_SPEC;
    const canvas = document.getElementById("particles");
    if (!spec || !spec.particles || !Array.isArray(spec.particles.seeds) || !canvas || typeof canvas.getContext !== "function" || typeof document.createElement !== "function") return;
    const context = canvas.getContext("2d", { alpha: true });
    if (!context) return;
    particleSpec = spec.particles; particleCanvas = canvas; particleContext = context;
    particlePhase = previewPhase === null ? spec.initial_phase : previewPhase;
    resizeParticles();
  }

  function syncCharacterMotion() {
    if (characterMotion) characterMotion.sync({
      enabled: layersReady && options.effects && options.charactermotion && !reducedMotion,
      strength: options.charactermotionstrength,
      paused: pausedByHost || document.hidden,
      previewPhase
    });
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

  function updateSceneGeometry() {
    const geometry = logoGeometry(Number(root.innerWidth), Number(root.innerHeight));
    if (!geometry) return;
    for (const key of ["left", "top", "width", "height", "maskX", "maskY"]) {
      const property = key.replace(/[A-Z]/g, character => `-${character.toLowerCase()}`);
      document.documentElement.style.setProperty(`--logo-${property}`, `${geometry[key].toFixed(3)}px`);
    }
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
      if (root.GTAVICharacterMotion) {
        try {
          characterMotion = root.GTAVICharacterMotion.create(document.getElementById("character-motion"), document.getElementById("characters"), images[1]);
        } catch (_) { characterMotion = null; }
      }
      layersReady = true;
      document.body.classList.toggle("is-layered", true);
      document.body.classList.toggle("has-logo-mask", true);
      syncMotion();
      syncCharacterMotion();
      freezePreviewEffects();
    }).catch(() => {
      // The static original is already visible, so missing layers never create a blank wallpaper.
    });
  }

  function applyUserProperties(properties) {
    if (!properties || typeof properties !== "object") return;
    if (properties.charactermotion) options.charactermotion = Boolean(properties.charactermotion.value);
    if (properties.particles) options.particles = Boolean(properties.particles.value);
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
    for (const [name, maximum] of [["charactermotionstrength", 100], ["parallaxstrength", 25], ["glowstrength", 100], ["particlecount", particleSpec ? particleSpec.seeds.length : 64], ["particlebrightness", 100], ["particlespeed", 300]]) {
      if (properties[name]) {
        const value = Number(properties[name].value);
        if (Number.isFinite(value)) options[name] = name === "particlecount" ? Math.floor(clamp(value, 0, maximum)) : clamp(value, 0, maximum);
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
    updateSceneGeometry();
    if (typeof root.matchMedia === "function") {
      const preference = root.matchMedia("(prefers-reduced-motion: reduce)");
      systemReducedMotion = preference.matches;
      const updateMotionPreference = event => { systemReducedMotion = event.matches; applyOptions(); };
      if (typeof preference.addEventListener === "function") preference.addEventListener("change", updateMotionPreference);
      else if (typeof preference.addListener === "function") preference.addListener(updateMotionPreference);
    }
    initializeParticles();
    applyOptions();
    document.addEventListener("visibilitychange", scheduleTick);
    document.addEventListener("mousemove", event => {
      mouseRatio = pointerRatio(event.clientX, Number(root.innerWidth));
      syncMotion();
    }, { passive: true });
    document.addEventListener("mouseleave", () => { mouseRatio = 0; syncMotion(); });
    if (typeof root.addEventListener === "function") root.addEventListener("resize", () => { updateSceneGeometry(); resizeParticles(); syncMotion(); syncParticles(); syncCharacterMotion(); freezePreviewEffects(); }, { passive: true });
    loadSceneLayers();
    scheduleTick();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize, { once: true });
  else initialize();
})(typeof window !== "undefined" ? window : globalThis);
