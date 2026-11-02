#!/usr/bin/env python3
"""按住连续走位标定（vol11 goto_pos_fast 经验移植到 vol12 美術館）。

标定项：
  A. 光标高亮检测（B 通道 62~150 隔离 光标(254,253,96) vs 灯泡黄 B≈31）
  B. hold Right/Left/Up/Down 连续移动速率 + 启动延迟（vol11 实测 ~0.10s/列）
  C. 板边行为：hold 到达 w-1/h-1 后是钳位还是 wrap（wrap=安全红线）
  D. 单步 wait=0.20/hold=0.02 是否零丢键（若零丢则短距修正用 0.20）

产出：/tmp/cal_hold_result.json
"""
import json
import subprocess
import sys
import time

sys.path.insert(0, ".")
import numpy as np

import ds
from play_akari_seg3 import (VR_BY_SIZE, VCW, escape_to_select, goto_level,
                             grab_np, reset_level, wait_select_page,
                             has_start_overlay)

PUZZLES = json.load(open(
    "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.12：美术馆/validation/puzzles.json"))["ふつう"]
PZ = {p["rec"]: p for p in PUZZLES}


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# 下屏菜单橙色图标渗入的格子（vc,vr）——光标真在该处时靠 recovery 兜底
ICON_MASK = {(11, 2), (11, 3)}


def cell_rgb(a, vc, vr):
    cx = int(16 + 16 * (vc + 0.5))
    cy = int(208 + 16 * (vr + 0.5))
    if cx + 5 > a.shape[1] or cy + 5 > a.shape[0] or cx - 5 < 0 or cy - 5 < 0:
        return None
    return a[cy - 4:cy + 5, cx - 4:cx + 5].reshape(-1, 3).mean(axis=0)


def find_cursor(pz, exp, search=3):
    """下屏橙色描边检测。光标=格线上的橙色空心框（格±3px 窗口内 ~48 橙像素，
    邻格共享边 ~20）。静态掩码排除菜单图标区 (11,2)/(11,3)。
    返回 (bx,by) 或 None。"""
    w, h = pz["w"], pz["h"]
    vrmax = VR_BY_SIZE[(w, h)]
    exp_dc = clamp(exp[0] - 5, 0, w - VCW)
    exp_dr = clamp(exp[1] - 9, 0, h - vrmax)
    a = grab_np()
    cands = sorted({(clamp(exp_dc + d, 0, w - VCW), clamp(exp_dr + d2, 0, h - vrmax))
                    for d in range(-search, search + 1)
                    for d2 in range(-search, search + 1)},
                   key=lambda c: abs(c[0] - exp_dc) + abs(c[1] - exp_dr))
    for (dc, dr) in cands:
        best, bestn = None, 0
        for vr in range(0, min(vrmax, h - dr)):
            for vc in range(0, min(VCW, w - dc)):
                if (vc, vr) in ICON_MASK:
                    continue
                y0, x0 = 208 + 16 * vr, 16 + 16 * vc
                reg = a[max(y0 - 3, 0):y0 + 19, max(x0 - 3, 0):x0 + 19]
                R, G, B = reg[:, :, 0], reg[:, :, 1], reg[:, :, 2]
                n = int(((R > 200) & (G > 110) & (G < 215) & (B < 95)).sum())
                if n > bestn:
                    bestn, best = n, (dc + vc, dr + vr)
        if best is not None and bestn >= 30:
            return best
    return None


def hold_key(key, sec):
    """按住不放连续移动（vol11 _hold_key 同款）。"""
    ds.ensure_window()
    subprocess.run(["xdotool", "keydown", key, "sleep", f"{sec:.3f}",
                    "keyup", key], env=ds.ENV)
    time.sleep(0.30)


def step(key, wait=0.30):
    ds.press(key, wait=wait, hold=0.02)


def zero_cursor(pz, w, h):
    for _ in range(h + 2):
        step("Up")
    for _ in range(w + 2):
        step("Left")
    time.sleep(0.5)
    return find_cursor(pz, (0, 0))


def main():
    res = {}
    pz = PZ[31]
    w, h = pz["w"], pz["h"]
    print(f"== 标定盘 Q31 {w}x{h}", flush=True)

    if not wait_select_page(8.0):
        print("不在选关页，尝试 escape_to_select", flush=True)
        escape_to_select()
    assert goto_level(31), "进 Q31 失败"
    time.sleep(2.0)
    assert reset_level(), "reset 失败"
    time.sleep(1.0)
    pos = zero_cursor(pz, w, h)
    print(f"[A] 归零检测: {pos} (期望 (0,0))", flush=True)
    assert pos == (0, 0), f"光标检测/归零失败: {pos}"
    cur = [0, 0]

    # ---- B. hold Right 速率：0.4 / 0.8 / 1.2s 三点 ----
    rates = {}
    print("== B. hold Right 速率", flush=True)
    pts = []
    for t in (0.4, 0.8, 1.2):
        start = tuple(cur)
        hold_key("Right", t)
        got = find_cursor(pz, (min(cur[0] + int(t / 0.10) + 3, w - 1), cur[1]))
        assert got is not None, f"hold {t}s 后找不到光标"
        moved = got[0] - cur[0]
        pts.append((t, moved))
        cur[0] = got[0]
        print(f"  hold Right {t}s: {start}->{got} (moved {moved})", flush=True)
        if cur[0] >= w - 1:
            break
    # 线性拟合 moved = (t - T0)/rate
    if len(pts) >= 2:
        t1, m1 = pts[0]
        t2, m2 = pts[-1]
        if m2 > m1:
            rate = (t2 - t1) / (m2 - m1)
            t0h = t1 - m1 * rate
            rates["Right"] = (rate, max(0.0, t0h))
    # 回左（单步，顺带测回程）
    while cur[0] > 0:
        step("Left"); cur[0] -= 1
    got = find_cursor(pz, (0, cur[1]))
    print(f"  回零复核: {got}", flush=True)

    # ---- B2. hold Down 速率（18×10 纵向无滚动，dr 恒 0）----
    print("== B2. hold Down 速率", flush=True)
    pts = []
    for t in (0.4, 0.8):
        start = tuple(cur)
        hold_key("Down", t)
        got = find_cursor(pz, (cur[0], min(cur[1] + int(t / 0.10) + 3, h - 1)))
        assert got is not None, f"hold Down {t}s 后找不到光标"
        moved = got[1] - cur[1]
        pts.append((t, moved))
        cur[1] = got[1]
        print(f"  hold Down {t}s: {start}->{got} (moved {moved})", flush=True)
        if cur[1] >= h - 1:
            break
    if len(pts) >= 2 and pts[-1][1] > pts[0][1]:
        rate = (pts[-1][0] - pts[0][0]) / (pts[-1][1] - pts[0][1])
        rates["Down"] = (rate, max(0.0, pts[0][0] - pts[0][1] * rate))
    while cur[1] > 0:
        step("Up"); cur[1] -= 1

    # ---- C. 板边行为：光标到 w-1，再 hold Right 0.5s，看是否 wrap ----
    print("== C. 板边行为", flush=True)
    while cur[0] < w - 1:
        step("Right"); cur[0] += 1
    got = find_cursor(pz, (w - 1, cur[1]))
    print(f"  到达右缘: {got} (期望 ({w-1},{cur[1]}))", flush=True)
    hold_key("Right", 0.5)
    got2 = find_cursor(pz, (w - 1, cur[1]), search=4)
    print(f"  右缘再 hold 0.5s: {got2}", flush=True)
    res["edge_hold_right"] = list(got2) if got2 else None
    # 回零
    while cur[0] > 0:
        step("Left"); cur[0] -= 1
    time.sleep(0.3)
    got = find_cursor(pz, (0, cur[1]))
    print(f"  回零: {got}", flush=True)
    if got and got[0] != 0:      # wrap 到了别处 → 记账复位
        cur = list(zero_cursor(pz, w, h) or (0, 0))
        print(f"  重新归零: {cur}", flush=True)

    # ---- D. 单步 wait=0.20 零丢键测试：Right×12 → 应到 col12 ----
    print("== D. 单步 wait=0.20 丢键测试", flush=True)
    for _ in range(12):
        step("Right", wait=0.20)
    got = find_cursor(pz, (12, cur[1]))
    print(f"  Right×12 @0.20s: {got} (期望 col=12)", flush=True)
    res["step20_loss"] = None if got is None else got[0] - 12
    while cur[0] < 12:
        step("Right", wait=0.20); cur[0] += 1
    while cur[0] > 0:
        step("Left", wait=0.20); cur[0] -= 1

    res["rates"] = {k: list(v) for k, v in rates.items()}
    print(json.dumps(res, ensure_ascii=False, indent=1), flush=True)
    json.dump(res, open("/tmp/cal_hold_result.json", "w"))


if __name__ == "__main__":
    main()
