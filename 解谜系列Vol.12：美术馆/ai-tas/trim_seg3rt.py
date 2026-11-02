#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""seg3 实时版(limiter ON)最终裁剪：逐段独立处理，规避旧版"共用concat缓存按累计帧数切片"的脆弱性。

老规矩（对齐 seg1/seg2）：
  * save 界面 —— 整段删除
  * 选关界面 —— 每段只留末尾 0.5s
  * 长静止段（相邻帧差<STILL_DIFF 且>1.0s）—— 只留末尾 0.5s
剪辑方式：Python 逐段解码一次、只写保留帧（视频 raw + 音频按 1470 样本/帧、以**源帧号 k** 对齐，
保证音画同步）→ 单段 libopenh264 编码 → 流复制拼接。
用法：
  python3.11 trim_seg3rt.py                # 自动 glob /workspace/seg3rt_*.mp4（排除 probe）
  python3.11 trim_seg3rt.py a.mp4 b.mp4    # 显式指定（冒烟测试用）
"""
import os, sys, subprocess, glob
import cv2
import numpy as np

KEEP_S = 0.5
MIN_SAVE_FRAMES = 1
ORANGE_MIN = 12000
WHITE_MIN = 0.30
STILL_DIFF = 0.5
STILL_MIN_S = 1.0
STILL_KEEP_S = 0.5
# ★Akari(美術館) 专用：点灯 gameplay 本身长时间静止等待（实测 A 段 74.8% 帧为静止），
#   开静止裁剪会把正常 gameplay 砍掉一半（A 段实测 1190s→543s）。
#   交付口径只剪「save 界面整段删除 + 选关界面留末尾 0.5s」，故默认关闭静止裁剪。
STILL_ENABLE = False
SR = 44100

DEF_SEGS = [
    "/workspace/seg3rt_A_q1_30.mp4",
    "/workspace/seg3rt2_B_q31_50.mp4",
    "/workspace/seg3rt2_C_q51_70.mp4",
    "/workspace/seg3rt2_D_q71_90.mp4",
    "/workspace/seg3rt2_E_q91_100.mp4",
    "/workspace/seg3rt2_F_q101_110.mp4",
]


def is_save(a):
    R = a[240:384, :, 0].astype(int); G = a[240:384, :, 1].astype(int); B = a[240:384, :, 2].astype(int)
    orange = (R > 150) & (R < 235) & (G > 55) & (G < 140) & (B < 95) & (R > B + 90)
    return int(orange.sum()) > ORANGE_MIN


def is_select(a):
    sub = a[25:185, 90:250, :]
    R = sub[:, :, 0].astype(int); G = sub[:, :, 1].astype(int); B = sub[:, :, 2].astype(int)
    white = (R > 195) & (G > 195) & (B > 195)
    return float(white.mean()) > WHITE_MIN


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
        return d["states"], d["saves"], float(d["fps"]), d["still"]
    cap = cv2.VideoCapture(in_mp4)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    states, saves, still = [], [], []
    prev = None
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        a = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
        sv = is_save(a)
        saves.append(sv)
        states.append("save" if sv else ("select" if is_select(a) else "other"))
        cur = cv2.resize(fr, (64, 96)).astype(np.int16)
        still.append(False if prev is None else (float(np.abs(cur - prev).mean()) < STILL_DIFF))
        prev = cur
    cap.release()
    states = np.array(states); saves = np.array(saves, dtype=bool); still = np.array(still, dtype=bool)
    np.savez(cache, states=states, saves=saves, fps=fps, still=still)
    return states, saves, fps, still


def keep_mask(states, saves, still, fps):
    n = len(states)
    sel_runs = runs_of(states == "select")
    save_runs = [r for r in runs_of(saves) if r[1] - r[0] + 1 >= MIN_SAVE_FRAMES]
    km = np.ones(n, dtype=bool)
    for s, e in save_runs:
        km[s:e + 1] = False
    for s, e in sel_runs:
        w = int(round(KEEP_S * fps))
        if e - s + 1 > w:
            km[s:e - w + 1] = False
    if not STILL_ENABLE:
        return km
    valid = np.nonzero(km)[0]
    sv = still[valid]
    out, i, m = [], 0, len(valid)
    while i < m:
        if sv[i]:
            j = i
            while j < m and sv[j]:
                j += 1
            if (j - i) / fps > STILL_MIN_S:
                w = int(round(STILL_KEEP_S * fps))
                out.extend(valid[j - w:j].tolist())
            else:
                out.extend(valid[i:j].tolist())
            i = j
        else:
            out.append(valid[i]); i += 1
    res = np.zeros(n, dtype=bool)
    res[out] = True
    return res


def trim_one(src, dst):
    cache = src + ".states_rt.npz"
    states, saves, fps, still = load(src, cache)
    n = len(states)
    km = keep_mask(states, saves, still, fps)
    kept = int(km.sum())
    spf = SR / fps
    vt = dst + ".vraw.tmp"; at = dst + ".araw.tmp"
    # 1) 整段音频解码一次 → PCM
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src, "-vn",
                    "-f", "s16le", "-ar", str(SR), "-ac", "2", at], check=True)
    audio = np.fromfile(at, dtype=np.int16)
    nsamp = len(audio) // 2
    # 2) 视频逐帧解码一次，只写保留帧
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
    # 3) 音频按源帧号 k 对齐切片（音画严格同步）
    with open(at, "wb") as fa:
        for k in range(n):
            if km[k]:
                a0 = int(round(k * spf)); a1 = int(round((k + 1) * spf))
                a0 = max(0, min(a0, nsamp)); a1 = max(a0, min(a1, nsamp))
                fa.write(audio[2 * a0:2 * a1].tobytes())
    # 4) 单段编码
    r = subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "256x384", "-r", "30", "-i", vt,
        "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", at,
        "-c:v", "libopenh264", "-b:v", "3000k", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", dst,
    ])
    os.remove(vt); os.remove(at)
    print(f"{'OK' if r.returncode==0 else 'FAIL'} {os.path.basename(src)} src_frames={n} kept={kept} "
          f"({kept/fps:.1f}s) rc={r.returncode}")
    return kept, fps, r.returncode


def main():
    if len(sys.argv) > 1:
        segs = sys.argv[1:]
    else:
        segs = [s for s in DEF_SEGS if os.path.exists(s)]
        missing = [s for s in DEF_SEGS if not os.path.exists(s)]
        if missing:
            print("!! 缺少分段:", missing); sys.exit(2)
    trimmed, total, fps0 = [], 0, 30.0
    for s in segs:
        dst = s[:-4] + "_t.mp4"
        kept, fps, rc = trim_one(s, dst)
        if rc != 0:
            print("!! 编码失败，终止"); sys.exit(rc)
        trimmed.append(dst); total += kept; fps0 = fps
    print(f"总保留帧={total} ({total/fps0:.2f}s / {total/fps0/60:.2f}min)")
    lst = "/tmp/seg3rt_concat.txt"
    with open(lst, "w") as f:
        for p in trimmed:
            f.write(f"file '{p}'\n")
    out = "/workspace/seg3rt_trimmed.mp4"
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                        "-i", lst, "-c", "copy", "-movflags", "+faststart", out])
    print("拼接:", "OK" if r.returncode == 0 else f"FAIL rc={r.returncode}", "->", out)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
