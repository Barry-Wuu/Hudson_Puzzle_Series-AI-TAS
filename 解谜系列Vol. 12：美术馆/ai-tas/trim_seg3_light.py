#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""seg3 裁剪 v2（2026-10-31）：去除每关「进关 → 第一次点灯」之间的片段。

用户口径：每关开始之后就立即开始点灯。旧片里每关开头有莫名其妙的重开和
光标移动（driver 的进关复位 / リトライ / D-pad 归零走位），这些都要去掉。

判据（B 段实测双峰极其干净，低峰 0~268 / 高峰 3195~5050）：
  * save 界面（is_save 命中，含 START/リトライ 橙色菜单）—— 整段删除
  * 选关界面 —— 每段只留末尾 0.5s
  * play 段按「段内盘面黄像素峰值 ymax」二分：
      - ymax < YMAX_MIN  → 进关复位/重开、通关黑屏、过场 → 整段删除
      - ymax >= YMAX_MIN → 真实关卡 → 保留，但从「首次点灯帧 - PAD」开始
        （首次点灯 = 段内第一帧 yellow >= FIRST_LIGHT_MIN）

用法：
  python3.11 trim_seg3_light.py a.mp4 b.mp4      # 显式指定
输出：<原名>_v2.mp4
"""
import os, sys, subprocess
import cv2
import numpy as np

KEEP_S = 0.5              # 选关界面保留末尾秒数
YMAX_MIN = 1000           # 真实关卡 / 重开过场 的 yellow 峰值分界
FIRST_LIGHT_MIN = 80      # 判定「已点灯」的黄像素数（单灯实测 ≈224）
PAD = 3                   # 首次点灯前保留的帧数（0.1s，避免硬切）
MIN_PLAY_FRAMES = 3       # 短于 3 帧的 play 段 = 拼接处过渡杂帧，删除
SR = 44100


def is_save(a):
    """下屏橙色界面（含 START/リトライ 菜单、通关存档提示）。"""
    R = a[240:384, :, 0].astype(int); G = a[240:384, :, 1].astype(int); B = a[240:384, :, 2].astype(int)
    orange = (R > 150) & (R < 235) & (G > 55) & (G < 140) & (B < 95) & (R > B + 90)
    return int(orange.sum()) > 12000


def is_select(a):
    """选关网格：上屏大片白格。"""
    sub = a[25:185, 90:250, :]
    R = sub[:, :, 0].astype(int); G = sub[:, :, 1].astype(int); B = sub[:, :, 2].astype(int)
    white = (R > 195) & (G > 195) & (B > 195)
    return float(white.mean()) > 0.30


def yellow_count(a):
    """盘面区黄像素数（同 play_akari_seg3.board_yellow_count）。"""
    sub = a[208:384, 8:196]
    R = sub[:, :, 0].astype(int); G = sub[:, :, 1].astype(int); B = sub[:, :, 2].astype(int)
    return int(((R > 190) & (G > 225) & (B < 120)).sum())


def runs_of(mask):
    out, k, n = [], 0, len(mask)
    while k < n:
        if mask[k]:
            s = k
            while k < n and mask[k]:
                k += 1
            out.append((s, k - 1))
        else:
            k += 1
    return out


def load(in_mp4, cache):
    if os.path.exists(cache):
        d = np.load(cache)
        return d["states"], d["saves"], d["ys"], float(d["fps"])
    cap = cv2.VideoCapture(in_mp4)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    states, saves, ys = [], [], []
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        a = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
        sv = is_save(a)
        saves.append(sv)
        states.append("save" if sv else ("select" if is_select(a) else "play"))
        ys.append(yellow_count(a))
    cap.release()
    states = np.array(states); saves = np.array(saves, dtype=bool); ys = np.array(ys)
    np.savez(cache, states=states, saves=saves, ys=ys, fps=fps)
    return states, saves, ys, fps


def keep_mask(states, saves, ys, fps):
    n = len(states)
    km = np.ones(n, dtype=bool)
    # 1) save / リトライ 橙色菜单：整段删除
    for s, e in runs_of(saves):
        km[s:e + 1] = False
    # 2) 选关：只留末尾 0.5s
    w = int(round(KEEP_S * fps))
    for s, e in runs_of(states == "select"):
        if e - s + 1 > w:
            km[s:e - w + 1] = False
    # 3) play 段：按 yellow 峰值二分
    for s, e in runs_of(states == "play"):
        ymax = int(ys[s:e + 1].max())
        if e - s + 1 < MIN_PLAY_FRAMES and ymax < YMAX_MIN:
            km[s:e + 1] = False          # 拼接处过渡杂帧
            continue
        if ymax < YMAX_MIN:
            km[s:e + 1] = False          # 重开/复位/黑屏/过场
            continue
        first = None
        for k in range(s, e + 1):
            if ys[k] >= FIRST_LIGHT_MIN:
                first = k
                break
        if first is not None:
            cut = max(s, first - PAD)
            if cut > s:
                km[s:cut] = False        # 进关后到第一次点灯之间
    return km


def trim_one(src, dst):
    cache = src + ".v2states.npz"
    states, saves, ys, fps = load(src, cache)
    n = len(states)
    km = keep_mask(states, saves, ys, fps)
    kept = int(km.sum())
    spf = SR / fps
    vt = dst + ".vraw.tmp"; at = dst + ".araw.tmp"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-vn",
                    "-f", "s16le", "-ar", str(SR), "-ac", "2", at], check=True)
    audio = np.fromfile(at, dtype=np.int16)
    nsamp = len(audio) // 2
    cap = cv2.VideoCapture(src)
    with open(vt, "wb") as fv:
        idx = 0
        while idx < n:
            ok, fr = cap.read()
            if not ok:
                break
            if km[idx]:
                fv.write(fr.tobytes())
            idx += 1
    cap.release()
    with open(at, "wb") as fa:
        for k in range(n):
            if km[k]:
                a0 = int(round(k * spf)); a1 = int(round((k + 1) * spf))
                a0 = max(0, min(a0, nsamp)); a1 = max(a0, min(a1, nsamp))
                fa.write(audio[2 * a0:2 * a1].tobytes())
    r = subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "256x384", "-r", "30", "-i", vt,
        "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", at,
        "-c:v", "libopenh264", "-b:v", "3000k", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", dst,
    ])
    os.remove(vt); os.remove(at)
    print(f"{'OK' if r.returncode == 0 else 'FAIL'} {os.path.basename(src)} src={n}帧({n/fps:.1f}s) "
          f"kept={kept}({kept/fps:.1f}s) rc={r.returncode}", flush=True)
    return r.returncode


def main():
    segs = sys.argv[1:]
    if not segs:
        print("用法: python3.11 trim_seg3_light.py <mp4> [mp4...]")
        return 2
    rc_all = 0
    for s in segs:
        rc_all |= trim_one(s, s[:-4] + "_v2.mp4")
    return rc_all


if __name__ == "__main__":
    sys.exit(main())
