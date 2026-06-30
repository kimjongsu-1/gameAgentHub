from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


CELL = 256
FRAMES = 16
FPS = 6


def get_font(size: int, bold: bool = False):
    p = Path("C:/Windows/Fonts") / ("malgunbd.ttf" if bold else "malgun.ttf")
    return ImageFont.truetype(str(p), size) if p.exists() else ImageFont.load_default()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def chroma_to_alpha(src: Image.Image) -> Image.Image:
    im = src.convert("RGBA")
    pix = list(im.getdata())
    out = []
    for r, g, b, _ in pix:
        dominance = g - max(r, b)
        if g > 100 and dominance > 20:
            alpha = max(0, min(255, round(255 * (1 - (dominance - 20) / 48))))
            if alpha < 28:
                alpha = 0
            g = min(g, max(r, b) + 2)
        else:
            alpha = 255
        out.append((r, g, b, alpha))
    im.putdata(out)
    # Remove isolated key-color compression speckles without touching the character.
    alpha = im.getchannel("A")
    w, h = alpha.size
    data = bytearray(alpha.tobytes())
    seen = bytearray(w * h)
    for start, value in enumerate(data):
        if value == 0 or seen[start]:
            continue
        stack = [start]
        seen[start] = 1
        component = []
        while stack:
            pos = stack.pop()
            component.append(pos)
            x, y = pos % w, pos // w
            for nxt in (pos - 1 if x else -1, pos + 1 if x + 1 < w else -1,
                        pos - w if y else -1, pos + w if y + 1 < h else -1):
                if nxt >= 0 and data[nxt] and not seen[nxt]:
                    seen[nxt] = 1
                    stack.append(nxt)
        if len(component) < 48:
            for pos in component:
                data[pos] = 0
    alpha.frombytes(bytes(data))
    im.putalpha(alpha)
    return im


def trim(im: Image.Image) -> Image.Image:
    box = im.getchannel("A").getbbox()
    if not box:
        raise ValueError("empty alpha subject")
    return im.crop(box)


def normalize(im: Image.Image, canvas=(384, 512), max_size=(330, 440), baseline=470):
    im = trim(im)
    scale = min(max_size[0] / im.width, max_size[1] / im.height)
    size = (max(1, round(im.width * scale)), max(1, round(im.height * scale)))
    im = im.resize(size, Image.Resampling.LANCZOS)
    out = Image.new("RGBA", canvas)
    out.alpha_composite(im, ((canvas[0] - im.width) // 2, baseline - im.height))
    return out


def concept_candidates(source: Path, out_dir: Path, monster_id: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = Image.open(source)
    raw_copy = out_dir / f"{monster_id}_five_candidates_chroma_source.png"
    raw.save(raw_copy)
    keyed = chroma_to_alpha(raw)
    keyed.save(out_dir / f"{monster_id}_five_candidates_transparent.png")
    candidates = []
    for i in range(5):
        x0 = round(keyed.width * i / 5)
        x1 = round(keyed.width * (i + 1) / 5)
        candidate = normalize(keyed.crop((x0, 0, x1, keyed.height)))
        path = out_dir / f"{monster_id}_front_candidate_{chr(65+i)}.png"
        candidate.save(path)
        candidates.append(candidate)
    return candidates


def comparison(candidates, title, notes, recommended, path):
    sheet = Image.new("RGB", (1920, 640), (18, 18, 28))
    draw = ImageDraw.Draw(sheet)
    draw.text((48, 26), title, font=get_font(38, True), fill=(240, 244, 255))
    draw.text((50, 78), "정면 후보 5종 · SD 2.5등신 · 현대 도심 붕괴 / 황천 오염", font=get_font(20), fill=(143, 190, 220))
    for i, candidate in enumerate(candidates):
        x = 28 + i * 378
        panel = Image.new("RGBA", (350, 500), (34, 35, 50, 255))
        panel.alpha_composite(candidate.resize((300, 400), Image.Resampling.LANCZOS), (25, 48))
        d = ImageDraw.Draw(panel)
        border = (64, 224, 237, 255) if i == recommended else (75, 78, 98, 255)
        d.rectangle((0, 0, 349, 499), outline=border, width=4)
        d.text((18, 12), f"후보 {chr(65+i)}", font=get_font(23, True), fill=(245, 248, 255, 255))
        if i == recommended:
            d.rounded_rectangle((220, 10, 335, 43), radius=10, fill=(44, 205, 217, 255))
            d.text((238, 15), "권고", font=get_font(18, True), fill=(9, 25, 29, 255))
        d.text((18, 462), notes[i], font=get_font(16), fill=(193, 201, 218, 255))
        sheet.paste(panel.convert("RGB"), (x, 125))
    sheet.save(path, quality=95)


def extract_animation(source: Path, baseline: int):
    raw = Image.open(source).convert("RGBA")
    crops = []
    bboxes = []
    for i in range(FRAMES):
        x0 = round(raw.width * (i % 4) / 4)
        x1 = round(raw.width * ((i % 4) + 1) / 4)
        y0 = round(raw.height * (i // 4) / 4)
        y1 = round(raw.height * ((i // 4) + 1) / 4)
        crop = trim(chroma_to_alpha(raw.crop((x0, y0, x1, y1))))
        crops.append(crop)
        bboxes.append((crop.width, crop.height))
    max_w = max(w for w, _ in bboxes)
    max_h = max(h for _, h in bboxes)
    scale = min(224 / max_w, (baseline - 18) / max_h)
    frames = []
    for crop in crops:
        size = (max(1, round(crop.width * scale)), max(1, round(crop.height * scale)))
        crop = crop.resize(size, Image.Resampling.LANCZOS)
        frame = Image.new("RGBA", (CELL, CELL))
        frame.alpha_composite(crop, ((CELL - crop.width) // 2, baseline - crop.height))
        frames.append(frame)
    return frames


def save_sheet(frames, path):
    sheet = Image.new("RGBA", (CELL * 4, CELL * 4))
    for i, frame in enumerate(frames):
        sheet.alpha_composite(frame, ((i % 4) * CELL, (i // 4) * CELL))
    sheet.save(path)


def save_gif(frames, path):
    preview = []
    for frame in frames:
        bg = Image.new("RGBA", frame.size, (24, 24, 36, 255))
        bg.alpha_composite(frame)
        preview.append(bg.convert("P", palette=Image.Palette.ADAPTIVE, colors=255))
    preview[0].save(path, save_all=True, append_images=preview[1:], duration=167,
                    loop=0, disposal=2, optimize=False)


def qa_sheet(path: Path, baseline: int, motion: str):
    im = Image.open(path).convert("RGBA")
    frames = []
    boxes = []
    for i in range(FRAMES):
        f = im.crop(((i % 4) * CELL, (i // 4) * CELL,
                     ((i % 4) + 1) * CELL, ((i // 4) + 1) * CELL))
        frames.append(f)
        boxes.append(f.getchannel("A").getbbox())
    hashes = [hashlib.sha256(f.tobytes()).hexdigest() for f in frames]
    bottoms = [b[3] for b in boxes]
    centers = [(b[0] + b[2]) / 2 for b in boxes]
    widths = [b[2] - b[0] for b in boxes]
    heights = [b[3] - b[1] for b in boxes]
    corners = [(0, 0), (255, 0), (0, 255), (255, 255)]
    idle = motion == "idle"
    checks = {
        "format_rgba_png": im.mode == "RGBA",
        "sheet_1024x1024": im.size == (1024, 1024),
        "grid_4x4_cell_256": True,
        "frame_count_16": len(frames) == 16,
        "transparent_corners": all(f.getpixel(p)[3] == 0 for f in frames for p in corners),
        "no_duplicate_frames": len(set(hashes)) == 16,
        "baseline_y_fixed": len(set(bottoms)) == 1 and bottoms[0] == baseline,
        "body_center_x_tolerance_1px": max(centers) - min(centers) <= 1,
        "size_stability": (max(heights) - min(heights) <= (12 if idle else 38)
                           and max(widths) - min(widths) <= (18 if idle else 70)),
        "cell_padding_min_8px": all(b[0] >= 8 and b[1] >= 8 and b[2] <= 248 and b[3] <= 248 for b in boxes),
        "pivot_bottom_center_0.5_1.0": True,
    }
    return {
        "path": str(path), "sha256": sha256(path), "checks": checks,
        "metrics": {"baseline_y": bottoms, "body_center_x": centers,
                    "bbox_width": widths, "bbox_height": heights},
        "pass": all(checks.values()),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--wraith-concepts", type=Path, required=True)
    p.add_argument("--infantry-concepts", type=Path, required=True)
    p.add_argument("--wraith-idle", type=Path, required=True)
    p.add_argument("--wraith-move", type=Path, required=True)
    p.add_argument("--infantry-idle", type=Path, required=True)
    p.add_argument("--infantry-walk", type=Path, required=True)
    a = p.parse_args()

    wid = "MON_PROLOGUE_CRACKED_WRAITH_01"
    iid = "MON_PROLOGUE_SEVERED_INFANTRY_01"
    wc = a.root / "04_concepts" / "work" / wid
    ic = a.root / "04_concepts" / "work" / iid
    ws = a.root / "05_sprites" / "work" / wid
    ins = a.root / "05_sprites" / "work" / iid
    for d in (wc, ic, ws, ins):
        d.mkdir(parents=True, exist_ok=True)

    wcan = concept_candidates(a.wraith_concepts, wc, wid)
    ican = concept_candidates(a.infantry_concepts, ic, iid)
    comparison(wcan, "금 간 잔령 · 정면 디자인 비교",
               ["단순·둥근 표준형", "각진 가면 강조", "균열 파츠 강조", "감정 파손 강조", "도시 잔재 강조"],
               0, wc / f"{wid}_front_comparison_sheet.jpg")
    comparison(ican, "끊긴 보병 · 정면 디자인 비교",
               ["비대칭 갑주형", "둥근 반가면형", "정면 균형 표준형", "각진 파손형", "경량 갑주형"],
               2, ic / f"{iid}_front_comparison_sheet.jpg")
    wrec = wc / f"{wid}_recommended_front_A.png"
    irec = ic / f"{iid}_recommended_front_C.png"
    wcan[0].save(wrec)
    ican[2].save(irec)

    jobs = [
        (wid, "idle", a.wraith_idle, ws, 230),
        (wid, "move", a.wraith_move, ws, 230),
        (iid, "idle", a.infantry_idle, ins, 238),
        (iid, "walk", a.infantry_walk, ins, 238),
    ]
    qa = []
    for monster, motion, source, out_dir, baseline in jobs:
        source_copy = out_dir / f"{monster}_{motion}_16f_chroma_source.png"
        Image.open(source).save(source_copy)
        frames = extract_animation(source, baseline)
        png = out_dir / f"{monster}_{motion}_16f_4x4.png"
        gif = out_dir / f"{monster}_{motion}_6fps.gif"
        save_sheet(frames, png)
        save_gif(frames, gif)
        entry = qa_sheet(png, baseline, motion)
        entry.update({"animation": motion, "preview_gif": str(gif),
                      "preview_sha256": sha256(gif), "fps": FPS, "loop": True})
        qa.append(entry)

    manifest = {
        "schema": "danmaek.sprite_qa_manifest.v1",
        "generated_by": "design_orchestra / built-in image generation + local Pillow post-processing",
        "external_ai_api_used": False,
        "unity_handoff": "BLOCKED_PENDING_CENTRAL_LOCAL_QA_AND_USER_APPROVAL",
        "global_spec": {"style": "SD 2.5-head mobile idle RPG",
                        "palette": "modern urban collapse: neon cyan, purple gray, noise",
                        "family": "underworld corruption", "grid": "4x4",
                        "cell_px": [256, 256], "sheet_px": [1024, 1024],
                        "frame_count": 16, "fps": 6, "pivot": [0.5, 1.0],
                        "background": "transparent RGBA"},
        "monsters": {
            wid: {"korean_name": "금 간 잔령", "recommended_candidate": "A",
                  "recommendation": "짧고 둥근 무다리 실루엣과 세로 균열 흰 가면이 축소 화면에서 가장 명확함",
                  "concept_dir": str(wc), "recommended_front": str(wrec),
                  "animations": [q for q in qa if wid in q["path"]]},
            iid: {"korean_name": "끊긴 보병", "recommended_candidate": "C",
                  "recommendation": "정면 균형, 넓은 어깨, 파손 가면과 짧은 단도의 판독성이 가장 안정적임",
                  "concept_dir": str(ic), "recommended_front": str(irec),
                  "animations": [q for q in qa if iid in q["path"]]},
        },
    }
    manifest["overall_pass"] = all(q["pass"] for q in qa)
    out = a.root / "05_sprites" / "work" / "PROLOGUE_MONSTERS_SPRITE_QA_MANIFEST.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(out), "overall_pass": manifest["overall_pass"],
                      "qa": [{"animation": q["animation"], "pass": q["pass"],
                               "checks": q["checks"]} for q in qa]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
