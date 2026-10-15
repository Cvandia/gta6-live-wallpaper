"""Derive effect-only alpha masks from the white GTA VI logo.

The official artwork is never modified.  Each output is a full-size white RGBA
canvas whose alpha channel is an outer rim around the original logo pixels.
Run with `uv run --group build python tools/create_logo_mask.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps


HERE = Path(__file__).resolve().parents[1]
ASSETS = HERE / "assets"
ROI = (200, 170, 1400, 1100)
DOWNSAMPLE = 2
FILTER_PADDING = 24  # Half-resolution pixels; prevent a clipped halo at ROI edge.


def create_masks() -> dict:
    with Image.open(ASSETS / "background.jpg") as source:
        source = source.convert("RGB")
        size = source.size
        crop = source.crop(ROI).resize(
            ((ROI[2] - ROI[0]) // DOWNSAMPLE,
             (ROI[3] - ROI[1]) // DOWNSAMPLE),
            Image.Resampling.LANCZOS,
        )

    # A neutral near-white threshold rejects the purple/pink sky.  The ramp
    # preserves antialiasing on the artwork's printed letters and VI outline.
    red, green, blue = crop.split()
    minimum = ImageChops.darker(ImageChops.darker(red, green), blue)
    maximum = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    chroma = ImageChops.subtract(maximum, minimum)
    luminance_gate = minimum.point(
        lambda value: round(max(0, min(1, (value - 210) / 35)) * 255)
    )
    neutral_gate = chroma.point(
        lambda value: round(max(0, min(1, (45 - value) / 18)) * 255)
    )
    logo_alpha = ImageChops.multiply(luminance_gate, neutral_gate)
    logo_alpha = ImageOps.expand(logo_alpha, border=FILTER_PADDING, fill=0)
    padding_native = FILTER_PADDING * DOWNSAMPLE
    output_roi = (ROI[0] - padding_native, ROI[1] - padding_native,
                  ROI[2] + padding_native, ROI[3] + padding_native)

    # At 4K these correspond to an approximately 4 px crisp rim and a soft
    # 8 px dilated halo with 10 px Gaussian blur.  All filtering stays in ROI.
    rim = ImageChops.subtract(logo_alpha.filter(ImageFilter.MaxFilter(5)), logo_alpha)
    halo = ImageChops.subtract(
        logo_alpha.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(5)),
        logo_alpha,
    )

    report = {
        "source": "assets/background.jpg",
        "source_size": list(size),
        "roi": list(ROI),
        "processing_scale": 1 / DOWNSAMPLE,
        "filter_padding_native_px": padding_native,
        "white_min_ramp": [210, 245],
        "chroma_max_ramp": [27, 45],
        "outputs": {},
    }
    for filename, alpha, parameters in (
        ("logo-mask.png", rim, {"dilate_filter": 5, "rim_native_px": 4}),
        ("logo-glow-mask.png", halo,
         {"dilate_filter": 9, "blur_sigma": 5, "native_blur_sigma": 10}),
    ):
        restored = alpha.resize((output_roi[2] - output_roi[0], output_roi[3] - output_roi[1]), Image.Resampling.LANCZOS)
        full_alpha = Image.new("L", size, 0)
        full_alpha.paste(restored, output_roi[:2])
        rgba = Image.new("RGBA", size, (255, 255, 255, 0))
        rgba.putalpha(full_alpha)
        output = ASSETS / filename
        rgba.save(output, optimize=True)
        report["outputs"][filename] = {
            "alpha_bbox": list(full_alpha.getbbox()),
            "alpha_extrema": list(full_alpha.getextrema()),
            "bytes": output.stat().st_size,
            **parameters,
        }
    (HERE / "docs" / "logo-mask-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    print(json.dumps(create_masks(), ensure_ascii=False, indent=2))
