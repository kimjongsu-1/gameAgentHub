from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import build_prologue_monsters as common


CELL = 256
FPS = 6


def extract(source: Path, cols: int, rows: int, count: int, baseline: int = 238):
    raw = Image.open(source).convert("RGBA")
    crops = []
    for i in range(count):
        x0 = round(raw.width * (i % cols) / cols)
        x1 = round(raw.width * ((i % cols) + 1) / cols)
        y0 = round(raw.height * (i // cols) / rows)
        y1 = round(raw.height * ((i // cols) + 1) / rows)
        crops.append(common.trim(common.chroma_to_alpha(raw.crop((x0, y0, x1, y1)))))
    max_w = max(x.width for x in crops)
    max_h = max(x.height for x in crops)
    scale = min(224 / max_w, (baseline - 14) / max_h)
    frames = []
    for crop in crops:
        crop = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.Resampling.LANCZOS)
        frame = Image.new("RGBA", (CELL, CELL))
        frame.alpha_composite(crop, ((CELL - crop.width) // 2, baseline - crop.height))
        frames.append(frame)
    return frames


def save_sheet(frames, cols, rows, path):
    out = Image.new("RGBA", (cols * CELL, rows * CELL))
    for i, frame in enumerate(frames):
        out.alpha_composite(frame, ((i % cols) * CELL, (i // cols) * CELL))
    out.save(path)


def save_gif(frames, path):
    seq = []
    for frame in frames:
        bg = Image.new("RGBA", frame.size, (24, 24, 36, 255))
        bg.alpha_composite(frame)
        seq.append(bg.convert("P", palette=Image.Palette.ADAPTIVE, colors=255))
    seq[0].save(path, save_all=True, append_images=seq[1:], duration=167,
                loop=0, disposal=2, optimize=False)


def qa(path: Path, cols, rows, count, baseline, motion):
    im = Image.open(path).convert("RGBA")
    frames, boxes = [], []
    for i in range(count):
        f = im.crop(((i % cols) * CELL, (i // cols) * CELL,
                     ((i % cols) + 1) * CELL, ((i // cols) + 1) * CELL))
        frames.append(f)
        boxes.append(f.getchannel("A").getbbox())
    hashes = [hashlib.sha256(f.tobytes()).hexdigest() for f in frames]
    centers = [(b[0] + b[2]) / 2 for b in boxes]
    bottoms = [b[3] for b in boxes]
    checks = {
        "rgba_png": im.mode == "RGBA",
        "grid_dimensions": im.size == (cols * CELL, rows * CELL),
        "frame_count": len(frames) == count,
        "transparent_corners": all(f.getpixel(p)[3] == 0 for f in frames for p in ((0,0),(255,0),(0,255),(255,255))),
        "no_duplicate_frames": len(set(hashes)) == count,
        "baseline_y_fixed": len(set(bottoms)) == 1 and bottoms[0] == baseline,
        "body_center_x_tolerance_1px": max(centers) - min(centers) <= 1,
        "cell_padding_min_8px": all(b[0] >= 8 and b[1] >= 8 and b[2] <= 248 and b[3] <= 248 for b in boxes),
        "pivot_bottom_center_0.5_1.0": True,
    }
    return {"animation": motion, "path": str(path), "sha256": common.sha256(path),
            "checks": checks, "pass": all(checks.values()),
            "metrics": {"baseline_y": bottoms, "body_center_x": centers,
                        "bbox": boxes}}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--concept", type=Path, required=True)
    for name in ("idle", "walk", "basic_attack", "hit", "death"):
        p.add_argument(f"--{name.replace('_','-')}", dest=name, type=Path, required=True)
    a = p.parse_args()
    mid = "CHR_PROTAGONIST_BASE_01"
    cdir = a.root / "04_concepts" / "work" / mid
    sdir = a.root / "05_sprites" / "work" / mid
    cdir.mkdir(parents=True, exist_ok=True)
    sdir.mkdir(parents=True, exist_ok=True)

    candidates = common.concept_candidates(a.concept, cdir, mid)
    common.comparison(candidates, "단맥 계승자 · 정면 디자인 비교",
                      ["후드 표준형", "재킷 정돈형", "권고·중성 후드형", "짧은 머리형", "하이칼라형"],
                      2, cdir / f"{mid}_front_comparison_sheet.jpg")
    rec = cdir / f"{mid}_recommended_front_C.png"
    candidates[2].save(rec)

    specs = [
        ("idle", a.idle, 4, 4, 16), ("walk", a.walk, 4, 4, 16),
        ("basic_attack", a.basic_attack, 4, 4, 16), ("hit", a.hit, 4, 2, 8),
        ("death", a.death, 4, 3, 12),
    ]
    entries = []
    for motion, source, cols, rows, count in specs:
        Image.open(source).save(sdir / f"{mid}_{motion}_chroma_source.png")
        frames = extract(source, cols, rows, count)
        png = sdir / f"{mid}_{motion}_{count}f_{cols}x{rows}.png"
        gif = sdir / f"{mid}_{motion}_6fps.gif"
        save_sheet(frames, cols, rows, png)
        save_gif(frames, gif)
        entry = qa(png, cols, rows, count, 238, motion)
        entry.update({"preview_gif": str(gif), "preview_sha256": common.sha256(gif), "fps": FPS})
        entries.append(entry)

    manifest = {
        "schema": "danmaek.stage01.protagonist_sprite_manifest.v1",
        "external_ai_api_used": False,
        "unity_handoff": "BLOCKED_PENDING_USER_APPROVAL",
        "character_id": mid, "recommended_candidate": "C",
        "recommendation": "중성적 현대 청년 실루엣, 최소 장식, 공용 리그 친화성이 가장 안정적임",
        "pivot": [0.5, 1.0], "cell_px": [256, 256], "fps": FPS,
        "concept_dir": str(cdir), "recommended_front": str(rec),
        "animations": entries, "overall_pass": all(x["pass"] for x in entries),
    }
    out = sdir / "STAGE01_PROTAGONIST_SPRITE_QA_MANIFEST.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(out), "overall_pass": manifest["overall_pass"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
