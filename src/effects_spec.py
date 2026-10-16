"""Shared effect parameters and deterministic, Qt-free animation state.

Times and CSS animation delays use seconds.  Geometry returned for particles
uses logical display pixels; logo points use the original artwork coordinates.
The bundled JSON is also exported to JavaScript by tools/prepare_web.py.
"""
from __future__ import annotations

from functools import lru_cache
import json
import math
from pathlib import Path
import sys


_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


@lru_cache(maxsize=4)
def load_effects_spec(path: str | Path | None = None) -> dict:
    """Read the single parameter source; callers should treat it as read-only."""
    source = Path(path) if path is not None else _ROOT / "assets" / "effects-spec.json"
    spec = json.loads(source.read_text(encoding="utf-8"))
    if spec.get("schema_version") != 1:
        raise ValueError("Unsupported wallpaper effects schema")
    particles = spec["particles"]
    if len(particles["seeds"]) != particles["count"]:
        raise ValueError("Particle seed count does not match effects spec")
    return spec


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, float(value)))


def animation_fraction(seconds: float, duration: float, delay: float = 0.0,
                       alternate: bool = False) -> float:
    """CSS-style local progress, including negative delay and alternate cycles."""
    if duration <= 0:
        raise ValueError("Animation duration must be positive")
    cycles = max(0.0, float(seconds)-float(delay)) / float(duration)
    iteration = math.floor(cycles)
    fraction = cycles-iteration
    return 1.0-fraction if alternate and iteration % 2 else fraction


def cubic_bezier(progress: float, control) -> float:
    """Evaluate CSS cubic-bezier by solving its x coordinate before reading y."""
    progress = _clamp(progress)
    if control == "linear" or progress in (0.0, 1.0):
        return progress
    if control == "ease-in-out":
        control = (.42, 0.0, .58, 1.0)
    x1, y1, x2, y2 = control

    def coordinate(t, first, second):
        inverse = 1.0-t
        return 3.0*inverse*inverse*t*first + 3.0*inverse*t*t*second + t*t*t

    lower, upper = 0.0, 1.0
    for _ in range(40):
        middle = (lower+upper)/2.0
        if coordinate(middle, x1, x2) < progress:
            lower = middle
        else:
            upper = middle
    return coordinate((lower+upper)/2.0, y1, y2)


def keyframe_values(progress: float, frames: list[dict], easing="linear") -> dict:
    """Interpolate properties with CSS timing applied within each keyframe span."""
    progress = _clamp(progress)
    keys = tuple(key for key in frames[0] if key != "at")
    for left, right in zip(frames, frames[1:]):
        if progress <= right["at"]:
            interval = right["at"]-left["at"]
            amount = 0.0 if interval <= 0 else (progress-left["at"])/interval
            amount = cubic_bezier(amount, easing)
            return {key: left[key]+(right[key]-left[key])*amount for key in keys}
    return {key: frames[-1][key] for key in keys}


def logo_state(seconds: float, layer: str = "halo", strength: float = 1.0,
               spec: dict | None = None) -> dict:
    """Return one logo layer's eased gradient position and effective opacity."""
    logo = (spec or load_effects_spec())["logo"]
    definition = next((item for item in logo["layers"] if item["name"] == layer), None)
    if definition is None:
        raise ValueError(f"Unknown logo layer: {layer}")
    flow, breathe = logo["flow"], logo["breathe"]
    position = animation_fraction(seconds, flow["duration"], definition["flow_delay"], flow["alternate"])
    pulse = animation_fraction(seconds, breathe["duration"], definition["breathe_delay"])
    opacity = keyframe_values(pulse, breathe["keyframes"], breathe["easing"])["opacity"]
    return dict(layer=layer, flow=cubic_bezier(position, flow["easing"]),
                opacity=opacity*_clamp(strength))


def sparkle_states(seconds: float, strength: float = 1.0,
                   spec: dict | None = None) -> list[dict]:
    """Return all fixed Web contour points with their staggered CSS glimmer."""
    definition = (spec or load_effects_spec())["logo"]["sparkles"]
    result = []
    for point in definition["points"]:
        progress = animation_fraction(seconds, definition["duration"], point["delay"])
        state = keyframe_values(progress, definition["keyframes"], definition["easing"])
        state["opacity"] *= _clamp(strength)
        result.append(dict(x=point["x"], y=point["y"], **state))
    return result


def particle_state(seed, width: float, height: float, seconds: float,
                   strength: float | None = None, spec: dict | None = None) -> dict:
    """Preserve the original EXE particle's position, light and trail formulas.

    ``size`` and ``color`` are indices into the shared sprite sizes and palette.
    The tail alpha already includes both its color alpha and painter opacity.
    """
    definition = (spec or load_effects_spec())["particles"]
    strength = _clamp(definition["default_strength"] if strength is None else strength)
    x, y, size, color, speed, offset, twinkle = seed
    reference = definition["scale"]["reference"]
    scale = max(definition["scale"]["minimum"], min(width/reference[0], height/reference[1]))
    trajectory, opacity, trail = definition["trajectory"], definition["alpha"], definition["trail"]
    px = ((x+trajectory["sway_amplitude"]*math.sin(seconds*trajectory["sway_frequency"]+offset)) % 1.0)*width
    py = ((y-seconds*speed*trajectory["rise_multiplier"]) % 1.0)*height
    alpha = (opacity["base"]+opacity["amplitude"]*(opacity["sine_base"]+opacity["sine_amplitude"]*math.sin(seconds*twinkle+offset)))*strength
    tail = dict(x1=px, y1=py+trail["start_y"]*scale,
                x2=px+trail["end_x"]*scale*math.cos(seconds*trail["cos_frequency"]+offset),
                y2=py+(trail["end_y_base"]+size*trail["end_y_step"])*scale,
                width=max(trail["width_min"], (trail["width_base"]+size*trail["width_step"])*scale),
                alpha=alpha*trail["opacity_multiplier"]*trail["alpha"]/255.0)
    return dict(x=px, y=py, size=size, color=color, alpha=alpha, scale=scale, tail=tail)


def particle_states(seconds: float, width: float, height: float,
                    strength: float | None = None, spec: dict | None = None) -> list[dict]:
    """Return no particles for a non-visible viewport, otherwise all fixed seeds."""
    if width <= 0 or height <= 0:
        return []
    source = spec or load_effects_spec()
    return [particle_state(seed, width, height, seconds, strength, source)
            for seed in source["particles"]["seeds"]]
