/* Local, continuous UV deformation: one texture, one bounded surface, no image copies per frame. */
(function (root) {
  "use strict";
  // Coordinates use the complete characters.png canvas, with Y increasing downward.
  const regions = [
    [.555, .198, .046, .105, 3.6, 1.0, 1.65, .2], // Lucia's ponytail
    [.486, .290, .035, .060, 3.0, 1.2, 1.90, 1.1], // loose hair ends
    [.711, .047, .044, .033, 1.2, .45, 1.50, 2.0], // Jason's hair
    [.437, .419, .059, .064, 1.4, 1.5, .92, .6], // bent forearm
    [.629, .554, .027, .168, 2.0, .75, .83, 1.4], // lowered forearm
    [.616, .259, .043, .112, 1.2, .65, .79, 2.3], // raised arm
    [.822, .257, .045, .103, 1.2, .65, .79, 2.3],
    [.554, .457, .057, .078, 1.0, 1.4, 1.03, .4], // shirt hem
    [.718, .459, .065, .139, 1.3, 1.8, .88, 1.7] // shirt folds
  ];
  const smooth = x => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };
  function displacement(x, y, phase, strength = 55) {
    let dx = 0, dy = 0;
    const facePin = smooth((Math.hypot((x - .52) / .031, (y - .205) / .057) - .9) / .35)
      * smooth((Math.hypot((x - .713) / .032, (y - .108) / .052) - .9) / .35);
    const gain = Math.max(0, Math.min(100, strength)) / 100 * facePin;
    for (const [cx, cy, rx, ry, ax, ay, speed, delay] of regions) {
      const r = Math.hypot((x - cx) / rx, (y - cy) / ry);
      const weight = (1 - smooth((r - .15) / .85)) * gain;
      dx += weight * ax * Math.sin(phase * speed + delay) / 1920;
      dy += weight * ay * Math.sin(phase * speed * .73 + delay + .8) / 1080;
    }
    return [dx, dy];
  }
  function surfaceSize(width, height) {
    if (!(width > 0 && height > 0 && Number.isFinite(width + height))) return null;
    const sceneWidth = Math.max(width, height * 16 / 9);
    const scale = Math.min(1, 1920 / sceneWidth);
    return { width: Math.max(1, Math.round(sceneWidth * scale)), height: Math.max(1, Math.round(sceneWidth * scale * 9 / 16)) };
  }
  const vertex = `attribute vec2 position; varying vec2 uv;
    void main() { uv = vec2((position.x + 1.0) * .5, (1.0 - position.y) * .5); gl_Position = vec4(position, 0.0, 1.0); }`;
  const fragment = `precision highp float;
    varying vec2 uv; uniform sampler2D picture; uniform float phase; uniform float strength;
    ${regions.map((r, i) => `const vec4 area${i} = vec4(${r.slice(0, 4).map(v => v.toFixed(6)).join(",")});`).join("\n")}
    vec2 bend(vec2 p, vec4 area, vec4 motion) {
      float weight = (1.0 - smoothstep(.15, 1.0, length((p - area.xy) / area.zw))) * strength;
      return weight * motion.xy * vec2(sin(phase * motion.z + motion.w), sin(phase * motion.z * .73 + motion.w + .8)) / vec2(1920.0,1080.0);
    }
    void main() {
      vec2 delta = vec2(0.0);
      ${regions.map((r, i) => `delta += bend(uv, area${i}, vec4(${r.slice(4).map(v => v.toFixed(6)).join(",")}));`).join("\n")}
      float facePin = smoothstep(.9, 1.25, length((uv - vec2(.52,.205)) / vec2(.031,.057)))
        * smoothstep(.9, 1.25, length((uv - vec2(.713,.108)) / vec2(.032,.052)));
      gl_FragColor = texture2D(picture, uv - delta * facePin);
    }`;

  function create(canvas, host, image, environment = root) {
    const gl = canvas.getContext("webgl", { alpha: true, antialias: false, depth: false, stencil: false, premultipliedAlpha: false, preserveDrawingBuffer: false });
    if (!gl) return null;
    let program, buffer, texture, timeLocation, strengthLocation;
    let ready = false, lost = false, frame = null, previous = null, phase = 0;
    let enabled = false, paused = false, strength = 55, fixedPhase = null;
    function compile(type, source) {
      const shader = gl.createShader(type);
      gl.shaderSource(shader, source); gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) { gl.deleteShader(shader); throw new Error("Character shader compilation failed"); }
      return shader;
    }
    function setup() {
      const vs = compile(gl.VERTEX_SHADER, vertex), fs = compile(gl.FRAGMENT_SHADER, fragment);
      program = gl.createProgram(); gl.attachShader(program, vs); gl.attachShader(program, fs); gl.linkProgram(program);
      gl.deleteShader(vs); gl.deleteShader(fs);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error("Character shader link failed");
      gl.useProgram(program);
      buffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
      const position = gl.getAttribLocation(program, "position");
      gl.enableVertexAttribArray(position); gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
      texture = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
      for (const parameter of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T]) gl.texParameteri(gl.TEXTURE_2D, parameter, gl.CLAMP_TO_EDGE);
      for (const parameter of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) gl.texParameteri(gl.TEXTURE_2D, parameter, gl.LINEAR);
      timeLocation = gl.getUniformLocation(program, "phase"); strengthLocation = gl.getUniformLocation(program, "strength");
      gl.uniform1i(gl.getUniformLocation(program, "picture"), 0);
      ready = true;
    }
    function resize() {
      const size = surfaceSize(Number(environment.innerWidth), Number(environment.innerHeight));
      if (!size || lost) return;
      if (canvas.width !== size.width || canvas.height !== size.height) { canvas.width = size.width; canvas.height = size.height; }
      gl.viewport(0, 0, canvas.width, canvas.height);
    }
    function draw() {
      if (!ready || lost) return;
      gl.uniform1f(timeLocation, fixedPhase === null ? phase : fixedPhase);
      gl.uniform1f(strengthLocation, strength / 100);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }
    function stop() {
      if (frame !== null) environment.cancelAnimationFrame(frame);
      frame = null; previous = null;
    }
    function animate(timestamp) {
      frame = null;
      if (!enabled || paused || lost) return;
      if (previous !== null) phase += Math.max(0, Math.min(.1, (timestamp - previous) / 1000));
      previous = timestamp; draw();
      frame = environment.requestAnimationFrame(animate);
    }
    function sync(settings) {
      enabled = Boolean(settings.enabled) && settings.strength > 0;
      paused = Boolean(settings.paused); strength = Math.max(0, Math.min(100, settings.strength));
      fixedPhase = settings.previewPhase == null ? null : settings.previewPhase;
      const visible = ready && !lost && enabled;
      host.classList.toggle("character-animated", visible);
      if (!visible || paused || fixedPhase !== null) stop();
      if (!visible) return;
      resize(); draw();
      if (!paused && fixedPhase === null && frame === null) frame = environment.requestAnimationFrame(animate);
    }
    canvas.addEventListener("webglcontextlost", event => { event.preventDefault(); lost = true; ready = false; stop(); host.classList.toggle("character-animated", false); });
    canvas.addEventListener("webglcontextrestored", () => {
      lost = false;
      try { setup(); sync({ enabled, paused, strength, previewPhase: fixedPhase }); }
      catch (_) { ready = false; host.classList.toggle("character-animated", false); }
    });
    try { setup(); }
    catch (_) {
      if (texture) gl.deleteTexture(texture);
      if (buffer) gl.deleteBuffer(buffer);
      if (program) gl.deleteProgram(program);
      return null;
    }
    return { sync, resize, getPhase: () => phase };
  }
  const api = { create, displacement, surfaceSize, regions, vertex, fragment };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.GTAVICharacterMotion = api;
})(typeof window !== "undefined" ? window : globalThis);
