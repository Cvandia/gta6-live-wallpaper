"""Cached neon, travelling VI sparkles, and luminous wallpaper particles.

The caller owns all timing and switches.  Passing the same phase always draws
the same frame, including while the app is paused or exporting a screenshot.
Large transparent surfaces are built only when the target size or DPR changes.
"""
from __future__ import annotations

import math
from pathlib import Path
import random

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor, QImageReader, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
    QRadialGradient,
)


_PALETTE = ("#3edfff", "#ff4fcf", "#9b6dff", "#ff9de5", "#55edff", "#db62ff")
_PARTICLE_COLORS = ("#91eeff", "#ff9bdf", "#c0a6ff", "#ffe6be")
# Actual centre lines of the artwork's VI strokes, in its native 3840x2160
# coordinates.  Separate runs preserve the intentional gaps around the words.
_VI_RUNS = (
    ((563, 298), (518, 219), (265, 219), (654, 1017), (713, 910)),
    ((747, 299), (792, 219), (1049, 219), (1003, 299)),
    ((1124, 309), (1124, 219), (1361, 219), (1361, 1043), (1101, 1043), (1101, 908)),
)


class _Track:
    def __init__(self, vertices):
        self.vertices = vertices
        self.lengths = [0.0]
        for a, b in zip(vertices, vertices[1:]):
            self.lengths.append(self.lengths[-1] + math.hypot(b[0]-a[0], b[1]-a[1]))
        self.total = self.lengths[-1]

    def point(self, distance):
        distance = min(self.total, max(0.0, distance))
        for i in range(len(self.vertices)-1):
            if distance <= self.lengths[i+1]:
                a, b = self.vertices[i], self.vertices[i+1]
                blend = (distance-self.lengths[i])/(self.lengths[i+1]-self.lengths[i])
                return a[0]+(b[0]-a[0])*blend, a[1]+(b[1]-a[1])*blend
        return self.vertices[-1]


def _blank(width, height, dpr):
    pixmap = QPixmap(max(1, round(width*dpr)), max(1, round(height*dpr)))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    return pixmap


def _gradient(width, height, variant):
    result = QLinearGradient(0, height*.1, width, height*.85)
    for stop in range(7):
        result.setColorAt(stop/6, QColor(_PALETTE[(stop+variant) % len(_PALETTE)]))
    return result


def _tint(mask, width, height, variant, dpr):
    result = _blank(width, height, dpr)
    painter = QPainter(result)
    painter.fillRect(QRectF(0, 0, width, height), _gradient(width, height, variant))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    painter.drawPixmap(0, 0, mask)
    painter.end()
    return result


class WallpaperVisuals:
    """Reusable drawing cache for a single wallpaper window.

    ``target`` is the full artwork's destination QRectF, including cover-crop.
    Strength uses 0..1; 0.85 is the intended visible default.  Qt coordinates
    are logical pixels, and dpr is QWidget.devicePixelRatioF().
    """

    particle_count = 64
    max_logo_cache_edge = 1024

    def __init__(self, logo_mask: QPixmap, logo_glow: QPixmap, *,
                 native_size=None, crop_rect=None, inputs_cropped=False):
        self.native_size = QSize(native_size or logo_mask.size())
        if self.native_size.isEmpty():
            self.native_size = QSize(3840, 2160)
        self.crop_rect = QRect(crop_rect) if crop_rect is not None else self._crop_for(self.native_size)
        # QPixmap.copy makes independent cropped storage.  Keeping a reference
        # to a shared full transparent 4K mask would otherwise retain 32 MiB.
        self.logo_mask = logo_mask if inputs_cropped else logo_mask.copy(self.crop_rect)
        self.logo_glow = logo_glow if inputs_cropped else logo_glow.copy(self.crop_rect)
        self._logo_key = None
        self._logo_frames = []
        self._logo_local_rect = QRectF()
        self._sprite_key = None
        self._star_key = None
        self._particle_sprites = []
        self._star_sprites = []
        self._tracks = [_Track(vertices) for vertices in _VI_RUNS]
        self.cache_builds = 0
        rng = random.Random(61016)
        # Immutable seeds, no advancing random state: phase determines motion.
        self._particles = tuple(
            (rng.random(), rng.random(), rng.randrange(3), rng.randrange(4),
             rng.uniform(.014, .039), rng.random()*math.tau,
             rng.uniform(.25, .65))
            for _ in range(self.particle_count)
        )

    @staticmethod
    def _crop_for(native_size):
        return QRect(round(native_size.width()*180/3840),
                     round(native_size.height()*140/2160),
                     round(native_size.width()*1255/3840),
                     round(native_size.height()*980/2160))

    @classmethod
    def from_assets(cls, assets):
        """Read only each mask's useful rectangle into persistent Qt storage.

        QImageReader may internally decode a PNG before clipping, but the full
        temporary QImage is released by read(); no full QPixmap is created.
        """
        masks = []
        native_size = crop_rect = None
        for filename in ("logo-mask.png", "logo-glow-mask.png"):
            reader = QImageReader(str(Path(assets) / filename))
            source_size = reader.size()
            if native_size is None and not source_size.isEmpty():
                native_size = QSize(source_size)
                crop_rect = cls._crop_for(native_size)
            if crop_rect is not None:
                reader.setClipRect(crop_rect)
            image = reader.read()
            if crop_rect is not None and image.size() == source_size:
                # Defensive fallback for image plugins that ignore ClipRect.
                image = image.copy(crop_rect)
            masks.append(QPixmap.fromImage(image))
        return cls(*masks, native_size=native_size, crop_rect=crop_rect,
                   inputs_cropped=True)

    def cache_bytes(self):
        """Estimate resident pixmap pixels, excluding transient decode buffers."""
        pixmaps = [self.logo_mask, self.logo_glow, *self._logo_frames]
        pixmaps.extend(sprite for row in self._particle_sprites for sprite, _ in row)
        pixmaps.extend(sprite for sprite, _ in self._star_sprites)
        # Count implicit-shared pixmaps once; Qt/raster bookkeeping is separate.
        unique = {pixmap.cacheKey(): pixmap for pixmap in pixmaps if not pixmap.isNull()}
        return sum(p.width()*p.height()*max(1, p.depth()//8) for p in unique.values())

    def invalidate(self):
        """Optional explicit invalidation; target size/DPR auto-invalidate."""
        self._logo_key = self._sprite_key = self._star_key = None
        self._logo_frames.clear()
        self._particle_sprites.clear()
        self._star_sprites.clear()

    def _ensure_logo(self, target, dpr):
        if self.logo_mask.isNull():
            return False
        key = (round(target.width(), 3), round(target.height(), 3), round(dpr, 3))
        if self._logo_key == key:
            return True
        # Free the previous viewport's atlas before allocating its replacement.
        self._logo_frames.clear()
        self._logo_key = None
        # Crop around the effect's nonempty alpha.  Never cache full 4K canvases.
        native = self.native_size
        sx, sy = target.width()/native.width(), target.height()/native.height()
        crop = self.crop_rect
        width, height = crop.width()*sx, crop.height()*sy
        # Halo and thin rim remain smooth at this resolution, while a 4K/DPR2
        # monitor cannot multiply a large transparent atlas without a bound.
        cache_dpr = min(dpr, self.max_logo_cache_edge/max(width, height))
        masks = []
        for source in (self.logo_mask, self.logo_glow):
            if source.isNull():
                source = self.logo_mask
            scaled = source.scaled(
                max(1, round(width*cache_dpr)), max(1, round(height*cache_dpr)),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            scaled.setDevicePixelRatio(cache_dpr)
            masks.append(scaled)
        bloom = max(.8, target.width()/3840*7)
        for variant in range(3):
            rim = _tint(masks[0], width, height, variant*2, cache_dpr)
            halo = _tint(masks[1], width, height, variant*2, cache_dpr)
            composed = _blank(width, height, cache_dpr)
            painter = QPainter(composed)
            # Cached wider bloom makes the glow visible even against the dusk
            # sky.  These blur-like offset copies run once, never per frame.
            painter.setOpacity(.24)
            for x, y in ((-bloom, 0), (bloom, 0), (0, -bloom), (0, bloom)):
                painter.drawPixmap(QPointF(x, y), halo)
            painter.setOpacity(.95)
            painter.drawPixmap(0, 0, halo)
            painter.setOpacity(1)
            painter.drawPixmap(0, 0, rim)
            painter.end()
            self._logo_frames.append(composed)
        self._logo_local_rect = QRectF(crop.x()*sx, crop.y()*sy, width, height)
        self._logo_key = key
        self.cache_builds += 1
        return True

    def _ensure_sprites(self, scale, dpr, star_only=False):
        key = (round(scale, 4), round(dpr, 3))
        if (self._star_key if star_only else self._sprite_key) == key:
            return
        if not star_only:
            self._particle_sprites = []
            for color in _PARTICLE_COLORS:
                row = []
                for size in range(3):
                    radius = (6.4+size*2.5)*scale
                    core = (.9+size*.38)*scale
                    sprite = _blank(radius*2+2, radius*2+2, dpr)
                    painter = QPainter(sprite)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    center = QPointF(radius+1, radius+1)
                    gradient = QRadialGradient(center, radius)
                    tint = QColor(color)
                    gradient.setColorAt(0, QColor(255, 248, 255, 245))
                    tint.setAlpha(150)
                    gradient.setColorAt(.16, tint)
                    tint.setAlpha(48)
                    gradient.setColorAt(.47, tint)
                    tint.setAlpha(0)
                    gradient.setColorAt(1, tint)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(gradient)
                    painter.drawEllipse(center, radius, radius)
                    painter.setBrush(QColor(255, 249, 255, 240))
                    painter.drawEllipse(center, core, core)
                    painter.end()
                    row.append((sprite, radius+1))
                self._particle_sprites.append(row)
            self._sprite_key = key
            return
        self._star_sprites = []
        for color in ("#91ecff", "#ff9ee9", "#d4bdff"):
            radius = 21*scale
            sprite = _blank(radius*2+2, radius*2+2, dpr)
            painter = QPainter(sprite)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            center = QPointF(radius+1, radius+1)
            bloom = QRadialGradient(center, radius)
            bloom.setColorAt(0, QColor(255, 246, 255, 245))
            tint = QColor(color)
            tint.setAlpha(155)
            bloom.setColorAt(.18, tint)
            tint.setAlpha(0)
            bloom.setColorAt(1, tint)
            painter.fillRect(QRectF(0, 0, radius*2+2, radius*2+2), bloom)
            painter.translate(center)
            # Four tapered points plus short diagonal rays, cached as a sprite.
            star = QPainterPath()
            star.moveTo(0, -17*scale)
            for point in ((1.4, -1.4), (12, 0), (1.4, 1.4), (0, 17),
                          (-1.4, 1.4), (-12, 0), (-1.4, -1.4)):
                star.lineTo(point[0]*scale, point[1]*scale)
            star.closeSubpath()
            painter.fillPath(star, QColor(255, 249, 255, 245))
            painter.setPen(QPen(QColor(color), max(.65, scale*.8)))
            for ax, ay, bx, by in ((-5, -5, 5, 5), (-5, 5, 5, -5)):
                painter.drawLine(QPointF(ax*scale, ay*scale), QPointF(bx*scale, by*scale))
            painter.end()
            self._star_sprites.append((sprite, radius+1))
        self._star_key = key

    def paint_logo(self, painter: QPainter, target: QRectF, phase: float,
                   strength: float = .85, dpr: float = 1.0):
        strength = min(1.0, max(0.0, strength))
        if strength == 0 or not self._ensure_logo(target, dpr):
            return
        scale = target.width()/1920
        self._ensure_sprites(max(.25, scale), dpr, star_only=True)
        # Cross-fade three already shaded gradients: no mask or big allocation in
        # the animation path. SourceOver preserves saturated halo colours.
        step = phase*.24
        first = math.floor(step) % len(self._logo_frames)
        blend = step-math.floor(step)
        breath = .88+.10*math.sin(phase*.92)+.02*math.sin(phase*5.8)
        origin = target.topLeft()+self._logo_local_rect.topLeft()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setOpacity(strength*breath*(1-blend))
        painter.drawPixmap(origin, self._logo_frames[first])
        painter.setOpacity(strength*breath*blend)
        painter.drawPixmap(origin, self._logo_frames[(first+1) % len(self._logo_frames)])
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        sx, sy = target.width()/3840, target.height()/2160
        for index, track in enumerate(self._tracks):
            distance = (phase*(91+index*9)+index*237) % track.total
            # A short sweep travels exactly along the VI's existing strokes.
            for piece in range(9, 0, -1):
                tail = distance-piece*12
                if tail < 0:
                    continue
                a, b = track.point(tail), track.point(tail+12)
                fade = (1-piece/10)**1.6
                tint = QColor(_PALETTE[(index+first) % len(_PALETTE)])
                tint.setAlpha(round(210*fade))
                painter.setOpacity(strength)
                painter.setPen(QPen(tint, max(1.1, 3.6*scale),
                                    Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(QPointF(target.x()+a[0]*sx, target.y()+a[1]*sy),
                                 QPointF(target.x()+b[0]*sx, target.y()+b[1]*sy))
            x, y = track.point(distance)
            star, half = self._star_sprites[index]
            sparkle = .66+.34*(.5+.5*math.sin(phase*(2.1+index*.3)+index*1.5))**3
            painter.setOpacity(strength*sparkle)
            painter.drawPixmap(QPointF(target.x()+x*sx-half, target.y()+y*sy-half), star)
        painter.restore()

    def paint_particles(self, painter: QPainter, width: float, height: float,
                        phase: float, strength: float = .85, dpr: float = 1.0):
        strength = min(1.0, max(0.0, strength))
        if strength == 0 or width <= 0 or height <= 0:
            return
        scale = max(.25, min(width/1920, height/1080))
        self._ensure_sprites(scale, dpr)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        for x, y, size, color, speed, offset, twinkle in self._particles:
            px = ((x+.010*math.sin(phase*.24+offset)) % 1)*width
            py = ((y-phase*speed*.34) % 1)*height
            alpha = (.43+.42*(.5+.5*math.sin(phase*twinkle+offset)))*strength
            # The faint downward tail makes the upward drift readable without
            # turning the particles into a rain overlay.
            tint = QColor(_PARTICLE_COLORS[color])
            tint.setAlpha(83)
            painter.setOpacity(alpha*.75)
            painter.setPen(QPen(tint, max(.65, (.7+size*.2)*scale),
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(px, py+scale),
                             QPointF(px-1.8*scale*math.cos(phase*.24+offset),
                                     py+(4.5+size*2.4)*scale))
            sprite, half = self._particle_sprites[color][size]
            painter.setOpacity(alpha)
            painter.drawPixmap(QPointF(px-half, py-half), sprite)
        painter.restore()
