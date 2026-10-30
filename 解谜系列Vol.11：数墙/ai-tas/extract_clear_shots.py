#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 seg4 实况片段抽取每关「通关页」截图，更新 validation/mode4_hard/lNNN_clear.png。

目标画面（用户定义）：上屏 = 涂满的答案棋盘（含 第XXX問 / SIZE / TIME 横幅），
                        下屏 = クリアタイム + 六颗金星 + 总分。

判定复用仓库既有工具：
  has_time_band()  check_evidence.py  —— 深蓝 TIME 横幅，确认是通关页
  stars_robust()   本文件             —— 数金星（6 槽布局 x=60..200，列高>=3 去碎块）

★ 为何不用 mode2_fast.stars_gold：部分通关页的星带里，每颗星旁会有 1px 高的
  抗锯齿碎块，stars_gold 的 gap>3 分组会把它切成独立组，6 星被读成 9~12。
  stars_robust 加「列高>=3」过滤即可稳定读出 6（实测星主体列高 5~7）。
  stars_gold 本体未改，mode2/mode3 历史图判定不受影响。

选帧策略：
  在片段末尾 SCAN_SEC 内按 FPS 抽帧 -> 只保留 has_time_band 的帧并记录星数
  -> 找「连续 STABLE_N 帧星数都恰好等于 6」的稳定区间（避开星星点亮的中间态：
     动画中间态下金色像素会被拆成碎块，stars_gold 会读出 9~12 这种假值）
  -> 在该区间内取「亮度 >= 峰值 93% 的最后一帧」：亮度过滤避开淡出变暗，
     取最后一帧保证得分已滚动到位。

用法:
  python3 extract_clear_shots.py 1 80        # 抽 lv1..80
  python3 extract_clear_shots.py 1 3 --dry   # 只报结果不落盘
"""
import os
import sys
import glob
import shutil
import subprocess
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from mode2_fast import stars_gold          # noqa: E402
from check_evidence import has_time_band    # noqa: E402

SRC_DIR = "/workspace"
OUT_DIR = os.path.normpath(os.path.join(HERE, "..", "validation", "mode4_hard"))
SCAN_SEC = 45.0
FPS = 10
MAX_STARS = 6
STABLE_N = 3        # 6 星需连续 3 帧（10fps 下 0.3s）稳定，排除点亮动画中间态


def stars_robust(im, min_col_h=3, gap=3, y0=294, y1=320, x0=60, x1=200):
    """鲁棒星数：同 stars_gold 的金色判据，但过滤「列高 < min_col_h」的碎块。

    ★ 2026-10-27 修：stars_gold 会在部分通关页把 6 星读成 9~12。
      实测 l073 的星带分段为
        (70..76, 列高7) (81..82, 列高1) (92..97,6) (102..103,1) ...
      即每颗星旁多出 1px 高的抗锯齿碎块（星形尖角），gap>3 就被切成独立组。
      按列高 >=3 过滤后 6 段整齐（星主体列高实测 5~7：l073=6~7、l080=5~6）。
      不改 stars_gold 本体，避免影响 mode2/mode3 已验收的历史图判定。
    """
    a = np.asarray(im.convert("RGB")).astype(int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    gold = (R > 200) & (G > 120) & (B < 150) & (G > R * 0.45) & (G < R * 0.95)
    prof = gold[y0:y1, x0:x1].sum(axis=0)
    xs = np.where(prof >= min_col_h)[0]
    if len(xs) == 0:
        return 0
    groups = 1
    prev = xs[0]
    for x in xs[1:]:
        if x - prev > gap:
            groups += 1
        prev = x
    return groups


def clip_duration(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", p], capture_output=True, text=True)
    return float(r.stdout.strip())


def mean_lum(im):
    return float(np.asarray(im.convert("L"), dtype=float).mean())


def pick_frame(lvl):
    """返回 (图片路径, 说明)。找不到返回 (None, 原因)。"""
    src = os.path.join(SRC_DIR, "数墙_seg4_lv%d.mp4" % lvl)
    if not os.path.exists(src):
        return None, "src missing"
    dur = clip_duration(src)
    start = max(0.0, dur - SCAN_SEC)
    td = tempfile.mkdtemp(prefix="shot_l%03d_" % lvl)
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y",
                        "-ss", "%.2f" % start, "-i", src,
                        "-vf", "fps=%d" % FPS, "-vsync", "0",
                        os.path.join(td, "f%04d.png")], capture_output=True)
        # 逐帧：非通关页记 None，通关页记 (路径, 亮度, 星数)
        seq = []
        for f in sorted(glob.glob(os.path.join(td, "f*.png"))):
            im = Image.open(f).convert("RGB")
            if not has_time_band(im):
                seq.append((f, None, None))
                continue
            seq.append((f, mean_lum(im), stars_robust(im)))
        n_tb = sum(1 for s in seq if s[2] is not None)
        # 找「连续 STABLE_N 帧星数恰为 6」的稳定区间
        runs = []
        i = 0
        while i < len(seq):
            if seq[i][2] == MAX_STARS:
                j = i
                while j < len(seq) and seq[j][2] == MAX_STARS:
                    j += 1
                if j - i >= STABLE_N:
                    runs.append((i, j - 1))
                i = j
            else:
                i += 1
        if not runs:
            return None, "timeband=%d 但无连续 %d 帧的稳定 6 星" % (n_tb, STABLE_N)
        s, e = runs[-1]
        cands = [seq[k] for k in range(s, e + 1)]
        mx = max(c[1] for c in cands)
        good = [c for c in cands if c[1] >= mx * 0.93]
        f, lum, n = good[-1]
        keep = "/tmp/pick_l%03d.png" % lvl
        shutil.copy(f, keep)
        return keep, "稳定6星区间=%d帧 选中亮度=%.1f(峰%.1f) timeband帧=%d" % (
            e - s + 1, lum, mx, n_tb)
    finally:
        shutil.rmtree(td, ignore_errors=True)


def main():
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 80
    dry = "--dry" in sys.argv
    os.makedirs(OUT_DIR, exist_ok=True)
    print("=== extract clear shots lv%d..%d -> %s%s" % (lo, hi, OUT_DIR, " (dry)" if dry else ""),
          flush=True)
    ok, fail = [], []
    for L in range(lo, hi + 1):
        p, msg = pick_frame(L)
        if p is None:
            print("  l%03d FAIL  %s" % (L, msg), flush=True)
            fail.append(L)
            continue
        dst = os.path.join(OUT_DIR, "l%03d_clear.png" % L)
        if not dry:
            shutil.copy(p, dst)
        im = Image.open(p)
        print("  l%03d ok    %s  %s" % (L, im.size, msg), flush=True)
        ok.append(L)
    print("\n=== 完成: 成功 %d, 失败 %d ===" % (len(ok), len(fail)), flush=True)
    if fail:
        print("失败关卡:", fail, flush=True)
    return 0 if not fail else 1


if __name__ == "__main__":
    sys.exit(main())
