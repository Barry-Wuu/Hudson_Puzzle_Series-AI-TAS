#!/usr/bin/env python3
"""页面状态检测 v3 —— 实测 RGB 签名 + 通用"单元格掩码"(兼容已通关变绿)。"""
import numpy as np
from PIL import Image

def _c(m):
    return int(m.sum())

def cells(im, y0, y1, x0=8, x1=248):
    """网格单元格掩码: teal(未通关) 或 green(已通关)。"""
    a = np.asarray(im.convert("RGB")).astype(int)
    R, G, B = a[y0:y1, x0:x1, 0], a[y0:y1, x0:x1, 1], a[y0:y1, x0:x1, 2]
    teal = (R < 40) & (G > 70) & (G < 170) & (B > 100) & (B < 180)
    green = (R < 140) & (G > 100) & (G > R + 50) & (B < 130)
    return _c(teal | green)

def detect(im):
    a = np.asarray(im.convert("RGB")).astype(int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    # 1. clear: 深蓝クリアタイム横幅 (49,82,123)
    if _c((abs(R[245:320, 30:225]-49) < 15) & (abs(G[245:320, 30:225]-82) < 15)
          & (abs(B[245:320, 30:225]-115) < 22)) > 1800:
        return "clear"
    # 2. tut: 淡蓝灰文字框 或 教程盘框右缘棕色
    r, g, b = R[28:155, 12:244], G[28:155, 12:244], B[28:155, 12:244]
    box = _c((r > 168) & (r < 218) & (g > 193) & (g < 238) & (b > 203) & (b < 248) & (b > r + 12))
    rr, gg, bb = R[230:350, 182:212], G[230:350, 182:212], B[230:350, 182:212]
    brown = _c((rr > 80) & (rr < 175) & (rr > bb + 22) & (gg < rr))
    if box > 6000 or brown > 1500:
        return "tut"
    # 3. menu: スタート/ヘルプ/チュートリアル 按钮 (0,106,156)
    # 4. menu: スタート/ヘルプ/チュートリアル 按钮 (0,106,156)
    r, g, b = R[262:348, 100:245], G[262:348, 100:245], B[262:348, 100:245]
    if _c((abs(r-0) < 30) & (abs(g-106) < 20) & (abs(b-156) < 12)) > 2000:
        return "menu"

    # 4. option: 金色 logo + teal 行(无紫色按钮)
    r2, g2, b2 = R[15:95, 30:225], G[15:95, 30:225], B[15:95, 30:225]
    if _c((r2 > 150) & (g2 > 100) & (b2 < 120) & (r2 > b2 + 60)) > 800:
        r3, g3, b3 = R[195:340, 8:248], G[195:340, 8:248], B[195:340, 8:248]
        if _c((abs(r3-131) < 30) & (abs(g3-115) < 30) & (abs(b3-222) < 30)) > 1200:
            return "title"
        if cells(im, 210, 330) > 1800:
            return "option"
    # 5. diff: 上屏关卡网格
    if cells(im, 85, 155) > 2000:
        return "diff"
    # 6. play: 盘面大量纯白 (246,246,246) 或大量黑墙格 (49,49,49)
    #    （2026-10-23 修：原签名仅查纯白>8000，burst 中途高涂黑盘面白像素
    #     不足会掉到 slot 兜底，导致 ensure_select 死循环。补黑墙格条件。）
    _rw = abs(R[220:355, 25:165] - 246) < 8
    _gw = abs(G[220:355, 25:165] - 246) < 8
    _rb = abs(R[220:355, 25:165] - 49) < 10
    _gb = abs(G[220:355, 25:165] - 49) < 10
    if _c(_rw & _gw) > 2500 or _c(_rb & _gb) > 800:
        return "play"
    # 7. select: 下屏关卡网格
    if cells(im, 268, 302) > 1000:
        return "select"
    return "slot"

if __name__ == "__main__":
    ART = "/root/.codebuddy/artifact/vol11"
    cases = {"boot.png": "title", "diag_t2.png": "menu", "nav2.png": "diff",
             "nav4.png": "diff", "nav5.png": "select", "td_r44.png": "play",
             "diag_sel.png": "tut", "l001_check.png": "clear", "nav1.png": "slot",
             "td_r12.png": "tut", "td_r03.png": "tut", "nav3.png": "diff",
             "quit3.png": "option", "flow4.png": "option", "k2.png": "select",
             "r1.png": "select", "selchk.png": "diff", "wrap_test.png": "select",
             "stuck12.png": "play", "d2.png": "diff"}
    bad = 0
    for f, want in cases.items():
        try: im = Image.open(f"{ART}/{f}")
        except Exception: print("miss", f); continue
        got = detect(im)
        if got != want: bad += 1
        print(("OK " if got == want else "BAD"), f"{f:16s} want={want:7s} got={got}")
    print("bad:", bad)
