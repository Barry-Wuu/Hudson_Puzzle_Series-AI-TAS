#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seg3 最终裁剪：Python 逐段解码一次，仅写出保留帧（视频 raw + 音频 s16le 按 1470 样本/帧对齐），
单 ffmpeg 编码每段 → 流复制拼接。彻底绕开 ffmpeg select 表达式 / concat 多路扇入的尺寸限制。"""
import os, subprocess, sys
import numpy as np
import cv2

KEEP_S = 0.5
MIN_SAVE_FRAMES = 1
ORANGE_MIN = 12000
WHITE_MIN = 0.30
STILL_DIFF = 0.5
STILL_MIN_S = 1.0
STILL_KEEP_S = 0.5

CACHE = "/workspace/seg3_futsuu_concat.mp4.states_v12.npz"
PARTS = [
    ("/workspace/seg3_A_q1_30.mp4",      "/workspace/seg3_t_A.mp4",      31969),
    ("/workspace/seg3_b_q31_90.mp4",     "/workspace/seg3_t_b.mp4",      37776),
    ("/workspace/seg3_B2a_q51_61.mp4",   "/workspace/seg3_t_B2a.mp4",    22036),
    ("/workspace/seg3_B2b_q62_90.mp4",   "/workspace/seg3_t_B2b.mp4",    59965),
    ("/workspace/seg3_C_q91_110.mp4",    "/workspace/seg3_t_C.mp4",     103698),
]


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
            out.append(valid[i])
            i += 1
    res = np.zeros(n, dtype=bool)
    res[out] = True
    return res


def main():
    d = np.load(CACHE)
    states, saves, still, fps = d["states"], d["saves"], d["still"], float(d["fps"])
    SR = 44100
    spf = SR / fps  # 1470.0
    off = 0
    total_kept = 0
    outlist = []
    for src, dst, num in PARTS:
        sl = slice(off, off + num)
        km = keep_mask(states[sl], saves[sl], still[sl], fps)
        off += num
        kept = int(km.sum())
        total_kept += kept
        n = num

        vt = dst + ".vraw.tmp"
        at = dst + ".araw.tmp"
        # 1) 音频整段解码一次 → PCM
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-i", src, "-vn",
            "-f", "s16le", "-ar", str(SR), "-ac", "2", at,
        ], check=True)
        audio = np.fromfile(at, dtype=np.int16)
        # 2) 视频逐帧解码一次，仅写保留帧
        cap = cv2.VideoCapture(src)
        with open(vt, "wb") as fv:
            idx = 0
            while True:
                ok, fr = cap.read()
                if not ok:
                    break
                if km[idx]:
                    fv.write(fr.tobytes())
                idx += 1
                if idx >= n:
                    break
        cap.release()
        # 3) 音频按帧对齐切片写出
        with open(at, "wb") as fa:
            s_idx = 0
            for k in range(n):
                if km[k]:
                    a0 = int(round(s_idx * spf))
                    a1 = int(round((s_idx + 1) * spf))
                    fa.write(audio[a0:a1].tobytes())
                    s_idx += 1
        # 4) 单 ffmpeg 编码
        r = subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "256x384", "-r", "30", "-i", vt,
            "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", at,
            "-c:v", "libopenh264", "-b:v", "3000k", "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", dst,
        ])
        os.remove(vt); os.remove(at)
        if r.returncode != 0:
            print(f"!! FAIL {dst} rc={r.returncode}"); sys.exit(r.returncode)
        print(f"OK {os.path.basename(dst)} kept={kept} ({kept / fps:.1f}s)")
    print(f"总保留帧={total_kept} ({total_kept / fps:.2f}s / {total_kept / fps / 60:.2f}min)")

    lst = "/tmp/seg3_parts_concat.txt"
    with open(lst, "w") as f:
        for p in outlist if False else [x[1] for x in PARTS]:
            f.write(f"file '{p}'\n")
    out = "/workspace/seg3_futsuu_trimmed.mp4"
    r = subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
        "-c", "copy", "-movflags", "+faststart", out,
    ])
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
