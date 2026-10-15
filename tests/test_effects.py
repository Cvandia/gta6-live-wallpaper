import math
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))
from effects import cursor_target, smooth_position, glow_pulse


class MotionTest(unittest.TestCase):
    def test_mouse_edges_and_leaving_screen(self):
        self.assertEqual(cursor_target(0, 1920), -1)
        self.assertEqual(cursor_target(960, 1920), 0)
        self.assertEqual(cursor_target(1920, 1920), 1)
        self.assertEqual(cursor_target(-500, 1920), -1)
        self.assertEqual(cursor_target(5000, 1920), 1)
        self.assertEqual(cursor_target(100, 1920, False), 0)

    def test_motion_is_frame_rate_independent(self):
        positions=[]
        for fps in (10,20,30,60):
            x=0
            for _ in range(fps):
                x=smooth_position(x,1,1/fps)
            positions.append(x)
        for value in positions:
            self.assertAlmostEqual(value, 1-math.exp(-1/.18), places=10)

    def test_no_overshoot_and_no_motion_for_zero_dt(self):
        self.assertEqual(smooth_position(.5,-1,0), .5)
        self.assertGreaterEqual(smooth_position(1,-1,5), -1)
        self.assertLessEqual(smooth_position(-1,1,5), 1)

    def test_glow_never_flashes_off(self):
        samples=[glow_pulse(i/30) for i in range(1800)]
        self.assertGreaterEqual(min(samples), .45)
        self.assertLessEqual(max(samples), 1)
        self.assertGreater(max(samples)-min(samples), .25)


class RenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFontDatabase
        cls.app = QApplication.instance() or QApplication([])
        font = Path(os.environ.get("WINDIR", "C:/Windows"))/"Fonts/msyh.ttc"
        if font.exists():
            QFontDatabase.addApplicationFont(str(font))

    def window(self):
        from main import Wallpaper
        args=SimpleNamespace(parentHWND=0,desktop=False,fullscreen=False,wpe_w=960,wpe_h=540,
            wpe_x=0,wpe_y=0,config_dir=str(Path(__file__).parent/"render-config"),
            at="2026-10-15T22:10:00+08:00",screenshot="test",phase=2.,parallax_x=0.)
        w=Wallpaper(args)
        w.now=w.frozen_now
        w.show()
        self.app.processEvents()
        self.addCleanup(w.close)
        return w

    def test_people_move_while_logo_and_countdown_stay_fixed(self):
        w=self.window()
        self.assertTrue(w.layers_ready)
        w.parallax_position=-1
        left=w.grab().toImage()
        w.parallax_position=1
        right=w.grab().toImage()
        self.assertEqual(left.copy(20,30,320,230),right.copy(20,30,320,230))
        self.assertEqual(left.copy(45,300,300,180),right.copy(45,300,300,180))
        self.assertNotEqual(left.copy(370,40,450,480),right.copy(370,40,450,480))

    def test_pause_freezes_light_despite_clock_repaint(self):
        w=self.window()
        before=w.grab().toImage()
        phase=w.animation_time
        w.paused=True
        w.on_animation()
        w.on_tick()
        after=w.grab().toImage()
        self.assertEqual(w.animation_time,phase)
        self.assertEqual(before,after)

    def test_effects_switch_removes_neon_without_moving_layout(self):
        w=self.window()
        before=w.grab().toImage()
        w.config["effects"]=False
        after=w.grab().toImage()
        self.assertNotEqual(before.copy(40,30,320,230),after.copy(40,30,320,230))
        self.assertEqual(w.width(),960)


if __name__=="__main__":
    unittest.main()
