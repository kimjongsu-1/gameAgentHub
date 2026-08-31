from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageStat


ROOT = Path(r"C:\Users\kukl3\Documents\게임 개발 프로젝트")
GENERATED = Path(r"C:\Users\kukl3\.codex\generated_images\019f1116-edae-76b3-9c9c-97f5ea8d61f8")
OUT = ROOT / "04_concepts" / "work" / "MONSTER_30_MAPS"
SOURCES = OUT / "sources"
FINAL = OUT / "final"

MAPS = [
    ("ABYSS", "황천 균열 도심", "exec-dc1ff00d-dbf4-4e46-8988-ffe81fbd65d7.png"),
    ("EMBER", "적염 봉인길", "exec-41bba5d2-ffdd-4df1-b127-56d108d0ab97.png"),
    ("FROST", "한빙 영맥 고개", "exec-ce53efd4-3ede-472e-b5c3-5de6cbec42d7.png"),
    ("VENOM", "독성 침식 습지", "exec-85fa1d0f-6b98-4f89-818b-6a55a4b15bb3.png"),
    ("GOLD", "황금 수호 유적", "exec-b0fbfe30-d265-4d60-9ef5-def54d1500e7.png"),
    ("BLOOD", "흑혈 제단", "exec-e72200c6-bd8e-4676-981b-724c9ac1726f.png"),
]


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def cover_9x16(image: Image.Image) -> Image.Image:
    target_ratio = 9 / 16
    ratio = image.width / image.height
    if ratio > target_ratio:
        width = round(image.height * target_ratio)
        left = (image.width - width) // 2
        image = image.crop((left, 0, left + width, image.height))
    elif ratio < target_ratio:
        height = round(image.width / target_ratio)
        top = (image.height - height) // 2
        image = image.crop((0, top, image.width, top + height))
    return image.resize((1080, 1920), Image.Resampling.LANCZOS).convert("RGB")


def main() -> None:
    SOURCES.mkdir(parents=True, exist_ok=True)
    FINAL.mkdir(parents=True, exist_ok=True)
    records = []
    thumbs = []
    for palette, title, filename in MAPS:
        source = GENERATED / filename
        if not source.exists():
            raise FileNotFoundError(source)
        source_copy = SOURCES / f"MAP_{palette}_SOURCE.png"
        shutil.copy2(source, source_copy)
        with Image.open(source_copy) as opened:
            original_size = list(opened.size)
            final_image = cover_9x16(opened.convert("RGB"))
        final_path = FINAL / f"MAP_{palette}_1080x1920.png"
        final_image.save(final_path, optimize=True)

        with Image.open(final_path) as checked:
            checked.load()
            stat = ImageStat.Stat(checked)
            passed = checked.size == (1080, 1920) and checked.mode == "RGB" and min(stat.stddev) > 8
            record = {
                "asset_id": f"MAP_MONSTER_PALETTE_{palette}_V01",
                "palette": palette,
                "title_ko": title,
                "source_path": str(source_copy.relative_to(ROOT)).replace("\\", "/"),
                "file_path": str(final_path.relative_to(ROOT)).replace("\\", "/"),
                "original_size": original_size,
                "final_size": list(checked.size),
                "mode": checked.mode,
                "sha256": sha256(final_path),
                "qa": {
                    "status": "PASS" if passed else "FAIL",
                    "exact_1080x1920": checked.size == (1080, 1920),
                    "opaque_rgb": checked.mode == "RGB",
                    "non_blank_stddev": [round(v, 3) for v in stat.stddev],
                    "no_characters_or_text": "VISUALLY_REVIEWED",
                    "central_combat_lane": "VISUALLY_REVIEWED",
                },
            }
            records.append(record)
            thumbs.append((palette, title, checked.copy().resize((270, 480), Image.Resampling.LANCZOS)))

    catalog = Image.new("RGB", (860, 1030), (18, 19, 24))
    draw = ImageDraw.Draw(catalog)
    font_path = Path(r"C:\Windows\Fonts\malgunbd.ttf")
    font = ImageFont.truetype(str(font_path), 16) if font_path.exists() else ImageFont.load_default()
    for index, (palette, title, thumb) in enumerate(thumbs):
        col, row = index % 3, index // 3
        x, y = 10 + col * 285, 35 + row * 505
        catalog.paste(thumb, (x, y))
        draw.text((x, y - 20), f"{palette} / {title}", fill=(235, 235, 240), font=font)
    catalog_path = OUT / "MONSTER_30_MAP_CATALOG.png"
    catalog.save(catalog_path, optimize=True)

    manifest = {
        "bundle_id": "MONSTER_30_PALETTE_MAPS_V01",
        "count": len(records),
        "spec": {"width": 1080, "height": 1920, "aspect": "9:16", "format": "PNG", "background": "opaque"},
        "qa_status": "PASS" if all(x["qa"]["status"] == "PASS" for x in records) else "FAIL",
        "catalog_path": str(catalog_path.relative_to(ROOT)).replace("\\", "/"),
        "maps": records,
    }
    manifest_path = OUT / "MONSTER_30_MAP_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"qa_status": manifest["qa_status"], "count": len(records), "catalog": str(catalog_path), "manifest": str(manifest_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
