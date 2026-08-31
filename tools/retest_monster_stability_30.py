from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "05_sprites/work/MONSTER_30_ANIMATIONS/MONSTER_30_ANIMATION_MANIFEST.json"
OUTPUT = ROOT / "05_sprites/work/MONSTER_30_ANIMATIONS/MONSTER_30_STRICT_STABILITY_RETEST.json"
CELL = 256
OPAQUE_THRESHOLD = 200


def bbox(image: Image.Image) -> tuple[int, int, int, int]:
    result = image.getchannel("A").point(lambda value: 255 if value >= OPAQUE_THRESHOLD else 0).getbbox()
    if result is None:
        raise ValueError("empty opaque body")
    return result


def center_x(image: Image.Image, top: float, bottom: float, center_bias: bool = False) -> float:
    alpha = image.getchannel("A")
    pixels = alpha.load()
    y0, y1 = round(image.height * top), round(image.height * bottom)
    total = weighted = 0.0
    for y in range(y0, min(image.height, y1)):
        for x in range(image.width):
            value = pixels[x, y]
            if value < OPAQUE_THRESHOLD:
                continue
            weight = float(value)
            if center_bias:
                weight *= max(0.15, 1.0 - abs(x / max(1, image.width - 1) - 0.5) * 1.5)
            total += weight
            weighted += x * weight
    return weighted / total if total else image.width / 2


def spread(values: list[float]) -> float:
    return round(max(values) - min(values), 4)


def analyze(path: Path) -> dict:
    sheet = Image.open(path).convert("RGBA")
    frames = []
    for index in range(16):
        col, row = index % 4, index // 4
        frame = sheet.crop((col * CELL, row * CELL, (col + 1) * CELL, (row + 1) * CELL))
        bounds = bbox(frame)
        subject = frame.crop(bounds)
        frames.append({
            "bbox": list(bounds),
            "mass_x": bounds[0] + center_x(subject, 0.0, 1.0),
            "head_x": bounds[0] + center_x(subject, 0.0, 0.46, True),
            "torso_x": bounds[0] + center_x(subject, 0.28, 0.76, True),
            "height": bounds[3] - bounds[1],
            "baseline": bounds[3],
        })
    heights = [item["height"] for item in frames]
    result = {
        "mass_center_x_range_px": spread([item["mass_x"] for item in frames]),
        "head_center_x_range_px": spread([item["head_x"] for item in frames]),
        "torso_center_x_range_px": spread([item["torso_x"] for item in frames]),
        "baseline_range_px": max(item["baseline"] for item in frames) - min(item["baseline"] for item in frames),
        "height_variation_percent": round((max(heights) - min(heights)) / mean(heights) * 100, 3),
    }
    result["horizontal_stability"] = "PASS" if (
        result["mass_center_x_range_px"] <= 0.25
        and result["head_center_x_range_px"] <= 0.5
        and result["torso_center_x_range_px"] <= 0.5
        and result["baseline_range_px"] == 0
    ) else "FAIL"
    result["strict_scale_consistency"] = "PASS" if result["height_variation_percent"] <= 2.0 else "FAIL"
    return result


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    results = []
    for entry in manifest["entries"]:
        metrics = analyze(ROOT / entry["sheet_path"])
        results.append({
            "asset_id": entry["asset_id"],
            "monster_id": entry["monster_id"],
            "motion": entry["motion"],
            "sheet_path": entry["sheet_path"],
            **metrics,
        })
    summary = {
        "title": "몬스터 30종 90시트 강화 흔들림 재검사",
        "thresholds": {
            "mass_center_x_range_px": 0.25,
            "head_center_x_range_px": 0.5,
            "torso_center_x_range_px": 0.5,
            "baseline_range_px": 0,
            "strict_scale_variation_percent": 2.0,
        },
        "total": len(results),
        "horizontal_pass": sum(item["horizontal_stability"] == "PASS" for item in results),
        "horizontal_fail": sum(item["horizontal_stability"] == "FAIL" for item in results),
        "strict_scale_pass": sum(item["strict_scale_consistency"] == "PASS" for item in results),
        "strict_scale_fail": sum(item["strict_scale_consistency"] == "FAIL" for item in results),
        "max_mass_center_x_range_px": max(item["mass_center_x_range_px"] for item in results),
        "max_head_center_x_range_px": max(item["head_center_x_range_px"] for item in results),
        "max_torso_center_x_range_px": max(item["torso_center_x_range_px"] for item in results),
        "max_height_variation_percent": max(item["height_variation_percent"] for item in results),
        "results": results,
    }
    summary["status"] = "PASS" if summary["horizontal_fail"] == 0 else "FAIL"
    OUTPUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("status", "total", "horizontal_pass", "horizontal_fail", "strict_scale_pass", "strict_scale_fail", "max_mass_center_x_range_px", "max_head_center_x_range_px", "max_torso_center_x_range_px", "max_height_variation_percent")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
