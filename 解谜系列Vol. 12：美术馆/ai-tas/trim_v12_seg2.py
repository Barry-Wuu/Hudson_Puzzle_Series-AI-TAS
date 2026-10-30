#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.12 美術館(Akari) seg2 录像后处理（老规矩 + 静止段压缩）。

老规矩（与 Vol.11 一致）：
  * 「セーブしています…」save 界面 —— **整段删除**
  * 选关界面 —— 每段只留末尾 0.5s
新增（因 limiter ON 实况总时长 488s、其中 72.5% 为静止画面）：
  * **长静止段压缩**：连续无变化的画面（相邻帧差异 < 阈值）超过 1.0s 的，
    只保留末尾 0.5s，其余直接剪掉。
    ★ 静止段本身就是"同一帧重复"，剪掉它不丢任何动画信息，
      动画段逐帧连续（实测段内 0% 卡顿），所以观感是"节奏变紧"而非"跳帧"。

用法: python3 trim_v12_seg2.py <in.mp4> <out.mp4>

★ seg2 说明：选关页特征与 seg1 一致（上半屏白预览板占比 >0.30）；
  seg2 的选关页含关卡网格与关卡预览，仍用同一判据。
"""
import os
import subprocess
import sys

import cv2
import numpy as np

KEEP_S = 0.5             # 选关界面保留时长
MIN_SAVE_FRAMES = 1      # save 段最短帧数（★2026-10-28 由 4 改 1：
                         #   实测有孤立 1 帧的 save 提示闪现（原阈值下漏删 21 帧））
ORANGE_MIN = 12000       # save 橙框像素阈值
WHITE_MIN = 0.30         # 选关页白预览板比例阈值

STILL_DIFF = 0.5         # 相邻帧平均差 < 此值 视为"静止"
STILL_MIN_S = 1.0        # 静止段超过此长度才压缩
STILL_KEEP_S = 0.5       # 静止段保留长度


def is_save(a):
    """a: RGB ndarray。save = 中下区大块橙色对话框。"""
    R = a[240:384, :, 0].astype(int)
    G = a[240:384, :, 1].astype(int)
    B = a[240:384, :, 2].astype(int)
    orange = (R > 150) & (R < 235) & (G > 55) & (G < 140) & (B < 95) & (R > B + 90)
    return int(orange.sum()) > ORANGE_MIN


def is_select(a):
    """select = 上半屏中间白预览板（白格盘面）比例高。"""
    sub = a[25:185, 90:250, :]
    R = sub[:, :, 0].astype(int)
    G = sub[:, :, 1].astype(int)
    B = sub[:, :, 2].astype(int)
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
    """返回 (states, saves, fps, still)

    ★2026-10-28 改**流式**：旧版把每帧缩到 64x96 全存进 npz，
      71424 帧 ⇒ 2.6GB，OOM 被杀（exit 137）。
      现在只保留上一帧的小图，边读边算相邻帧差异，内存 O(1)。
    """
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
        if prev is None:
            still.append(False)
        else:
            still.append(float(np.abs(cur - prev).mean()) < STILL_DIFF)
        prev = cur
    cap.release()
    states = np.array(states)
    saves = np.array(saves, dtype=bool)
    still = np.array(still, dtype=bool)
    np.savez(cache, states=states, saves=saves, fps=fps, still=still)
    return states, saves, fps, still


def main():
    in_mp4, out_mp4 = sys.argv[1], sys.argv[2]
    cache = in_mp4 + ".states_v12.npz"
    states, saves, fps, still = load(in_mp4, cache)
    n = len(states)

    # ---- 步骤1：save 整段删除、select 只留末尾 KEEP_S ----
    sel_runs = runs_of(states == "select")
    save_runs = [r for r in runs_of(saves) if r[1] - r[0] + 1 >= MIN_SAVE_FRAMES]
    keep_mask = np.ones(n, dtype=bool)
    for s, e in save_runs:
        keep_mask[s:e + 1] = False
    for s, e in sel_runs:
        w = int(round(KEEP_S * fps))
        if e - s + 1 > w:
            keep_mask[s:e - w + 1] = False
    valid = np.nonzero(keep_mask)[0]

    sel_t = sum(e - s + 1 for s, e in sel_runs) / fps
    save_t = sum(e - s + 1 for s, e in save_runs) / fps
    print(f"frames={n} fps={fps:.1f} 源时长={n/fps:.2f}s")
    print(f"select 段={len(sel_runs)} 合计{sel_t:.2f}s（每段留末尾{KEEP_S}s）")
    print(f"save   段={len(save_runs)} 合计{save_t:.2f}s（整段删除）")
    print(f"步骤1 后有效帧={len(valid)} ({len(valid)/fps:.2f}s)")

    # ---- 步骤2：长静止段压缩（保留末尾 STILL_KEEP_S）----
    still_valid = still[valid]
    out_idx = []
    still_run_cnt = 0
    i = 0
    m = len(valid)
    while i < m:
        if still_valid[i]:
            j = i
            while j < m and still_valid[j]:
                j += 1
            run_len = j - i
            if run_len / fps > STILL_MIN_S:
                w = int(round(STILL_KEEP_S * fps))
                out_idx.extend(valid[j - w:j].tolist())
                still_run_cnt += 1
            else:
                out_idx.extend(valid[i:j].tolist())
            i = j
        else:
            out_idx.append(valid[i])
            i += 1
    out_idx = np.array(out_idx, dtype=np.int64)
    print(f"步骤2 压缩静止段 {still_run_cnt} 个 → 最终 {len(out_idx)} 帧 "
          f"({len(out_idx)/fps:.2f}s)")

    # ---- 步骤3：帧序列 → 连续区间 → ffmpeg trim/atrim + concat ----
    merged = []
    for idx in out_idx:
        if merged and idx == merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], int(idx))
        else:
            merged.append((int(idx), int(idx)))
    dur = sum(e - a + 1 for a, e in merged) / fps
    print(f"keep 段={len(merged)} 输出≈{dur:.2f}s ({dur/60:.2f} min)")

    parts_v, parts_a, cin = [], [], []
    for i, (a, b) in enumerate(merged):
        s, e = a / fps, (b + 1) / fps
        parts_v.append(f"[0:v]trim=start={s:.6f}:end={e:.6f},setpts=PTS-STARTPTS[v{i}]")
        parts_a.append(f"[0:a]atrim=start={s:.6f}:end={e:.6f},asetpts=PTS-STARTPTS[a{i}]")
        cin.append(f"[v{i}][a{i}]")
    flt = ";\n".join(parts_v + parts_a) + ";\n" + "".join(cin) + \
        f"concat=n={len(merged)}:v=1:a=1[vout][aout]\n"
    fpath = out_mp4 + ".filter.txt"
    with open(fpath, "w") as f:
        f.write(flt)

    r = subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
        "-i", in_mp4, "-filter_complex_script", fpath,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libopenh264", "-b:v", "3000k",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out_mp4,
    ])
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
