"use strict";
const assert = require("node:assert/strict");
const motion = require("../web/character-motion.js");
const fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
let checks = 0;
function ok(value, message) { assert.ok(value, message); checks++; }
for (const [w,h] of [[1920,1080],[3840,2160],[7680,4320],[900,1600]]) {
  const size = motion.surfaceSize(w,h);
  ok(size.width * size.height <= 2073600, "GPU surface is capped at 1080p, including portrait displays");
  ok(Math.abs(size.width / size.height - 16 / 9) < .003);
}
ok(motion.surfaceSize(0,1080) === null);
ok(motion.surfaceSize(Infinity,1080) === null);
for (let time = 0; time < 20; time += .25) {
  for (const [x,y] of [[.52,.20],[.713,.105],[.55,.85],[.73,.85],[.2,.4]]) {
    const [dx,dy] = motion.displacement(x,y,time,100);
    ok(dx === 0 && dy === 0, "faces, legs and empty background stay pinned");
  }
  for (const region of motion.regions) {
    const [dx,dy] = motion.displacement(region[0],region[1],time,100);
    ok(Math.hypot(dx * 1920, dy * 1080) < 16, "localized displacement stays subtle at maximum strength");
    const half = motion.displacement(region[0],region[1],time,50);
    ok(Math.abs(half[0] - dx / 2) < 1e-12 && Math.abs(half[1] - dy / 2) < 1e-12);
    assert.deepEqual(motion.displacement(region[0],region[1],time,0),[0,0]); checks++;
  }
}
ok(motion.create({getContext:()=>null}, {}, {}) === null, "no WebGL keeps the original image fallback");
const web = path.resolve(__dirname, "../web");
const sandbox = {window:{}};
vm.runInNewContext(fs.readFileSync(path.join(web,"character-texture.js"),"utf8"),sandbox);
const texture = sandbox.window.GTA6_CHARACTER_TEXTURE;
ok(texture.startsWith("data:image/png;base64,"), "local-file texture uses an origin-safe data URL");
assert.deepEqual(Buffer.from(texture.split(",")[1],"base64"),fs.readFileSync(path.join(web,"assets/characters.png"))); checks++;
const html = fs.readFileSync(path.join(web,"index.html"),"utf8");
ok(html.indexOf('src="character-texture.js"') < html.indexOf('src="app.js"'), "embedded texture is ready before local images load");
console.log(`PASS: ${checks} character deformation, pinned anatomy, strength and memory assertions`);
