"""Check actual JavaScript and Python particle states against the same seeds."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from effects_spec import load_effects_spec, particle_states


class EffectParityTest(unittest.TestCase):
    def test_particle_positions_light_and_trails_match_javascript(self):
        node = os.environ.get("NODE_BINARY") or shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for cross-runtime parity; CI provides it")
        cases = [(width, height, phase, strength)
                 for width, height in ((960, 540), (1920, 1080), (3840, 2160), (2560, 1080))
                 for phase in (0, .125, 2, 6.4, 9, 12345.678)
                 for strength in (0, .85, 1)]
        script = """
const api = require(process.argv[1]);
const spec = require(process.argv[2]);
let text = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', data => text += data);
process.stdin.on('end', () => {
  const cases = JSON.parse(text);
  const states = cases.map(([width, height, phase, strength]) =>
    spec.particles.seeds.map(seed => api.particleState(seed, width, height, phase, strength, spec.particles)));
  process.stdout.write(JSON.stringify(states));
});
"""
        output = subprocess.run([node, "-e", script, str(ROOT/"web/app.js"),
                                 str(ROOT/"assets/effects-spec.json")], input=json.dumps(cases),
                                text=True, capture_output=True, check=True, timeout=30)
        actual = json.loads(output.stdout)
        spec = load_effects_spec()
        self.assertEqual(len(spec["particles"]["seeds"]), 64)
        self.assertEqual(len(actual), len(cases))
        for case, web_states in zip(cases, actual):
            width, height, phase, strength = case
            native_states = particle_states(phase, width, height, strength, spec)
            self.assertEqual(len(web_states), 64)
            for native, web in zip(native_states, web_states):
                self.assertEqual(set(native), set(web))
                for key in ("x", "y", "size", "color", "alpha", "scale"):
                    self.assertAlmostEqual(native[key], web[key], delta=1e-7, msg=f"{case}: {key}")
                self.assertEqual(set(native["tail"]), set(web["tail"]))
                for key in native["tail"]:
                    self.assertAlmostEqual(native["tail"][key], web["tail"][key], delta=1e-7,
                                           msg=f"{case}: tail {key}")


if __name__ == "__main__":
    unittest.main()
