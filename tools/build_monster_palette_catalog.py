from __future__ import annotations

import colorsys
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from normalize_sprite_sheet import keep_largest_component, remove_green


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "04_concepts" / "work" / "MONSTER_30_CATALOG"
SOURCE = OUT / "sources"
CANVAS = 512
MAX_SUBJECT = 420
BASELINE = 466


FAMILIES = [
    {
        "id": "INFANTRY",
        "name": "보병형",
        "path": ROOT / "04_concepts/work/MON_PROLOGUE_SEVERED_INFANTRY_01/MON_PROLOGUE_SEVERED_INFANTRY_01_recommended_front_C.png",
        "mode": "transparent",
    },
    {"id": "BEAST", "name": "짐승형", "path": SOURCE / "beast_chroma_source.png", "mode": "chroma"},
    {
        "id": "WRAITH",
        "name": "망령형",
        "path": ROOT / "04_concepts/work/MON_PROLOGUE_CRACKED_WRAITH_01/MON_PROLOGUE_CRACKED_WRAITH_01_recommended_front_A.png",
        "mode": "transparent",
    },
    {"id": "HEAVY", "name": "중장형", "path": SOURCE / "heavy_chroma_source.png", "mode": "chroma"},
    {
        "id": "GIANT",
        "name": "거체형",
        "path": ROOT / "05_sprites/work/recentered_monsters_v02/DUEOKSINI_WALK_LEFT_V03/DUEOKSINI_WALK_LEFT_V03_16f_4x4_recentered.png",
        "mode": "first_cell",
    },
]


PALETTES = [
    {"id": "ABYSS", "name": "황천 자주", "primary": 0.76, "secondary": 0.52, "original": True},
    {"id": "EMBER", "name": "적염", "primary": 0.98, "secondary": 0.07},
    {"id": "FROST", "name": "한빙", "primary": 0.61, "secondary": 0.52},
    {"id": "VENOM", "name": "독성", "primary": 0.34, "secondary": 0.22},
    {"id": "GOLD", "name": "황금", "primary": 0.10, "secondary": 0.15},
    {"id": "BLOOD", "name": "흑혈", "primary": 0.92, "secondary": 0.84},
]


def alpha_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    bbox = image.getchannel("A").point(lambda value: 255 if value >= 16 else 0).getbbox()
    if bbox is None:
        raise ValueError("empty monster source")
    return bbox


def normalized_base(spec: dict) -> Image.Image:
    image = Image.open(spec["path"]).convert("RGBA")
    if spec["mode"] == "chroma":
        image = remove_green(image)
    elif spec["mode"] == "first_cell":
        image = image.crop((0, 0, image.width // 4, image.height // 4))
    image = keep_largest_component(image)
    crop = image.crop(alpha_bbox(image))
    scale = min(MAX_SUBJECT / crop.width, MAX_SUBJECT / crop.height)
    crop = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.Resampling.LANCZOS)
    crop = crop.crop(alpha_bbox(crop))
    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.alpha_composite(crop, ((CANVAS - crop.width) // 2, BASELINE - crop.height))
    return canvas


def recolor(base: Image.Image, palette: dict) -> Image.Image:
    if palette.get("original"):
        return base.copy()
    output = []
    primary = palette["primary"]
    secondary = palette["secondary"]
    for r, g, b, a in base.getdata():
        if a == 0:
            output.append((0, 0, 0, 0))
            continue
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s < 0.12 and v > 0.72:
            # Preserve bright mask/eye whites for family recognition.
            nr, ng, nb = r / 255, g / 255, b / 255
        elif v < 0.10:
            nr, ng, nb = colorsys.hsv_to_rgb(primary, min(0.22, s + 0.08), v)
        elif s < 0.18:
            nr, ng, nb = colorsys.hsv_to_rgb(primary, 0.16 + 0.12 * (1 - v), v)
        else:
            target_hue = secondary if v > 0.62 else primary
            nr, ng, nb = colorsys.hsv_to_rgb(target_hue, max(0.52, min(0.95, s)), v)
        output.append((round(nr * 255), round(ng * 255), round(nb * 255), a))
    result = Image.new("RGBA", base.size)
    result.putdata(output)
    return result


def alpha_checksum(image: Image.Image) -> str:
    return hashlib.sha256(image.getchannel("A").tobytes()).hexdigest()


def main() -> None:
    (OUT / "base").mkdir(parents=True, exist_ok=True)
    (OUT / "variants").mkdir(parents=True, exist_ok=True)
    catalog = Image.new("RGB", (6 * 256, 5 * 256), (18, 21, 28))
    draw = ImageDraw.Draw(catalog)
    entries = []

    for row, family in enumerate(FAMILIES):
        base = normalized_base(family)
        base_path = OUT / "base" / f"MON_{family['id']}_BASE.png"
        base.save(base_path, "PNG", optimize=True)
        base_alpha = alpha_checksum(base)
        for col, palette in enumerate(PALETTES):
            variant = recolor(base, palette)
            asset_id = f"MON_{family['id']}_{palette['id']}_V01"
            path = OUT / "variants" / f"{asset_id}.png"
            variant.save(path, "PNG", optimize=True)

            thumb = variant.copy()
            bounds = alpha_bbox(thumb)
            thumb = thumb.crop(bounds)
            thumb.thumbnail((218, 210), Image.Resampling.LANCZOS)
            ox, oy = col * 256, row * 256
            card = Image.new("RGBA", (256, 256), (28, 32, 42, 255))
            card.alpha_composite(thumb, ((256 - thumb.width) // 2, 34 + (210 - thumb.height) // 2))
            catalog.paste(card.convert("RGB"), (ox, oy))
            draw.rectangle((ox, oy, ox + 255, oy + 255), outline=(60, 70, 90), width=1)
            draw.text((ox + 8, oy + 8), f"{row + 1}-{col + 1} {family['id']} / {palette['id']}", fill=(225, 230, 240))

            entries.append(
                {
                    "asset_id": asset_id,
                    "family": family["id"],
                    "family_name": family["name"],
                    "palette": palette["id"],
                    "palette_name": palette["name"],
                    "file_path": path.relative_to(ROOT).as_posix(),
                    "size": [CANVAS, CANVAS],
                    "mode": "RGBA",
                    "silhouette_checksum": alpha_checksum(variant),
                    "silhouette_matches_family_base": alpha_checksum(variant) == base_alpha,
                    "derivation": "palette_only",
                }
            )

    catalog_path = OUT / "MONSTER_30_CATALOG.png"
    catalog.save(catalog_path, "PNG", optimize=True)
    manifest = {
        "title": "단맥 몬스터 5체형 x 6팔레트 카탈로그",
        "total": len(entries),
        "families": [{"id": item["id"], "name": item["name"]} for item in FAMILIES],
        "palettes": [{"id": item["id"], "name": item["name"]} for item in PALETTES],
        "rule": "같은 체형에서는 색상만 변경하며 실루엣과 알파 마스크를 유지한다.",
        "all_silhouettes_locked": all(item["silhouette_matches_family_base"] for item in entries),
        "entries": entries,
    }
    (OUT / "MONSTER_30_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"total": len(entries), "catalog": str(catalog_path), "all_silhouettes_locked": manifest["all_silhouettes_locked"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
