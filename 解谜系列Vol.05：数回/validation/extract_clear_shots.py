#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""从 Vol.05 数回 270 关录像抽取每关『刚显示 Completion』帧作为 validation。
惯例对齐其他 vol：validation/modeN_xxx/lNNN_clear.png，256x384，P 模式调色板 PNG。
判据：Completion 艺术字模板匹配（跨尺寸通用）；取峰值 90% 的首帧。
"""
import os, sys, re, glob, subprocess, tempfile, csv, time
import cv2, numpy as np
from PIL import Image
from concurrent.futures import ProcessPoolExecutor, as_completed

REPO = "/workspace/hudson_tas/解谜系列Vol.05：数回/validation"
TMPL_BIG = "/tmp/v5_tpl_big.png"
TMPL_NYUU = "/tmp/v5_tpl_nyuu.png"

# mode -> (目录名, [(录像目录, 文件名前缀), ...])
MODES = {
    "mode1_tutorial": [("/workspace/vol5_recordings", "数回_入門_")],
    "mode2_easy": [("/workspace/vol5_recordings_10x10", "数回_やさしい10x10_"),
                   ("/workspace/vol5_recordings_18x10", "数回_やさしい18x10_")],
    "mode3_medium": [("/workspace/vol5_recordings_futsuu_18x10", "数回_ふつう18x10_"),
                     ("/workspace/vol5_recordings_futsuu_24x14", "数回_ふつう24x14_")],
    "mode4_hard": [("/workspace/vol5_recordings_muzukashii_24x14", "数回_むずかしい24x14_"),
                   ("/workspace/vol5_recordings_muzukashii_36x20", "数回_むずかしい36x20_")],
}

_TPLS = None
def templates():
    global _TPLS
    if _TPLS is None:
        _TPLS = [
            cv2.imread(TMPL_BIG)[262:312, 30:230],
            cv2.imread(TMPL_NYUU)[262:312, 30:230],
        ]
    return _TPLS

def comp_score(frame_bgr):
    reg = frame_bgr[192:384, :]
    best = 0.0
    for t in templates():
        _, mx, _, _ = cv2.minMaxLoc(cv2.matchTemplate(reg, t, cv2.TM_CCOEFF_NORMED))
        if mx > best: best = mx
    return best

def frames_4fps(path):
    """流式产出 4fps 的 256x384 BGR 帧。"""
    cmd = ['ffmpeg','-v','error','-i',path,'-vf','fps=4',
           '-f','rawvideo','-pix_fmt','bgr24','-']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    fs = 256*384*3
    try:
        while True:
            buf = p.stdout.read(fs)
            if len(buf) < fs: break
            yield np.frombuffer(buf, np.uint8).reshape(384,256,3)
    finally:
        try: p.stdout.close()
        except Exception: pass
        try: p.wait(timeout=5)
        except Exception: p.kill()

def process_one(task):
    mode, lvl, src = task
    out_dir = os.path.join(REPO, mode)
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"l{lvl:03d}_clear.png")
    scores = []
    frames = []
    peak = 0.0
    for i, fr in enumerate(frames_4fps(src)):
        s = comp_score(fr)
        scores.append(s)
        frames.append(fr)          # 单关最多 ~1300 帧 * 294912B ≈ 380MB，内存充足
        if s > peak: peak = s
    if not frames:
        return (mode, lvl, os.path.basename(src), 0.0, -1, out, "NO_FRAMES")
    if peak < 0.5:
        return (mode, lvl, os.path.basename(src), round(peak,3), -1, out, "NO_COMPLETION")
    thr = peak * 0.9
    pick_i = next((i for i,s in enumerate(scores) if s >= thr), int(np.argmax(scores)))
    fr = frames[pick_i]
    # P 模式调色板 PNG，与其他 vol 一致
    img = Image.fromarray(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
    img.convert('P', palette=Image.ADAPTIVE, colors=256).save(out, optimize=True)
    return (mode, lvl, os.path.basename(src), round(peak,3), round(pick_i/4,1), out, "OK")

def main():
    tasks = []
    for mode, sources in MODES.items():
        lvl_of = {}
        for d, prefix in sources:
            for f in glob.glob(os.path.join(d, prefix+"*.mp4")):
                m = re.search(r'第(\d+)問', os.path.basename(f))
                if not m: continue
                lvl = int(m.group(1))
                if lvl in lvl_of:
                    print(f"[WARN] duplicate lvl {mode} l{lvl}: {lvl_of[lvl]} vs {f}", file=sys.stderr)
                lvl_of[lvl] = f
        for lvl in sorted(lvl_of):
            tasks.append((mode, lvl, lvl_of[lvl]))
    print(f"总任务: {len(tasks)} 关")
    results = []
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(process_one, t): t for t in tasks}
        for n, fu in enumerate(as_completed(futs), 1):
            r = fu.result()
            results.append(r)
            if n % 20 == 0 or r[6] != "OK":
                print(f"[{n}/{len(tasks)}] {r[0]} l{r[1]:03d} peak={r[3]} t={r[4]} {r[6]}", flush=True)
    results.sort(key=lambda x:(x[0],x[1]))
    with open(os.path.join(REPO, "_extract_log.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["mode","lvl","src","peak_score","pick_sec","out","status"])
        w.writerows(results)
    ok = sum(1 for r in results if r[6]=="OK")
    bad = [r for r in results if r[6]!="OK"]
    print(f"\n完成: {ok}/{len(results)} OK, {len(bad)} 失败, 用时 {time.time()-t0:.0f}s")
    for r in bad:
        print("  FAIL:", r)

if __name__ == "__main__":
    main()
