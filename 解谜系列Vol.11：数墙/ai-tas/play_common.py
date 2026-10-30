"""入門 6x6 盘面公用层: 几何/扫描。"""
import sys, time
sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import ds
import numpy as np

PX0, PY0, P, N = 35, 227, 24, 6   # 窗口坐标格心

def grab_gray():
    return np.asarray(ds.grab(None).convert("L"), dtype=float)

def scan_board(g=None):
    """返回 {(r,c): 'B'|'W'|'C'}  黑/白/线索(含数字). C 也可能是白印。"""
    if g is None: g = grab_gray()
    out = {}
    for r in range(N):
        for c in range(N):
            cx, cy = PX0+P*c, PY0+P*r
            m = g[cy-7:cy+7, cx-7:cx+7].mean()
            out[(r,c)] = "B" if m < 90 else ("W" if m > 215 else "C")
    return out

def show(b):
    for r in range(N):
        print("".join(b[(r,c)] for c in range(N)))
