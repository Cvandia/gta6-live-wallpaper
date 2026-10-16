"""Decode only the display-sized artwork retained by the wallpaper."""
from pathlib import Path
from PySide6.QtCore import QSize, QRect
from PySide6.QtGui import QImageReader, QPixmap


def load_scaled_pixmap(path: Path, width: float, height: float, dpr: float,
                       crop: tuple[float, float, float, float] | None = None) -> QPixmap:
    reader = QImageReader(str(path))
    size = QSize(max(1, round(width*dpr)), max(1, round(height*dpr)))
    reader.setScaledSize(size)
    if crop is not None:
        x, y, w, h = crop
        reader.setScaledClipRect(QRect(round(x*size.width()), round(y*size.height()),
                                      max(1, round(w*size.width())), max(1, round(h*size.height()))))
    image = reader.read()
    if image.isNull():
        raise RuntimeError(f"无法加载壁纸素材 {path.name}: {reader.errorString()}")
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(dpr)
    return pixmap
