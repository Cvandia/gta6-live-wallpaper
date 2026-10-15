"""Time-zone independent countdown shared by preview and wallpaper modes."""
from datetime import datetime, timedelta, timezone
from math import ceil

BEIJING = timezone(timedelta(hours=8), "北京时间")
DEFAULT_TARGET = "2026-11-19T00:00:00+08:00"
START = datetime.fromisoformat("2023-12-04T18:00:00-05:00")
RELEASE_SOURCE = "https://store.playstation.com/zh-hans-hk/product/EP1004-PPSA01547_00-GTAVISTANDARD001"
ART_SOURCE = "https://www.rockstargames.com/VI/media/artwork-wallpapers"


def parse_target(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("发售时间必须是 ISO 8601 字符串")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("发售时间必须包含时区，例如 +08:00")
    return result.astimezone(BEIJING)


def format_target(value: datetime) -> str:
    """Avoid platform strftime encodings for Chinese text on English Windows."""
    target=value.astimezone(BEIJING)
    return f"{target.year}年{target.month:02d}月{target.day:02d}日 — {target.hour:02d}:{target.minute:02d} GMT+8"


def snapshot(now: datetime, target: datetime) -> dict:
    if now.tzinfo is None or target.tzinfo is None:
        raise ValueError("必须使用包含时区的时间")
    seconds = max(0, ceil((target - now).total_seconds()))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, seconds_part = divmod(rest, 60)
    duration = (target - START).total_seconds()
    progress = max(0.0, min(1.0, (now - START).total_seconds() / duration)) if duration > 0 else float(now >= target)
    return dict(days=days, hours=hours, minutes=minutes, seconds=seconds_part,
                progress=progress, released=now >= target)
