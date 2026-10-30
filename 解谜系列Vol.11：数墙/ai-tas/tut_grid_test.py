#!/usr/bin/env python3
"""独立验证 detect_grid：当前帧 + 历史帧回归。"""
import sys, glob
sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import numpy as np
from PIL import Image
import tut, ds

def check(img_path=None, live=False):
    if live:
        f = tut.grab_np()
    else:
        f = np.asarray(Image.open(img_path).convert("RGB")).astype(int)
    g = tut.detect_grid(f, verbose=True)
    if not g:
        print(f"  {img_path or 'live'}: NO GRID")
        return None
    x0, y0, cols, rows = g
    print(f"  {img_path or 'live'}: OK x0={x0} y0={y0} cols={cols} rows={rows}")
    return g

if __name__ == "__main__":
    print("== live ==")
    g = check(live=True)
    if g:
        # 保存标注图: 画格线
        f = tut.grab_np()
        img = Image.fromarray(f.astype(np.uint8))
        arr = np.asarray(img).copy()
        x0, y0, cols, rows = g
        for i in range(cols + 1):
            x = x0 + 24 * i
            if 0 <= x < 256:
                arr[y0:y0 + 24 * rows, x] = [255, 0, 0]
        for j in range(rows + 1):
            y = y0 + 24 * j
            if 0 <= y < 384:
                arr[y, x0:x0 + 24 * cols] = [255, 0, 0]
        Image.fromarray(arr).resize((512, 768), Image.NEAREST).save(
            "/tmp/tut_grid_annot.png")
        print("saved /tmp/tut_grid_annot.png")
    print("== regression on saved frames ==")
    for p in sorted(glob.glob("/tmp/tut_f*.png")) + sorted(glob.glob("/tmp/tut_step*.png")) + sorted(glob.glob("/tmp/tut_now*.png")):
        check(p)
