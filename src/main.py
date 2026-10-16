from __future__ import annotations

import argparse
import json
import logging
import math
import os
from pathlib import Path
import sys
import time
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QDateTime, QUrl
from PySide6.QtGui import (QColor, QPainter, QPixmap, QFont, QFontDatabase, QFontMetricsF,
                           QLinearGradient, QRadialGradient, QIcon, QDesktopServices, QCursor,
                           QPainterPath, QPen, QImageReader)
from PySide6.QtWidgets import (QApplication, QWidget, QMenu, QSystemTrayIcon,
    QDialog, QVBoxLayout, QFormLayout, QLabel, QCheckBox, QComboBox, QDateTimeEdit,
    QDialogButtonBox, QMessageBox, QSlider)

from model import BEIJING, DEFAULT_TARGET, RELEASE_SOURCE, ART_SOURCE, parse_target, snapshot, format_target
from effects import cursor_target, smooth_position, glow_pulse
from visuals import WallpaperVisuals
from memory import load_scaled_pixmap
from effects_spec import load_effects_spec

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
ASSETS = ROOT / "assets"
TITLE = "GTA VI · 北京时间倒计时"
DEFAULTS = dict(target=DEFAULT_TARGET, effects=True, clock=True, fps=20, text_scale=100,
                neon=True, glow_strength=85, parallax=True, parallax_strength=12)


class SettingsDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner if not owner.embedded else None)
        self.setWindowTitle("GTA VI 壁纸设置")
        self.setMinimumWidth(450)
        self.setStyleSheet("QDialog{background:#201d36;color:#fbf4ff} QLabel,QCheckBox{color:#fbf4ff} QDateTimeEdit,QComboBox{padding:8px} QPushButton{padding:7px 14px}")
        layout = QVBoxLayout(self)
        title = QLabel("GTA VI  ·  欢迎来到莱昂尼达")
        title.setStyleSheet("font-size:20px;font-weight:700;padding:12px 0")
        layout.addWidget(title)
        form = QFormLayout()
        self.date = QDateTimeEdit()
        dt = owner.target.astimezone(BEIJING)
        self.date.setDateTime(QDateTime.fromString(dt.strftime("%Y-%m-%d %H:%M:%S"), "yyyy-MM-dd HH:mm:ss"))
        self.date.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.date.setCalendarPopup(True)
        form.addRow("目标时间（北京时间）", self.date)
        self.effects = QCheckBox("开启动态效果")
        self.effects.setChecked(owner.config["effects"])
        form.addRow("动态效果", self.effects)
        self.neon = QCheckBox("VI 标志与数字渐变轮廓光")
        self.neon.setChecked(owner.config["neon"])
        form.addRow("霓虹光效", self.neon)
        self.glow = QSlider(Qt.Orientation.Horizontal)
        self.glow.setRange(0, 100)
        self.glow.setValue(owner.config["glow_strength"])
        form.addRow("发光强度", self.glow)
        self.parallax = QCheckBox("人物轻微跟随鼠标左右移动")
        self.parallax.setChecked(owner.config["parallax"])
        self.parallax.setEnabled(owner.layers_ready)
        form.addRow("人物视差", self.parallax)
        self.motion = QSlider(Qt.Orientation.Horizontal)
        self.motion.setRange(0, 25)
        self.motion.setValue(owner.config["parallax_strength"])
        form.addRow("移动幅度", self.motion)
        self.clock = QCheckBox("显示北京时间与日期")
        self.clock.setChecked(owner.config["clock"])
        form.addRow("右上角时钟", self.clock)
        self.fps = QComboBox()
        self.fps.addItems(["省电 · 10 FPS", "均衡 · 20 FPS", "流畅 · 30 FPS"])
        self.fps.setCurrentIndex([10, 20, 30].index(owner.config["fps"]))
        form.addRow("动画帧率", self.fps)
        self.scale = QSlider(Qt.Orientation.Horizontal)
        self.scale.setRange(75, 115)
        self.scale.setValue(owner.config["text_scale"])
        form.addRow("倒计时大小", self.scale)
        layout.addLayout(form)
        note = QLabel("默认 2026-11-19 00:00（UTC+8）\n来源：港区 PS Store 标准版列示时间。\n日期核查：2026-10-15；其他平台及地区以各商店为准。\n进度起点：2023-12-04 首支预告发布日。")
        note.setWordWrap(True)
        note.setStyleSheet("color:#c1b2d7;line-height:1.6;padding:12px 0")
        layout.addWidget(note)
        links = QLabel(f'<a style="color:#ff87c8" href="{RELEASE_SOURCE}">查看发售时间来源</a>　 <a style="color:#ff87c8" href="{ART_SOURCE}">查看原画来源</a>')
        links.setOpenExternalLinks(True)
        layout.addWidget(links)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.RestoreDefaults)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).setText("恢复默认")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(self.reset)
        layout.addWidget(buttons)

    def reset(self):
        self.date.setDateTime(QDateTime.fromString("2026-11-19 00:00:00", "yyyy-MM-dd HH:mm:ss"))
        self.effects.setChecked(True)
        self.neon.setChecked(True)
        self.glow.setValue(85)
        self.parallax.setChecked(True)
        self.motion.setValue(12)
        self.clock.setChecked(True)
        self.fps.setCurrentIndex(1)
        self.scale.setValue(100)

    def values(self):
        return dict(target=self.date.dateTime().toString("yyyy-MM-ddTHH:mm:ss") + "+08:00",
                    effects=self.effects.isChecked(), clock=self.clock.isChecked(),
                    fps=[10, 20, 30][self.fps.currentIndex()], text_scale=self.scale.value(),
                    neon=self.neon.isChecked(), glow_strength=self.glow.value(),
                    parallax=self.parallax.isChecked(), parallax_strength=self.motion.value())


class Wallpaper(QWidget):
    def __init__(self, args):
        super().__init__()
        self.args = args
        self.embedded = bool(args.parentHWND or args.desktop)
        self.parent_hwnd = args.parentHWND or 0
        self.engine_viewport = None
        self.wall_rect = None
        self.setWindowTitle(TITLE)
        self.setWindowIcon(QIcon(str(ASSETS / "icon.ico")))
        if self.embedded or args.fullscreen:
            self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.resize(args.wpe_w or 1280, args.wpe_h or 720)
        self.setMinimumSize(480, 300)
        self.config_path = Path(args.config_dir) / "settings.json" if args.config_dir else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "GTA6Wallpaper" / "settings.json"
        self.config = dict(DEFAULTS)
        try:
            stored = json.loads(self.config_path.read_text(encoding="utf-8"))
            if not isinstance(stored, dict):
                raise ValueError("无效的设置文件")
            parse_target(stored.get("target", DEFAULT_TARGET))
            for key in DEFAULTS:
                if key in stored and type(stored[key]) is type(DEFAULTS[key]):
                    self.config[key] = stored[key]
        except (OSError, ValueError, TypeError):
            pass
        if self.config["fps"] not in [10, 20, 30]:
            self.config["fps"] = 20
        self.config["text_scale"] = min(115, max(75, self.config["text_scale"]))
        self.config["glow_strength"] = min(100, max(0, self.config["glow_strength"]))
        self.config["parallax_strength"] = min(25, max(0, self.config["parallax_strength"]))
        self.target = parse_target(self.config["target"])
        # Read dimensions without retaining the full 4K promotional bitmap.
        self.art_size = QImageReader(str(ASSETS / "background.jpg")).size()
        if not self.art_size.isValid():
            raise RuntimeError("缺少背景原画，请重新解压完整文件包")
        self.layers_ready = all(QImageReader(str(ASSETS / name)).canRead()
                                for name in ("scene-background.jpg", "characters.png"))
        self.visuals = WallpaperVisuals.from_assets(ASSETS)
        self.background_cache = None
        self.foreground_cache = None
        self.text_paths = {}
        self.started = time.monotonic()
        self.last_frame = self.started
        self.animation_time = args.phase
        self.parallax_position = max(-1.0, min(1.0, args.parallax_x or 0.0))
        self.now = datetime.now(BEIJING)
        self.frozen_now = parse_target(args.at) if args.at else None
        self.hover = False
        self.paused = False
        self.numbers = "Anton"
        if (ASSETS / "Anton-Regular.ttf").exists():
            fid = QFontDatabase.addApplicationFont(str(ASSETS / "Anton-Regular.ttf"))
            families = QFontDatabase.applicationFontFamilies(fid)
            if families:
                self.numbers = families[0]
        self.tick = QTimer(self)
        self.tick.timeout.connect(self.on_tick)
        self.tick.start(250)
        self.animation = QTimer(self)
        self.animation.timeout.connect(self.on_animation)
        self.animation.start(round(1000 / self.config["fps"]))
        self.host_timer = QTimer(self)
        self.host_timer.timeout.connect(self.sync_host)
        self.menu = self.make_menu()
        self.tray = None
        if not args.parentHWND and not args.screenshot and QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self.windowIcon(), self)
            self.tray.setToolTip(TITLE + " · 右键设置/退出")
            self.tray.setContextMenu(self.menu)
            self.tray.activated.connect(lambda reason: self.settings() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
            self.tray.show()

    def make_menu(self):
        menu = QMenu(self)
        menu.addAction("壁纸设置…", self.settings)
        if not self.args.parentHWND:
            menu.addAction("独立设为桌面壁纸", self.attach_desktop)
            menu.addAction("窗口预览", self.detach_preview)
        menu.addAction("打开官方发售时间", lambda: QDesktopServices.openUrl(QUrl(RELEASE_SOURCE)))
        menu.addSeparator()
        menu.addAction("退出壁纸", QApplication.instance().quit)
        return menu

    def settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.config = dialog.values()
            self.target = parse_target(self.config["target"])
            try:
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                self.config_path.write_text(json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError as error:
                QMessageBox.warning(dialog, "设置未能保存", str(error))
            self.visuals.invalidate()
            self.text_paths.clear()
            self.animation.setInterval(round(1000 / self.config["fps"]))
            self.update()

    def setup_host(self):
        if self.args.parentHWND:
            try:
                import winwall
                winwall.attach(int(self.winId()), self.parent_hwnd)
                host_size = winwall.client_size(self.parent_hwnd)
                supplied = (self.args.wpe_w, self.args.wpe_h)
                if all(v > 0 for v in supplied) and (self.args.wpe_x or self.args.wpe_y or supplied != host_size):
                    self.engine_viewport = (self.args.wpe_x, self.args.wpe_y, *supplied)
                self.sync_host()
                self.host_timer.start(250)
            except Exception:
                logging.exception("Unable to attach Wallpaper Engine host")
                QApplication.instance().exit(1)
        elif self.args.desktop:
            self.attach_desktop()

    def attach_desktop(self):
        try:
            import winwall
            parent = winwall.desktop_parent()
            self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
            self.show()
            winwall.attach(int(self.winId()), parent)
            self.parent_hwnd = parent
            self.embedded = True
            screen = QApplication.primaryScreen()
            self.wall_rect = screen.geometry()
            self.sync_host()
            self.host_timer.start(500)
            if self.tray:
                self.tray.showMessage("GTA VI 壁纸已启动", "右键托盘 VI 图标可设置、预览或退出。", QSystemTrayIcon.MessageIcon.Information, 3500)
        except Exception as error:
            logging.exception("Unable to attach desktop")
            self.detach_preview()
            QMessageBox.warning(self, "桌面壁纸模式", str(error))

    def detach_preview(self):
        if self.args.parentHWND:
            return
        self.host_timer.stop()
        if self.parent_hwnd:
            import winwall
            winwall.user32.SetParent(int(self.winId()), None)
        self.parent_hwnd = 0
        self.embedded = False
        self.wall_rect = None
        self.setWindowFlags(Qt.WindowType.Window)
        self.resize(1280, 720)
        self.showNormal()
        self.raise_()

    def sync_host(self):
        import winwall
        if not winwall.user32.IsWindow(self.parent_hwnd):
            QApplication.instance().quit()
            return
        size = winwall.client_size(self.parent_hwnd)
        if not size:
            return
        if self.wall_rect is None:
            winwall.place(int(self.winId()), *(self.engine_viewport or (0, 0, *size)))
        else:
            # Independent mode uses primary screen only; Wallpaper Engine handles its own monitors.
            screen = QApplication.primaryScreen()
            ratio = screen.devicePixelRatio()
            g = screen.geometry()
            point = __import__('ctypes').wintypes.POINT(round(g.x()*ratio), round(g.y()*ratio))
            winwall.user32.ScreenToClient.argtypes = [winwall.HWND, __import__('ctypes').POINTER(__import__('ctypes').wintypes.POINT)]
            winwall.user32.ScreenToClient(self.parent_hwnd, __import__('ctypes').byref(point))
            winwall.place(int(self.winId()), point.x, point.y, round(g.width()*ratio), round(g.height()*ratio))

    def on_tick(self):
        now = self.frozen_now or datetime.now(BEIJING)
        if now.replace(microsecond=0) != self.now.replace(microsecond=0):
            self.now = now
            self.update()

    def on_animation(self):
        now = time.monotonic()
        dt = min(.1, max(0.0, now-self.last_frame))
        self.last_frame = now
        if self.config["effects"] and not self.paused and not self.isMinimized() and not self.frozen_now:
            self.animation_time += dt
            desired = 0.0
            if self.config["parallax"] and self.layers_ready:
                pos = self.mapFromGlobal(QCursor.pos())
                desired = cursor_target(pos.x(), self.width(), self.rect().contains(pos))
            self.parallax_position = smooth_position(self.parallax_position, desired, dt)
            self.update()

    def make_font(self, size, number=False, bold=False):
        f = QFont(self.numbers if number else "Microsoft YaHei UI")
        f.setPixelSize(max(1, round(size)))
        if bold:
            f.setWeight(QFont.Weight.DemiBold)
        return f

    def text(self, p, rect, value, size, number=False, color="#fff7ff", align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, bold=False):
        font = self.make_font(size, number, bold)
        if number:
            measured = QFontMetricsF(font).horizontalAdvance(value)
            if measured > rect.width()*.94:
                font.setPixelSize(max(1, round(font.pixelSize()*rect.width()*.94/measured)))
        p.setFont(font)
        if number and self.config["effects"] and self.config["neon"] and self.config["glow_strength"]:
            key = (value, font.toString(), rect.width(), rect.height())
            if key not in self.text_paths:
                glyph = QPainterPath()
                glyph.addText(0, 0, font, value)
                bounds = glyph.boundingRect()
                glyph.translate(rect.width()/2-bounds.center().x(), rect.height()/2-bounds.center().y())
                # Bounded cache: seconds and hours repeat; font/viewport changes invalidate it.
                if len(self.text_paths) > 96:
                    self.text_paths.clear()
                self.text_paths[key] = glyph
            path = self.text_paths[key]
            p.save()
            p.translate(rect.topLeft())
            gradient = self.neon_gradient(rect.width(), rect.height())
            amount = self.config["glow_strength"]/100 * glow_pulse(self.animation_time)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for width, opacity in [(font.pixelSize()*.13, .10), (font.pixelSize()*.065, .20), (max(1.1, font.pixelSize()*.021), .85)]:
                p.setOpacity(amount*opacity)
                p.setPen(QPen(gradient, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.drawPath(path)
            p.setOpacity(1)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawPath(path)
            p.restore()
            return
        p.setPen(QColor(16, 12, 38, 80))
        p.drawText(rect.translated(0, 2), align, value)
        p.setPen(QColor(color))
        p.drawText(rect, align, value)

    def neon_gradient(self, width, height):
        phase = (.5+.5*math.sin(self.animation_time*.22))
        g = QLinearGradient(-width*.35+phase*width*.7, 0, width*.85+phase*width*.7, height)
        g.setColorAt(0, QColor("#77deff"))
        g.setColorAt(.4, QColor("#ff73df"))
        g.setColorAt(.75, QColor("#c092ff"))
        g.setColorAt(1, QColor("#8de9ff"))
        return g

    def paint_logo(self, p, key, target):
        if self.config["neon"] and self.config["effects"]:
            self.visuals.paint_logo(p, target, self.animation_time,
                                   self.config["glow_strength"]/100, self.devicePixelRatioF())

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cache_key = (w, h, self.devicePixelRatioF())
        ratio = max(w/self.art_size.width(), h/self.art_size.height())
        iw, ih = self.art_size.width()*ratio, self.art_size.height()*ratio
        target = QRectF((w-iw)/2, (h-ih)/2, iw, ih)
        if not self.background_cache or self.background_cache[0] != cache_key:
            pix = QPixmap(round(w*self.devicePixelRatioF()), round(h*self.devicePixelRatioF()))
            pix.setDevicePixelRatio(self.devicePixelRatioF())
            bp = QPainter(pix)
            bp.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            name = "scene-background.jpg" if self.layers_ready else "background.jpg"
            base = load_scaled_pixmap(ASSETS / name, iw, ih, self.devicePixelRatioF())
            bp.drawPixmap(target, base, QRectF(base.rect()))
            bp.end()
            self.background_cache = (cache_key, pix)
        p.drawPixmap(0, 0, self.background_cache[1])
        if self.layers_ready:
            if self.foreground_cache is None or self.foreground_cache[0] != cache_key:
                # Store only the visible half of the transparent character canvas.
                scaled = load_scaled_pixmap(ASSETS / "characters.png", iw, ih,
                                            self.devicePixelRatioF(), crop=(.37, 0, .52, 1))
                self.foreground_cache = (cache_key, scaled)
            amount = self.config["parallax_strength"] * w/1920
            dx = self.parallax_position * amount if self.config["effects"] and self.config["parallax"] else 0
            p.save()
            # Ignore sub-visible alpha residue far away from the extracted people.
            p.setClipRect(QRectF(target.x()+iw*.37+dx, target.y(), iw*.52, ih))
            p.drawPixmap(QPointF(target.x()+iw*.37+dx, target.y()), self.foreground_cache[1])
            p.restore()
        shade = QLinearGradient(0, h*.43, 0, h)
        shade.setColorAt(0, QColor(18, 12, 43, 0))
        shade.setColorAt(.55, QColor(25, 15, 52, 40))
        shade.setColorAt(1, QColor(20, 12, 41, 125))
        p.fillRect(QRectF(0, h*.43, w, h*.57), shade)
        self.paint_logo(p, cache_key, target)
        t = self.animation_time
        if self.config["effects"]:
            glow = QRadialGradient(QPointF(w*.21, h*.66), w*.32)
            glow.setColorAt(0, QColor(255, 77, 193, round(10+4*math.sin(t*.25))))
            glow.setColorAt(1, QColor(255, 89, 170, 0))
            p.fillRect(self.rect(), glow)
            self.visuals.paint_particles(p, w, h, t, .85, self.devicePixelRatioF())
        scale = min(w/1920, h/1080)
        ui = scale * self.config["text_scale"]/100
        x = w*.062
        available = min(660*ui, w*.40)
        num_size = min(116*ui, available/5.2)
        top = h*.555
        if h/w > .67:
            top = h*.59
        state = snapshot(self.now, self.target)
        caption = "欢迎来到莱昂尼达" if state["released"] else "欢迎来到莱昂尼达，还有"
        self.text(p, QRectF(x, top-36*ui, available+50*scale, 34*ui), caption, 19*ui, bold=True, color="#ffe6f5")
        values = [state[k] for k in ["days", "hours", "minutes", "seconds"]]
        col = available/4
        for i, value in enumerate(values):
            self.text(p, QRectF(x+i*col-8*ui, top, col, 143*ui), f"{value:02d}", num_size, True, align=Qt.AlignmentFlag.AlignCenter)
            self.text(p, QRectF(x+i*col-8*ui, top+139*ui, col, 30*ui), ["天", "时", "分", "秒"][i], 16*ui, color="#f5c6e4", align=Qt.AlignmentFlag.AlignCenter, bold=True)
        bar_y = top+195*ui
        bar_w = min(560*ui, available*.94)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 235, 252, 40))
        p.drawRoundedRect(QRectF(x, bar_y, bar_w, 5*ui), 2.5*ui, 2.5*ui)
        accent = QLinearGradient(x, 0, x+bar_w, 0)
        accent.setColorAt(0, QColor("#ff68c8"))
        accent.setColorAt(1, QColor("#ff22b6"))
        p.setBrush(accent)
        p.drawRoundedRect(QRectF(x, bar_y, bar_w*state["progress"], 5*ui), 2.5*ui, 2.5*ui)
        self.text(p, QRectF(x, bar_y+17*ui, available, 30*ui), f"已完成 {state['progress']*100:.1f}%" if not state["released"] else "计划发售日已到 · 以商店实际解锁为准", 15*ui, color="#e7c5e0")
        target_text = format_target(self.target)
        self.text(p, QRectF(x, bar_y+62*ui, available+120*ui, 32*ui), target_text, 18*ui, bold=True, color="#fae7f5")
        custom = self.config["target"] != DEFAULT_TARGET
        self.text(p, QRectF(x, bar_y+97*ui, available+150*ui, 26*ui), "自定义目标 · 北京时间" if custom else "港区 PS5 · PS Store 列示时间", 12*ui, color="#d9b8d5")
        if self.config["clock"]:
            cw = 210*scale
            cx = w-cw-55*scale
            cy = 38*scale
            self.text(p, QRectF(cx, cy, cw, 74*scale), self.now.strftime("%H:%M"), 59*scale, True, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            weekdays = "一二三四五六日"
            self.text(p, QRectF(cx-70*scale, cy+75*scale, cw+70*scale, 26*scale), f"{self.now.month}月{self.now.day}日 星期{weekdays[self.now.weekday()]}", 15*scale, color="#f8d4ec", align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, bold=True)
            self.text(p, QRectF(cx, cy+105*scale, cw, 20*scale), "BEIJING  /  UTC+8", 10*scale, color="#d9c4e4", align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if self.hover and not self.embedded and not self.args.screenshot:
            self.text(p, QRectF(w-300*scale, h-36*scale, 275*scale, 22*scale), "右键设置  ·  F11 全屏  ·  Esc 返回", 12*scale, color="#f5d9ed", align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        p.end()

    def resizeEvent(self, event):
        self.background_cache = None
        self.foreground_cache = None
        self.visuals.invalidate()
        self.text_paths.clear()
        super().resizeEvent(event)

    def enterEvent(self, event):
        self.hover = True
        self.update()

    def leaveEvent(self, event):
        self.hover = False
        self.update()

    def contextMenuEvent(self, event):
        self.menu.exec(event.globalPos())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F11 and not self.embedded:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
        elif event.key() == Qt.Key.Key_Escape and not self.embedded:
            self.showNormal() if self.isFullScreen() else self.close()
        elif event.key() == Qt.Key.Key_Space:
            self.paused = not self.paused

    def closeEvent(self, event):
        if self.tray:
            self.tray.hide()
        QApplication.instance().quit()
        event.accept()


def main():
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("-parentHWND", "--parent-hwnd", dest="parentHWND", type=int, default=0)
    for key in ["x", "y", "w", "h"]:
        parser.add_argument(f"-wpe_{key}", dest=f"wpe_{key}", type=int, default=0)
    parser.add_argument("--desktop", action="store_true")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--config-dir")
    parser.add_argument("--screenshot")
    parser.add_argument("--at", help="ISO 8601 time used only for deterministic preview")
    parser.add_argument("--phase", type=float, default=load_effects_spec()["initial_phase"], help="Initial animation phase for deterministic preview")
    parser.add_argument("--parallax-x", type=float, choices=None, help="Fixed normalized foreground offset for deterministic preview")
    parser.add_argument("--quit-after", type=int, default=0)
    args, unknown = parser.parse_known_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("GTA6Wallpaper")
    app.setOrganizationName("LocalWallpaper")
    app.setQuitOnLastWindowClosed(True)
    # The offscreen Qt plugin has no system font database; load installed Windows
    # fonts explicitly so exported previews contain the same Chinese glyphs.
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        for name in ("msyh.ttc", "msyhbd.ttc", "segoeui.ttf"):
            font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / name
            if font_path.exists():
                QFontDatabase.addApplicationFont(str(font_path))
    try:
        window = Wallpaper(args)
        window.showFullScreen() if args.fullscreen else window.show()
        if args.screenshot:
            window.now = window.frozen_now or datetime.now(BEIJING)
            def capture():
                window.grab().save(args.screenshot)
                app.quit()
            QTimer.singleShot(350, capture)
        else:
            QTimer.singleShot(0, window.setup_host)
        if args.quit_after:
            QTimer.singleShot(args.quit_after * 1000, app.quit)
        return app.exec()
    except Exception as error:
        logging.exception("Wallpaper startup failed")
        QMessageBox.critical(None, "GTA VI 壁纸启动失败", str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
