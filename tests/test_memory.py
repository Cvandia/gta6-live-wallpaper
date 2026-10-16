"""Check retained bitmap sizes and cache lifetime using real Qt image storage."""

import gc
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import weakref

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from memory import load_scaled_pixmap
from model import DEFAULT_TARGET


class QtMemoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def temporary_directory(self):
        temporary = tempfile.TemporaryDirectory(prefix="gta6-bitmap-test-")
        self.addCleanup(temporary.cleanup)
        return Path(temporary.name)


class DisplaySizedDecodeTest(QtMemoryTest):
    def striped_image(self):
        path = self.temporary_directory() / "striped.png"
        image = QImage(1000, 500, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.fillRect(0, 0, 370, 500, QColor("red"))
        painter.fillRect(370, 0, 520, 500, QColor("lime"))
        painter.fillRect(890, 0, 110, 500, QColor("blue"))
        painter.end()
        self.assertTrue(image.save(str(path)))
        return path

    def test_decode_uses_display_pixels_and_preserves_device_pixel_ratio(self):
        path = self.striped_image()
        for dpr in (1.0, 1.5, 2.0):
            with self.subTest(dpr=dpr):
                pixmap = load_scaled_pixmap(path, 200, 100, dpr)
                self.assertEqual(pixmap.size(), QSize(round(200*dpr), round(100*dpr)))
                self.assertEqual(pixmap.devicePixelRatio(), dpr)
                self.assertEqual(pixmap.deviceIndependentSize().width(), 200)
                self.assertEqual(pixmap.deviceIndependentSize().height(), 100)
                self.assertLess(pixmap.width()*pixmap.height(), 1000*500)

    def test_people_crop_keeps_correct_pixels_and_only_half_the_canvas(self):
        path = self.striped_image()
        for dpr in (1.0, 1.5, 2.0):
            with self.subTest(dpr=dpr):
                whole = load_scaled_pixmap(path, 200, 100, dpr)
                cropped = load_scaled_pixmap(path, 200, 100, dpr, crop=(.37, 0, .52, 1))
                self.assertEqual(cropped.size(), QSize(round(.52*round(200*dpr)), round(100*dpr)))
                self.assertEqual(cropped.devicePixelRatio(), dpr)
                self.assertLess(cropped.width()*cropped.height(), whole.width()*whole.height()*.53)
                image = cropped.toImage()
                for x in (3, image.width()//2, image.width()-4):
                    self.assertEqual(image.pixelColor(x, image.height()//2), QColor("lime"))

    def test_missing_or_corrupt_image_reports_an_error(self):
        directory = self.temporary_directory()
        missing = directory / "missing.png"
        corrupt = directory / "corrupt.png"
        corrupt.write_text("not an image", encoding="utf-8")
        for path in (missing, corrupt):
            with self.subTest(path=path.name):
                with self.assertRaisesRegex(RuntimeError, path.name.replace(".", r"\.")):
                    load_scaled_pixmap(path, 200, 100, 1.0)


class WallpaperBitmapCacheTest(QtMemoryTest):
    def wallpaper(self):
        from main import Wallpaper
        args = SimpleNamespace(parentHWND=0, desktop=False, fullscreen=False,
            wpe_w=960, wpe_h=540, wpe_x=0, wpe_y=0,
            config_dir=str(self.temporary_directory()), at=DEFAULT_TARGET,
            screenshot="test", phase=2.0, parallax_x=0.0)
        window = Wallpaper(args)
        window.now = window.frozen_now
        window.animation.stop()
        window.tick.stop()
        window.host_timer.stop()
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        window.grab()
        return window

    def test_retained_scene_and_people_use_display_sized_storage(self):
        window = self.wallpaper()
        self.assertTrue(window.layers_ready)
        dpr = window.devicePixelRatioF()
        background = window.background_cache[1]
        foreground = window.foreground_cache[1]
        self.assertEqual(background.size(), QSize(round(960*dpr), round(540*dpr)))
        self.assertEqual(foreground.size(), QSize(round(.52*round(960*dpr)), round(540*dpr)))
        retained_pixels = background.width()*background.height() + foreground.width()*foreground.height()
        original_pixels = window.art_size.width()*window.art_size.height()
        # At this viewport the display buffers need far less storage than even
        # one original 4K bitmap, before counting the formerly retained layers.
        self.assertLess(retained_pixels, original_pixels/4)
        self.assertLess(foreground.width()*foreground.height(), background.width()*background.height()*.53)

    def test_resize_releases_old_bitmap_objects_and_invalidates_visuals(self):
        window = self.wallpaper()
        old_background = weakref.ref(window.background_cache[1])
        old_foreground = weakref.ref(window.foreground_cache[1])
        old_effects = [weakref.ref(pixmap) for pixmap in window.visuals._logo_frames]
        old_effects += [weakref.ref(sprite) for row in window.visuals._particle_sprites for sprite, _ in row]
        old_effects += [weakref.ref(sprite) for sprite, _ in window.visuals._star_sprites]
        self.assertTrue(old_effects)
        old_effect_bytes = window.visuals.cache_bytes()
        original_invalidate = window.visuals.invalidate

        def invalidate_and_check_release():
            original_invalidate()
            self.assertLess(window.visuals.cache_bytes(), old_effect_bytes)
            self.assertTrue(all(reference() is None for reference in old_effects))

        with patch.object(window.visuals, "invalidate", side_effect=invalidate_and_check_release) as invalidate:
            window.resize(800, 450)
            self.app.processEvents()
            window.grab()
            self.assertGreaterEqual(invalidate.call_count, 1)
        gc.collect()
        self.assertIsNone(old_background())
        self.assertIsNone(old_foreground())
        self.assertTrue(all(reference() is None for reference in old_effects))
        self.assertLess(window.visuals.cache_bytes(), old_effect_bytes)
        dpr = window.devicePixelRatioF()
        self.assertEqual(window.background_cache[1].size(), QSize(round(800*dpr), round(450*dpr)))
        self.assertEqual(window.foreground_cache[1].size(), QSize(round(.52*round(800*dpr)), round(450*dpr)))

    def test_animation_reuses_display_bitmaps_instead_of_accumulating_frames(self):
        window = self.wallpaper()
        background_key = window.background_cache[1].cacheKey()
        foreground_key = window.foreground_cache[1].cacheKey()
        visual_bytes = window.visuals.cache_bytes()
        for frame in range(24):
            window.animation_time = frame*.7
            window.grab()
            self.assertEqual(window.background_cache[1].cacheKey(), background_key)
            self.assertEqual(window.foreground_cache[1].cacheKey(), foreground_key)
            self.assertEqual(window.visuals.cache_bytes(), visual_bytes)


if __name__ == "__main__":
    unittest.main()
