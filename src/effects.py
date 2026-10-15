"""Frame-rate independent motion for both desktop and Wallpaper Engine windows."""
import math


def cursor_target(x: float, width: float, inside: bool = True) -> float:
    if not inside or width <= 0:
        return 0.0
    return max(-1.0, min(1.0, x / width * 2.0 - 1.0))


def smooth_position(current: float, target: float, seconds: float) -> float:
    # A time constant makes 10, 20 and 30 FPS feel identical.
    return current + (target-current) * (1-math.exp(-max(0.0, seconds)/.18))


def glow_pulse(seconds: float) -> float:
    # Slow breathing plus a tiny neon irregularity; the light never flashes off.
    return max(.45, min(1.0, .74 + .19*math.sin(seconds*.9) + .035*math.sin(seconds*7.3)*math.sin(seconds*2.1)))
