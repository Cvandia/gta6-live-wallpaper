"""Headless visual contracts and memory limits; no benchmark/output files."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QApplication

from visuals import WallpaperVisuals


class VisualsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        # The real clipped assets are loaded once. No test loads a background or
        # allocates a full-screen 4K canvas just to exercise the atlas limits.
        cls.visuals = WallpaperVisuals.from_assets(ROOT / "assets")

    def setUp(self):
        self.visuals.invalidate()
        self.source_bytes = self.visuals.cache_bytes()

    def tearDown(self):
        self.visuals.invalidate()

    def render(self, phase, strength=.85):
        canvas = QPixmap(640, 360)
        canvas.fill(QColor("#211735"))
        painter = QPainter(canvas)
        try:
            self.visuals.paint_logo(painter, QRectF(0, 0, 640, 360), phase, strength)
            self.visuals.paint_particles(painter, 640, 360, phase, strength)
        finally:
            painter.end()
        return canvas.toImage()

    def test_frozen_phase_is_deterministic_and_later_phase_changes_pixels(self):
        first = self.render(2)
        self.assertEqual(first, self.render(2))
        self.assertNotEqual(first, self.render(8))

    def test_zero_strength_leaves_the_entire_canvas_unchanged(self):
        first = self.render(2, strength=0)
        self.assertEqual(first, self.render(8, strength=0))
        self.assertEqual(first.pixelColor(30, 30), QColor("#211735"))
        self.assertEqual(self.visuals.cache_bytes(), self.source_bytes)

    def test_drawing_restores_caller_painter_state(self):
        canvas = QPixmap(640, 360)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        painter.setOpacity(.73)
        painter.translate(3.25, 4.5)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        state = (painter.opacity(), painter.transform(), painter.compositionMode(),
                 painter.pen(), painter.brush(), painter.renderHints())
        try:
            for draw in (
                lambda: self.visuals.paint_logo(painter, QRectF(0, 0, 640, 360), 2),
                lambda: self.visuals.paint_particles(painter, 640, 360, 2),
            ):
                draw()
                self.assertEqual((painter.opacity(), painter.transform(), painter.compositionMode(),
                                  painter.pen(), painter.brush(), painter.renderHints()), state)
        finally:
            painter.end()

    def test_asset_reader_retains_only_logo_crop_and_native_coordinates(self):
        self.assertFalse(self.visuals.logo_mask.isNull())
        self.assertFalse(self.visuals.logo_glow.isNull())
        self.assertEqual(self.visuals.native_size, QSize(3840, 2160))
        self.assertEqual(self.visuals.crop_rect.getRect(), (180, 140, 1255, 980))
        self.assertEqual(self.visuals.logo_mask.size(), QSize(1255, 980))
        self.assertEqual(self.visuals.logo_glow.size(), QSize(1255, 980))
        self.assertEqual(self.source_bytes, 1255*980*4*2)
        self.assertLess(self.source_bytes, (3840*2160*4*2)/5)

    def test_constructor_crops_inputs_without_retaining_full_shared_storage(self):
        # A scaled synthetic source proves the constructor contract with less
        # than 1 MiB of input, rather than decoding two more 4K asset pixmaps.
        source = QPixmap(384, 216)
        source.fill(Qt.GlobalColor.white)
        visual = WallpaperVisuals(source, source)
        self.assertEqual(visual.native_size, QSize(384, 216))
        self.assertEqual(visual.logo_mask.size(), QSize(126, 98))
        self.assertEqual(visual.logo_glow.size(), QSize(126, 98))
        self.assertLess(visual.cache_bytes(), 384*216*4*2/5)

    def test_4k_and_high_dpi_atlas_stays_bounded_and_reuses_one_viewport(self):
        canvas = QPixmap(32, 32)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        try:
            for width, height, dpr in ((3840, 2160, 1), (1920, 1080, 2), (3840, 2160, 2)):
                with self.subTest(width=width, height=height, dpr=dpr):
                    before = self.visuals.cache_builds
                    target = QRectF(0, 0, width, height)
                    self.visuals.paint_logo(painter, target, 2, .85, dpr)
                    self.visuals.paint_particles(painter, width, height, 2, .85, dpr)
                    self.assertEqual(self.visuals.cache_builds, before+1)
                    self.assertEqual(len(self.visuals._logo_frames), 3)
                    self.assertTrue(all(max(frame.width(), frame.height()) <= 1024
                                        for frame in self.visuals._logo_frames))
                    self.assertLess(self.visuals.cache_bytes(), 22*1024**2)
                    frames = tuple(frame.cacheKey() for frame in self.visuals._logo_frames)
                    self.visuals.paint_logo(painter, target, 2.1, .85, dpr)
                    self.assertEqual(self.visuals.cache_builds, before+1)
                    self.assertEqual(tuple(frame.cacheKey() for frame in self.visuals._logo_frames), frames)
                    self.visuals.invalidate()
                    self.assertEqual(self.visuals.cache_bytes(), self.source_bytes)
        finally:
            painter.end()

    def test_ultrawide_particles_do_not_rebuild_the_star_cache(self):
        canvas = QPixmap(32, 32)
        canvas.fill(Qt.GlobalColor.transparent)
        painter = QPainter(canvas)
        try:
            target = QRectF(0, -124, 1720, 968)
            for phase in (2, 2.01):
                self.visuals.paint_logo(painter, target, phase)
                star_keys = tuple(sprite.cacheKey() for sprite, _ in self.visuals._star_sprites)
                self.visuals.paint_particles(painter, 1720, 720, phase)
                self.assertEqual(tuple(sprite.cacheKey() for sprite, _ in self.visuals._star_sprites), star_keys)
        finally:
            painter.end()

    def test_invalidation_immediately_releases_all_rendered_pixmaps(self):
        self.render(2)
        self.assertGreater(self.visuals.cache_bytes(), self.source_bytes)
        self.visuals.invalidate()
        self.assertEqual(self.visuals.cache_bytes(), self.source_bytes)
        self.assertEqual(self.visuals._logo_frames, [])
        self.assertEqual(self.visuals._particle_sprites, [])
        self.assertEqual(self.visuals._star_sprites, [])


if __name__ == "__main__":
    unittest.main()
