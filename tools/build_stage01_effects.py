from __future__ import annotations

import argparse, hashlib, json, sys
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import build_prologue_monsters as common
from build_stage01_background import remove_magenta

CELL, FPS = 256, 6


def extract(source, cols, rows, count, key):
    raw = Image.open(source).convert("RGBA")
    crops = []
    for i in range(count):
        x0, x1 = round(raw.width*(i%cols)/cols), round(raw.width*((i%cols)+1)/cols)
        y0, y1 = round(raw.height*(i//cols)/rows), round(raw.height*((i//cols)+1)/rows)
        keyed = remove_magenta(raw.crop((x0,y0,x1,y1))) if key == "magenta" else common.chroma_to_alpha(raw.crop((x0,y0,x1,y1)))
        box = keyed.getchannel("A").getbbox()
        if box:
            crops.append(keyed.crop(box))
        else:
            # A fully vanished terminal frame is valid; retain an effectively
            # invisible centered marker so grid metrics remain deterministic.
            crops.append(Image.new("RGBA", (1, 1), (255, 255, 255, 1)))
    scale = min(224/max(x.width for x in crops), 224/max(x.height for x in crops))
    frames=[]
    for c in crops:
        c=c.resize((max(1,round(c.width*scale)),max(1,round(c.height*scale))),Image.Resampling.LANCZOS)
        f=Image.new("RGBA",(CELL,CELL)); f.alpha_composite(c,((CELL-c.width)//2,(CELL-c.height)//2)); frames.append(f)
    return frames


def save(frames, cols, rows, png, gif):
    sheet=Image.new("RGBA",(cols*CELL,rows*CELL))
    for i,f in enumerate(frames): sheet.alpha_composite(f,((i%cols)*CELL,(i//cols)*CELL))
    sheet.save(png)
    seq=[]
    for f in frames:
        bg=Image.new("RGBA",f.size,(22,22,34,255)); bg.alpha_composite(f)
        seq.append(bg.convert("P",palette=Image.Palette.ADAPTIVE,colors=255))
    seq[0].save(gif,save_all=True,append_images=seq[1:],duration=167,loop=0,disposal=2,optimize=False)


def qa(png, cols, rows, count):
    im=Image.open(png).convert("RGBA"); fs=[]; boxes=[]
    for i in range(count):
        f=im.crop(((i%cols)*CELL,(i//cols)*CELL,((i%cols)+1)*CELL,((i//cols)+1)*CELL)); fs.append(f); boxes.append(f.getchannel("A").getbbox())
    centers=[((b[0]+b[2])/2,(b[1]+b[3])/2) for b in boxes]
    hs=[hashlib.sha256(f.tobytes()).hexdigest() for f in fs]
    checks={"rgba_png":im.mode=="RGBA","grid_dimensions":im.size==(cols*CELL,rows*CELL),"frame_count":len(fs)==count,
            "transparent_corners":all(f.getpixel(p)[3]==0 for f in fs for p in ((0,0),(255,0),(0,255),(255,255))),
            "no_duplicate_frames":len(set(hs))==count,
            "center_tolerance_1px":max(x for x,y in centers)-min(x for x,y in centers)<=1 and max(y for x,y in centers)-min(y for x,y in centers)<=1,
            "cell_padding_min_8px":all(b[0]>=8 and b[1]>=8 and b[2]<=248 and b[3]<=248 for b in boxes)}
    return {"path":str(png),"sha256":common.sha256(png),"checks":checks,"pass":all(checks.values()),"centers":centers}


def main():
    p=argparse.ArgumentParser(); p.add_argument("--root",type=Path,required=True)
    for n in ("pulse_strike","normal_hit","underworld_hit","monster_vanish","ground_crack"):
        p.add_argument(f"--{n.replace('_','-')}",dest=n,type=Path,required=True)
    a=p.parse_args(); out=a.root/"05_sprites"/"work"/"STAGE01_COMBAT_EFFECTS"; out.mkdir(parents=True,exist_ok=True)
    specs=[("pulse_strike",a.pulse_strike,4,4,16,"magenta"),("normal_hit",a.normal_hit,4,2,8,"magenta"),
           ("underworld_hit",a.underworld_hit,4,2,8,"green"),("monster_vanish",a.monster_vanish,4,3,12,"green"),
           ("ground_crack",a.ground_crack,4,4,16,"magenta")]
    entries=[]
    for name,source,cols,rows,count,key in specs:
        Image.open(source).save(out/f"VFX_STAGE01_{name}_chroma_source.png")
        frames=extract(source,cols,rows,count,key)
        png=out/f"VFX_STAGE01_{name}_{count}f_{cols}x{rows}.png"; gif=out/f"VFX_STAGE01_{name}_6fps.gif"
        save(frames,cols,rows,png,gif); e=qa(png,cols,rows,count); e.update({"effect":name,"frames":count,"fps":FPS,"preview_gif":str(gif),"preview_sha256":common.sha256(gif)}); entries.append(e)
    manifest={"schema":"danmaek.stage01.combat_effects.v1","external_ai_api_used":False,"unity_handoff":"BLOCKED_PENDING_USER_APPROVAL",
              "cell_px":[CELL,CELL],"pivot":[0.5,0.5],"effects":entries,"overall_pass":all(x["pass"] for x in entries)}
    m=out/"STAGE01_COMBAT_EFFECTS_QA_MANIFEST.json"; m.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"manifest":str(m),"overall_pass":manifest["overall_pass"],"failed":[x["effect"] for x in entries if not x["pass"]]},ensure_ascii=False))


if __name__=="__main__": main()
