#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""滚动响应深度标定：过吞键期后逐次 Right/Down，实测视口规则。

用法: python3.11 exp_cal2.py <关卡号>
"""
import sys
import time

import numpy as np
from PIL import Image

import ds
import play_akari_seg3 as P
import state2

SHOT = "/tmp/cal2"
X0, Y0, PP = 16, 208, 16
SCR_COLS, SCR_ROWS = 15, 11


def shot(tag):
    im = P.grab_np()
    Image.fromarray(im.astype("uint8")).save(f"{SHOT}_{tag}.png")
    return im


def scr_walls(a, ncols=SCR_COLS, nrows=SCR_ROWS):
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
    scr = scr_walls(a)
    best = (-1, None)
    for dr in range(-1, h):
        for dc in range(-1, w):
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
                best = (m, (dc, dr, tot))
    if best[1] is None:
        return None
    dc, dr, tot = best[1]
    return dict(dc=dc, dr=dr, score=best[0], tot=tot, ratio=best[0] / tot)


def report(a, pz, label):
    exp = P.expected_walls(pz)
    o = find_offset(a, exp, pz["w"], pz["h"])
    if o is None:
        print(f"  [{label}] 匹配失败")
        return None
    print(f"  [{label}] dc={o['dc']} dr={o['dr']} match={o['ratio']*100:.1f}%", flush=True)
    return o


def ensure_select():
    for _ in range(10):
        im = P.grab_np()
        img = Image.fromarray(im.astype("uint8"))
        st = state2.detect(img)
        if st == "select" and P.cursor_cell() is not None:
            return True
        if st == "play" or P.in_play_page(im):
            P.escape_to_select()
            time.sleep(1.4)
            continue
        ds.press("x", wait=1.0)
        time.sleep(0.6)
    return False


def cal_scroll(n, pz, axes="rc"):
    w, h = pz["w"], pz["h"]
    print(f"\n===== Q{n} ({w}x{h}) =====", flush=True)
    if not ensure_select():
        print("!! 无选关页"); return
    if not P.goto_level(n):
        print("!! goto 失败"); return
    time.sleep(1.6)
    if not P.in_play_page():
        for _ in range(6):
            ds.press("x", wait=1.0)
            if P.in_play_page():
                break
        time.sleep(1.0)
    if not P.in_play_page():
        print("!! 未进关"); return
    P.reset_level()
    time.sleep(4.0)                    # 过吞键期
    a = shot("base")
    o = report(a, pz, "base")
    exp = P.expected_walls(pz)

    if "r" in axes:
        print("-- Right 步进 --", flush=True)
        for i in range(1, 20):
            ds.press("Right", wait=0.30, hold=0.02)
            time.sleep(0.25)
            ai = shot(f"q{n}_R{i}")
            oi = report(ai, pz, f"R{i}")
            if oi and o and oi["dc"] >= w - 13 + 1:   # 到最右
                pass
        # 顶死
        for _ in range(h + 2):
            ds.press("Up", wait=0.30, hold=0.02)
        for _ in range(w + 2):
            ds.press("Left", wait=0.30, hold=0.02)
        time.sleep(0.4)
        report(shot(f"q{n}_home"), pz, "home(顶死)")

    if "d" in axes:
        print("-- Down 步进 --", flush=True)
        for i in range(1, 16):
            ds.press("Down", wait=0.30, hold=0.02)
            time.sleep(0.25)
            ai = shot(f"q{n}_D{i}")
            report(ai, pz, f"D{i}")
        # 底部再测 Left 回程
        print("-- Left 步进 --", flush=True)
        for i in range(1, 4):
            ds.press("Left", wait=0.30, hold=0.02)
            time.sleep(0.25)
            report(shot(f"q{n}_L{i}"), pz, f"L{i}")
    # 退出到选关页
    P.escape_to_select()
    time.sleep(1.5)


if __name__ == "__main__":
    for n in [int(x) for x in sys.argv[1:]] or [31]:
        pz = P._SEQ[n - 1]
        axes = "rd" if pz["h"] > 11 else "r"
        cal_scroll(n, pz, axes=axes)
    print("=== DONE ===", flush=True)
