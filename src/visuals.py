"""Web-matched VI light and shared, deterministic luminous particles.

All timing/style data comes from assets/effects-spec.json. The caller supplies
animation time, so pausing and frozen screenshots require no separate clock.
Three reusable colour buffers and their blurred alpha masks are size-bounded;
animation never allocates a new large pixmap or accumulates coloured frames.
"""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor, QImageReader, QLinearGradient, QPainter, QPainterPath, QPen,
    QPixmap, QRadialGradient,
)
from PySide6.QtWidgets import QGraphicsBlurEffect, QGraphicsPixmapItem, QGraphicsScene

from effects_spec import (
    load_effects_spec, logo_state, particle_states, sparkle_states,
)


def _blank(width, height, dpr):
    result = QPixmap(max(1, round(width*dpr)), max(1, round(height*dpr)))
    result.setDevicePixelRatio(dpr)
    result.fill(Qt.GlobalColor.transparent)
    return result


def _filtered_color(color, saturation=1.0, brightness=1.0):
    """CSS saturate()/brightness() colour matrix, applied to gradient stops."""
    color = QColor(color)
    r, g, b = color.redF(), color.greenF(), color.blueF()
    luminance = .213*r+.715*g+.072*b
    return QColor.fromRgbF(*(min(1.0, max(0.0, (luminance+(c-luminance)*saturation)*brightness))
                              for c in (r, g, b)), color.alphaF())


def _css_gradient(width, height, padding, progress, flow, layer):
    # CSS background-position moves the 260%-wide image by (box-image)*p.
    # A CSS angle is clockwise from up; 105 degrees therefore slopes down/right.
    image_w, image_h = width*flow["background_scale"][0], height*flow["background_scale"][1]
    angle = math.radians(flow["angle_deg"])
    dx, dy = math.sin(angle), -math.cos(angle)
    length = abs(image_w*dx)+abs(image_h*dy)
    cx = padding+(width-image_w)*progress+image_w/2
    cy = padding+(height-image_h)*.5+image_h/2
    gradient = QLinearGradient(cx-dx*length/2, cy-dy*length/2,
                               cx+dx*length/2, cy+dy*length/2)
    stops = flow["stops"]
    # Intermediate stops preserve colour-filter clipping between CSS stops.
    for index, (position, color) in enumerate(stops):
        if index:
            previous, previous_color = stops[index-1]
            a, b = QColor(previous_color), QColor(color)
            for step in (1, 2, 3):
                amount = step/4
                mixed = QColor.fromRgbF(a.redF()+(b.redF()-a.redF())*amount,
                                       a.greenF()+(b.greenF()-a.greenF())*amount,
                                       a.blueF()+(b.blueF()-a.blueF())*amount)
                gradient.setColorAt(previous+(position-previous)*amount,
                                    _filtered_color(mixed, layer["saturation"], layer["brightness"]))
        gradient.setColorAt(position, _filtered_color(color, layer["saturation"], layer["brightness"]))
    return gradient


def _blurred_alpha(source, width, height, blur, padding, dpr):
    """Pre-render a padded soft mask once at the layer's bounded resolution."""
    total_w, total_h = width+padding*2, height+padding*2
    result = _blank(total_w, total_h, dpr)
    # Work in physical scene units; the result receives its logical DPR after
    # rendering. Qt's blur radius is approximately twice a CSS Gaussian sigma.
    result.setDevicePixelRatio(1)
    scaled = source.scaled(max(1, round(width*dpr)), max(1, round(height*dpr)),
                           Qt.AspectRatioMode.IgnoreAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
    scaled.setDevicePixelRatio(1)
    # Put padding into source pixels, rather than an item's scene position:
    # QGraphicsBlurEffect's offscreen source offset can otherwise discard that
    # translation and leave a displaced duplicate silhouette in the aura.
    padded = QPixmap(result.size())
    padded.fill(Qt.GlobalColor.transparent)
    pp = QPainter(padded)
    pp.drawPixmap(QPointF(padding*dpr, padding*dpr), scaled)
    pp.end()
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(padded)
    effect = QGraphicsBlurEffect()
    effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
    effect.setBlurRadius(max(.01, blur*dpr*2))
    item.setGraphicsEffect(effect)
    scene.addItem(item)
    bounds = QRectF(0, 0, result.width(), result.height())
    scene.setSceneRect(bounds)
    painter = QPainter(result)
    scene.render(painter, bounds, bounds)
    painter.end()
    result.setDevicePixelRatio(dpr)
    return result


def _path(vertices, scale):
    path = QPainterPath()
    path.moveTo(vertices[0][0]*scale, vertices[0][1]*scale)
    for x, y in vertices[1:]:
        path.lineTo(x*scale, y*scale)
    path.closeSubpath()
    return path


class WallpaperVisuals:
    particle_count = 64
    max_logo_cache_edge = 1024

    def __init__(self, logo_mask: QPixmap, logo_glow: QPixmap, *,
                 native_size=None, crop_rect=None, inputs_cropped=False,
                 effects_spec=None):
        self.spec = effects_spec if effects_spec is not None else load_effects_spec()
        self.particle_count = self.spec["particles"]["count"]
        self.native_size = QSize(native_size or logo_mask.size())
        if self.native_size.isEmpty():
            self.native_size = QSize(*self.spec["logo"]["canvas"])
        self.crop_rect = QRect(crop_rect) if crop_rect is not None else self._crop_for(self.native_size, self.spec)
        self.logo_mask = logo_mask if inputs_cropped else logo_mask.copy(self.crop_rect)
        self.logo_glow = logo_glow if inputs_cropped else logo_glow.copy(self.crop_rect)
        self._logo_key = None
        self._logo_frames = []  # Three reusable working surfaces, not a growing frame atlas.
        self._logo_masks = []
        self._logo_metadata = []
        self._logo_phases = []
        self._logo_local_rect = QRectF()
        self._sprite_key = self._star_key = None
        self._particle_sprites = []
        self._star_sprites = []
        self._particles = tuple(tuple(seed) for seed in self.spec["particles"]["seeds"])
        self.cache_builds = 0

    @staticmethod
    def _crop_for(native_size, spec=None):
        logo = (spec if spec is not None else load_effects_spec())["logo"]
        x, y, width, height = logo["crop"]
        native_w, native_h = logo["canvas"]
        return QRect(round(native_size.width()*x/native_w), round(native_size.height()*y/native_h),
                     round(native_size.width()*width/native_w), round(native_size.height()*height/native_h))

    @classmethod
    def from_assets(cls, assets):
        spec = load_effects_spec(Path(assets) / "effects-spec.json")
        masks = []
        native_size = crop_rect = None
        for filename in ("logo-mask.png", "logo-glow-mask.png"):
            reader = QImageReader(str(Path(assets) / filename))
            source_size = reader.size()
            if native_size is None and not source_size.isEmpty():
                native_size = QSize(source_size)
                crop_rect = cls._crop_for(native_size, spec)
            if crop_rect is not None:
                reader.setClipRect(crop_rect)
            image = reader.read()
            if crop_rect is not None and image.size() == source_size:
                image = image.copy(crop_rect)
            masks.append(QPixmap.fromImage(image))
        return cls(*masks, native_size=native_size, crop_rect=crop_rect,
                   inputs_cropped=True, effects_spec=spec)

    def cache_bytes(self):
        """Estimate resident CPU pixmap pixels, excluding temporary PNG decode."""
        pixmaps = [self.logo_mask, self.logo_glow, *self._logo_frames, *self._logo_masks]
        pixmaps.extend(sprite for row in self._particle_sprites for sprite, _ in row)
        pixmaps.extend(sprite for sprite, _ in self._star_sprites)
        unique = {pixmap.cacheKey(): pixmap for pixmap in pixmaps if not pixmap.isNull()}
        return sum(p.width()*p.height()*max(1, p.depth()//8) for p in unique.values())

    def invalidate(self):
        self._logo_key = self._sprite_key = self._star_key = None
        self._logo_frames.clear()
        self._logo_masks.clear()
        self._logo_metadata.clear()
        self._logo_phases.clear()
        self._particle_sprites.clear()
        self._star_sprites.clear()

    def _ensure_logo(self, target, dpr, viewport_width=None):
        if self.logo_mask.isNull():
            return False
        viewport_width = viewport_width or target.width()
        key = (round(target.width(), 3), round(target.height(), 3), round(dpr, 3), round(viewport_width, 3))
        if self._logo_key == key:
            return True
        self._logo_frames.clear()
        self._logo_masks.clear()
        self._logo_metadata.clear()
        self._logo_phases.clear()
        self._logo_key = None
        sx, sy = target.width()/self.native_size.width(), target.height()/self.native_size.height()
        width, height = self.crop_rect.width()*sx, self.crop_rect.height()*sy
        self._logo_local_rect = QRectF(self.crop_rect.x()*sx, self.crop_rect.y()*sy, width, height)
        limits = {"aura": 256, "halo": 512, "edge": self.max_logo_cache_edge}
        for layer in self.spec["logo"]["layers"]:
            blur = max(layer["blur_min"], layer["blur_width"]*viewport_width)
            padding = math.ceil(blur*3+2)
            total_w, total_h = width+padding*2, height+padding*2
            cache_dpr = min(dpr, limits[layer["name"]]/max(total_w, total_h))
            source = self.logo_mask if layer["mask"] == "logo-mask.png" else self.logo_glow
            if source.isNull():
                source = self.logo_mask
            mask = _blurred_alpha(source, width, height, blur, padding, cache_dpr)
            self._logo_masks.append(mask)
            self._logo_frames.append(_blank(total_w, total_h, cache_dpr))
            self._logo_metadata.append((layer, width, height, padding, total_w, total_h))
            self._logo_phases.append(None)
        self._logo_key = key
        self.cache_builds += 1
        return True

    def _ensure_sprites(self, scale, dpr, star_only=False):
        key = (round(scale, 4), round(dpr, 3))
        if (self._star_key if star_only else self._sprite_key) == key:
            return
        if not star_only:
            self._particle_sprites.clear()
            particles = self.spec["particles"]
            style = particles["sprite"]
            for color in particles["colors"]:
                row = []
                for size in range(style["size_count"]):
                    radius = (style["radius_base"]+size*style["radius_step"])*scale
                    core = (style["core_base"]+size*style["core_step"])*scale
                    half = radius+style["padding"]
                    sprite = _blank(half*2, half*2, dpr)
                    painter = QPainter(sprite)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    center = QPointF(half, half)
                    gradient = QRadialGradient(center, radius)
                    for stop in style["stops"]:
                        tint = QColor(*stop["color"]) if "color" in stop else QColor(color)
                        if "tint_alpha" in stop:
                            tint.setAlpha(stop["tint_alpha"])
                        gradient.setColorAt(stop["at"], tint)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(gradient)
                    painter.drawEllipse(center, radius, radius)
                    painter.setBrush(QColor(*style["core_color"]))
                    painter.drawEllipse(center, core, core)
                    painter.end()
                    row.append((sprite, half))
                self._particle_sprites.append(row)
            self._sprite_key = key
            return
        self._star_sprites.clear()
        shape = self.spec["logo"]["sparkles"]["shape"]
        radius = max(abs(coordinate) for point in shape["main"] for coordinate in point)*scale
        padding = sum(shadow["blur"] for shadow in shape["shadows"])*scale*3+2
        half = radius+padding
        core = _blank(half*2, half*2, dpr)
        painter = QPainter(core)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(half, half)
        painter.fillPath(_path(shape["main"], scale), QColor(shape["fill"]))
        painter.save()
        painter.rotate(shape["diagonal_rotation"])
        painter.setOpacity(shape["diagonal_opacity"])
        painter.fillPath(_path(shape["diagonal"], scale), QColor(shape["diagonal_fill"]))
        painter.restore()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(shape["fill"]))
        painter.drawEllipse(QPointF(0, 0), shape["center_radius"]*scale, shape["center_radius"]*scale)
        painter.end()
        sprite = _blank(half*2, half*2, dpr)
        painter = QPainter(sprite)
        for shadow in reversed(shape["shadows"]):
            blurred = _blurred_alpha(core, half*2, half*2, shadow["blur"]*scale, 0, dpr)
            sp = QPainter(blurred)
            sp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            sp.fillRect(QRectF(0, 0, half*2, half*2), QColor(shadow["color"]))
            sp.end()
            painter.drawPixmap(0, 0, blurred)
        painter.drawPixmap(0, 0, core)
        painter.end()
        self._star_sprites.append((sprite, half))
        self._star_key = key

    def paint_logo(self, painter: QPainter, target: QRectF, phase: float,
                   strength: float = .85, dpr: float = 1.0):
        strength = min(1.0, max(0.0, strength))
        device = painter.device()
        viewport_width = device.width()/device.devicePixelRatioF() if isinstance(device, QPixmap) else device.width()
        if strength == 0 or not self._ensure_logo(target, dpr, viewport_width):
            return
        canvas_w, canvas_h = self.spec["logo"]["canvas"]
        self._ensure_sprites(max(.025, target.width()/canvas_w), dpr, star_only=True)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        origin = target.topLeft()+self._logo_local_rect.topLeft()
        for index, (layer, width, height, padding, total_w, total_h) in enumerate(self._logo_metadata):
            state = logo_state(phase, layer["name"], strength, self.spec)
            buffer = self._logo_frames[index]
            if self._logo_phases[index] != phase:
                buffer.fill(Qt.GlobalColor.transparent)
                bp = QPainter(buffer)
                bp.fillRect(QRectF(0, 0, total_w, total_h),
                            _css_gradient(width, height, padding, state["flow"], self.spec["logo"]["flow"], layer))
                bp.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
                # Qt's point overload does not consistently expand pixmaps
                # with DPR below one. Give both the mask and output their
                # explicit logical destination to keep low-memory layers aligned.
                bp.drawPixmap(QRectF(0, 0, total_w, total_h),
                              self._logo_masks[index], QRectF(self._logo_masks[index].rect()))
                bp.end()
                self._logo_phases[index] = phase
            painter.setOpacity(state["opacity"])
            painter.drawPixmap(QRectF(origin.x()-padding, origin.y()-padding, total_w, total_h),
                               buffer, QRectF(buffer.rect()))
        star, half = self._star_sprites[0]
        for state in sparkle_states(phase, strength, self.spec):
            # All sixteen positions stay fixed on the original outline. Only
            # the SVG-equivalent scale, rotation, and opacity change with time.
            painter.save()
            painter.translate(target.x()+state["x"]*target.width()/canvas_w,
                              target.y()+state["y"]*target.height()/canvas_h)
            painter.rotate(state["rotate_deg"])
            painter.scale(state["scale"], state["scale"])
            painter.setOpacity(state["opacity"])
            painter.drawPixmap(QPointF(-half, -half), star)
            painter.restore()
        painter.restore()

    def paint_particles(self, painter: QPainter, width: float, height: float,
                        phase: float, strength: float = .85, dpr: float = 1.0):
        strength = min(1.0, max(0.0, strength))
        if strength == 0 or width <= 0 or height <= 0:
            return
        style = self.spec["particles"]
        reference_w, reference_h = style["scale"]["reference"]
        scale = max(style["scale"]["minimum"], min(width/reference_w, height/reference_h))
        self._ensure_sprites(scale, dpr)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        for state in particle_states(phase, width, height, strength, self.spec):
            color, size, tail = state["color"], state["size"], state["tail"]
            painter.setOpacity(tail["alpha"])
            painter.setPen(QPen(QColor(style["colors"][color]), tail["width"],
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(tail["x1"], tail["y1"]), QPointF(tail["x2"], tail["y2"]))
            sprite, half = self._particle_sprites[color][size]
            painter.setOpacity(state["alpha"])
            painter.drawPixmap(QPointF(state["x"]-half, state["y"]-half), sprite)
        painter.restore()
