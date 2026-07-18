#!/usr/bin/env python3
# 灵剪 · SFX 混音（按 SFX_STRATEGY 把音效卡到画面节点上）
# ---------------------------------------------------------------
# 每个音效对应一个明确画面动作;快节奏截短去拖尾、收尾留余韵;固定增益混音(不 sidechain/不 ducking,BGM 已在 full 里全程恒定垫底)+ alimiter。
# 用法:
#   python3 sfx_mix.py <full.mp4>(已含配音+BGM) <hits.json> <out.mp4> [sfxdir]
# hits.json: [{"t":秒, "sfx":"音效名", "vol":0.4, "trim":0.3|null, "for":"对应画面(注释)"}, ...]
#   trim 非空 = 截短去拖尾(快节奏打击);null = 全长(收尾/重击留余韵)
import subprocess, sys, json, os
SFXDIR_DEFAULT = os.path.expanduser("~/.claude/skills/hyperframes-media/assets/sfx")

def mix(full, hits, out, sfxdir=SFXDIR_DEFAULT):
    missing = [h["sfx"] for h in hits if not os.path.exists(f"{sfxdir}/{h['sfx']}.mp3")]
    if missing:
        raise SystemExit(
            f"缺音效文件 {missing} @ {sfxdir}\n"
            "音效库不随灵剪发布(见 SFX_STRATEGY.md「音效库来源」):自备 mp3 到该目录,"
            "或把音效目录作为第 4 个位置参数传入(sfx_mix.py full.mp4 hits.json out.mp4 <目录>),"
            "或安装 hyperframes-media skill。"
        )
    inputs = ["-i", full]
    for h in hits: inputs += ["-i", f"{sfxdir}/{h['sfx']}.mp3"]
    fc = []; labels = ["[0:a]"]
    for i, h in enumerate(hits, 1):
        ms = int(h["t"] * 1000); v = h.get("vol", 0.4); sh = h.get("trim")
        if sh:
            fc.append(f"[{i}:a]atrim=0:{sh},afade=t=out:st={round(sh-0.06,2)}:d=0.06,adelay={ms}|{ms},volume={v}[s{i}]")
        else:
            fc.append(f"[{i}:a]adelay={ms}|{ms},volume={v}[s{i}]")
        labels.append(f"[s{i}]")
    fc.append("".join(labels) + f"amix=inputs={len(hits)+1}:duration=first:normalize=0,alimiter=limit=0.95[mix]")
    cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", ";".join(fc),
           "-map", "0:v", "-map", "[mix]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", out]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0, (r.stderr[-400:] if r.returncode else "OK")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("用法: python3 sfx_mix.py <full.mp4> <hits.json> <out.mp4> [sfxdir]"); sys.exit(1)
    hits = json.load(open(sys.argv[2]))
    sfxdir = sys.argv[4] if len(sys.argv) > 4 else SFXDIR_DEFAULT
    ok, msg = mix(sys.argv[1], hits, sys.argv[3], sfxdir)
    print(f"✓ {len(hits)} 个音效 → {sys.argv[3]}" if ok else "ERR: " + msg)
