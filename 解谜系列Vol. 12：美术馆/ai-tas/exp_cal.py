#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘面视口标定：找出真实几何 + 滚动响应 + 点灯对墙检测的影响。

用法: python3.11 exp_cal.py <关卡号>
输出: /tmp/cal_*.png 截图 + 控制台诊断报告
"""
import sys
import time

import numpy as np
from PIL import Image

import ds
import play_akari_seg3 as P
import state2

SHOT = "/tmp/cal"

# 屏幕可扫描范围（16px 网格，X0=16 Y0=208）
X0, Y0, PP = 16, 208, 16
SCR_COLS = 15      # 16+16*15 = 256
SCR_ROWS = 11      # 208+16*11 = 384


def shot(tag):
    im = P.grab_np()
    Image.fromarray(im.astype("uint8")).save(f"{SHOT}_{tag}.png")
    return im


def scr_walls(a, ncols=SCR_COLS, nrows=SCR_ROWS):
    """读屏幕上每格是否为墙（蓝色块）。"""
    out = []
    for r in range(nrows):
        row = ""
        for c in range(ncols):
            cx, cy = int(X0 + PP * (c + 0.5)), int(Y0 + PP * (r + 0.5))
            if cy + 6 > a.shape[0]:
                row += "?"
                continue
            cell = a[cy - 5:cy + 6, cx - 5:cx + 6].reshape(-1, 3)
            blue = ((cell[:, 2] > 100) & (cell[:, 2] > cell[:, 0] + 35)).mean()
            row += "W" if blue > 0.35 else "."
        out.append(row)
    return out


def find_offset(a, exp, w, h):
    """二维滑动匹配：返回 (视口列偏移 dc, 行偏移 dr, 匹配分, 有效格数)。"""
    scr = scr_walls(a)
    best = (-1, None)
    for dr in range(-2, h):
        for dc in range(-2, w):
            m = tot = 0
            for r in range(SCR_ROWS):
                for c in range(SCR_COLS):
                    gy, gx = r + dr, c + dc
                    if not (0 <= gy < h and 0 <= gx < w):
                        continue
                    ch = scr[r][c]
                    if ch == "?":
                        continue
                    tot += 1
                    m += (ch == exp[gy][gx])
            if tot >= 40 and m > best[0]:
                best = (m, (dc, dr, tot, m / tot if tot else 0))
    if best[1] is None:
        return None
    dc, dr, tot, ratio = best[1]
    return dict(dc=dc, dr=dr, tot=tot, ratio=ratio, score=best[0])


def report(a, pz, label):
    exp = P.expected_walls(pz)
    w, h = pz["w"], pz["h"]
    o = find_offset(a, exp, w, h)
    if o is None:
        print(f"  [{label}] 匹配失败")
        return None
    print(f"  [{label}] 视口偏移 dc={o['dc']} dr={o['dr']}  "
          f"匹配 {o['ratio']*100:.1f}%  (有效格 {o['tot']})")
    return o


def ensure_select():
    for _ in range(8):
        im = P.grab_np()
        st = state2.detect(Image.fromarray(im.astype("uint8")))
        if st == "select" and P.cursor_cell() is not None:
            return True
        for _ in range(2):
            ds.press("x", wait=1.0)
        time.sleep(0.6)
    return False


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 31
    pz = P._SEQ[n - 1]
    w, h = pz["w"], pz["h"]
    print(f"=== 标定 Q{n}  size={w}x{h}  bulbs={len(pz['bulbs'])} "
          f"walls={sum(1 for v in pz['given'] if v != 45)} ===", flush=True)

    if not ensure_select():
        print("!! 回不到选关页"); return 1
    if not P.goto_level(n):
        print("!! goto_level 失败"); return 1
    time.sleep(1.6)
    if not P.in_play_page():
        for _ in range(6):
            ds.press("x", wait=1.0)
            if P.in_play_page():
                break
        time.sleep(1.0)
    if not P.in_play_page():
        print("!! 未进关"); return 1

    a = shot("enter")
    st = state2.detect(Image.fromarray(a.astype("uint8")))
    print(f"进关后 state = {st}", flush=True)

    # ---- 复位到干净盘面（灯全灭）----
    print("\n--- reset_level ---", flush=True)
    ok_r = P.reset_level()
    print("reset =", ok_r, flush=True)
    time.sleep(1.0)
    a = shot("clean")

    print("\n[Phase1] 干净盘面 vs 初始（不滚动）")
    o0 = report(a, pz, "clean@start")

    # ---- Phase2: 逐次 Right，记录视口偏移响应 ----
    print("\n[Phase2] 慢剂量 Right 步进响应（wait=.30 hold=.02）")
    seq = []
    for i in range(1, 13):
        ds.press("Right", wait=0.30, hold=0.02)
        time.sleep(0.25)
        ai = shot(f"r{i}")
        o = report(ai, pz, f"Right×{i}")
        seq.append((i, o["dc"] if o else None, o["dr"] if o else None))
    print("  响应曲线 (按次数, dc, dr):", seq, flush=True)

    # ---- Phase3: 顶死左上 ----
    print("\n[Phase3] Up×h + Left×w 顶死")
    for _ in range(h):
        ds.press("Up", wait=0.30, hold=0.02)
    for _ in range(w):
        ds.press("Left", wait=0.30, hold=0.02)
    time.sleep(0.4)
    a = shot("topleft")
    o_tl = report(a, pz, "topleft")

    # ---- Phase4: 点 3 个灯后再测（验证灯光晕是否污染墙检测）----
    if pz["bulbs"]:
        print("\n[Phase4] 点 3 个灯后重测同一视口（污染检查）")
        before = scr_walls(a)
        cnt = 0
        for (bx, by) in pz["bulbs"]:
            dc = o_tl["dc"] if o_tl else 0
            dr = o_tl["dr"] if o_tl else 0
            sx_, sy_ = bx - dc, by - dr
            if 0 <= sx_ < SCR_COLS and 0 <= sy_ < SCR_ROWS and cnt < 3:
                ds.tap(int(X0 + PP * (sx_ + 0.5)),
                       int(Y0 + PP * (sy_ + 0.5) - 192), after=0.35)
                cnt += 1
        time.sleep(0.8)
        a2 = shot("lit3")
        after = scr_walls(a2)
        print("  墙图差异（行: 干净 -> 点灯后）:")
        ndiff = 0
        for r in range(SCR_ROWS):
            if before[r] != after[r]:
                ndiff += 1
                print(f"    r{r}: {before[r]}")
                print(f"        {after[r]}")
        print(f"  差异行数 = {ndiff}")
        report(a2, pz, "lit3")
        # 灯亮度验证
        yc = P.board_yellow_count()
        print(f"  board_yellow_count = {yc}")

    print("\n=== 标定结束 ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
