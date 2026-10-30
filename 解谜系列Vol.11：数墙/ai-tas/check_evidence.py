#!/usr/bin/env python3
"""校验通关证据图：逐张读金星数 + 是否有 TIME 横幅。

用法: python3 check_evidence.py <evidence_dir> [max_stars]
  默认目录 validation/mode2_easy，默认满星 4（やさしい，规则 n+2）。
输出每个文件的金星数，末尾汇总；有缺失或未满星时退出码 1。
"""
import glob
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mode2_fast import stars_gold


def has_time_band(im):
    """通关页 TIME 行：深蓝横幅 (49,82,115) 区域。"""
    a = np.asarray(im.convert("RGB")).astype(int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    reg = (abs(R[245:320, 30:225] - 49) < 15) & (abs(G[245:320, 30:225] - 82) < 15) \
        & (abs(B[245:320, 30:225] - 115) < 22)
    return int(reg.sum()) > 1800


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else \
        "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/validation/mode2_easy"
    mx = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    files = sorted(glob.glob(os.path.join(d, "l*_clear.png")))
    if not files:
        print("no evidence files")
        return 1
    bad = []
    nums = []
    for f in files:
        im = Image.open(f).convert("RGB")
        n = stars_gold(im)
        ok = has_time_band(im)
        tag = "" if (n >= mx and ok) else "  <-- WARN"
        print(f"{os.path.basename(f)} stars={n} time_band={ok}{tag}")
        if n < mx or not ok:
            bad.append(os.path.basename(f))
        try:
            nums.append(int(os.path.basename(f)[1:4]))
        except ValueError:
            pass
    nums = sorted(set(nums))
    miss = [i for i in range(1, (nums[-1] if nums else 0) + 1) if i not in nums]
    print(f"\ntotal={len(files)} max_stars={mx} bad={len(bad)}")
    if miss:
        print("missing:", [f"l{i:03d}" for i in miss])
    return 0 if not bad and not miss else 1


if __name__ == "__main__":
    sys.exit(main())
