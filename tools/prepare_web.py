"""Copy the shared local assets into the standalone Web wallpaper directory."""

from pathlib import Path
import json
import shutil


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ASSETS = ("background.jpg", "Anton-Regular.ttf", "effects-spec.json")
OPTIONAL_ASSETS = (
    "scene-background.jpg",
    "characters.png",
    "logo-mask.png",
    "logo-glow-mask.png",
    "Anton-OFL.txt",
    "sources.json",
)


def prepare_web_assets() -> int:
    assets = PROJECT_ROOT / "assets"
    destination = PROJECT_ROOT / "web" / "assets"
    missing = [name for name in REQUIRED_ASSETS if not (assets / name).is_file()]
    if missing:
        raise FileNotFoundError("Missing required assets: " + ", ".join(missing))
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name in REQUIRED_ASSETS + OPTIONAL_ASSETS:
        source = assets / name
        if source.is_file():
            shutil.copy2(source, destination / name)
            copied += 1
    spec = json.loads((assets / "effects-spec.json").read_text(encoding="utf-8"))
    # A classic local script also works under file://, unlike fetch() of a JSON file.
    (PROJECT_ROOT / "web" / "effects-data.js").write_text(
        "window.GTA6_EFFECTS_SPEC = " + json.dumps(spec, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8", newline="\n",
    )
    return copied


if __name__ == "__main__":
    count = prepare_web_assets()
    print(f"Prepared {count} assets in {PROJECT_ROOT / 'web' / 'assets'}")
