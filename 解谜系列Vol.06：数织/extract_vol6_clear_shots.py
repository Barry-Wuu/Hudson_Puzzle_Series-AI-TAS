#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 300 支通关录播里，为每一关抽一张「黑格刚涂满、尚未变色」的画面，按尺寸分目录存进 validation/。

识别方法（针对 ILLUST LOGIC / 数织，纯像素，无 OCR）：

  数织的实机节奏是「逐格涂黑 → 最后一格落笔 → 立刻播放浸染/上色动画 → 正解」。用户要的
  validation 图就是**刚涂满、还没变色**那一帧。全屏亮度、近黑占比之类的粗指标都不成立：
  片头整屏暗红、片尾整屏淡出、上色后还有大片深色图案。本脚本改用「对着答案盘逐格解码」：

    1. 盘面几何按尺寸硬编码（由红色分组线与格线峰值实测，见 GEO），每格取格心 3×3 邻域；
    2. 每格判「涂黑」= max(R,G,B)<115 且 R>G+8 —— 游戏把黑格画成暗棕红 (67,22,30)，
       空格是米白 (252,244,220)，两者判据毫无重叠；
    3. 逐帧与 puzzles.json 的答案盘比对：ag = 逐格一致率，miss = 该涂没涂的格数；
    4. **取最后一个 ag==1.0 连续段的第一帧** —— 那一刻正好是最后一格落笔的瞬间：
       黑格已全涂满，浸染动画还一格都没动到。

  为什么取「段首」而不是「段尾」：浸染是先动空格底色、后动黑格本体。空格底色从
  米白 (254,244,220) 一路褪成 (230,237,226) → (203,229,236) → 蓝，这一段 ag 仍是 1.0
  （黑格还没变），要等黑格本体变色 ag 才掉。取段尾会拿到已经褪色甚至泛蓝的画面，
  段首才是「还没变颜色」。

  时间精度：先 10 fps 粗扫定位，再在 ±0.5 s 窗口内 30 fps 精扫取段首，避免落在两次采样
  之间（涂满与浸染有时只隔 1~2 帧 @30 fps）。

落盘压缩：沿用 Vol.9 数独2 的口径 —— 先砍回 RGB565（抹掉 H.264 色度子采样噪声），
再中位切压成 256 色索引 PNG（optimize + compress_level=9），与全仓 P 模式统一。

文件名沿用其它卷约定：lNNN_clear.png（NNN 为该尺寸内编号，从 001 起）。
"""
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REC = os.path.join(HERE, 'recordings')
OUT = os.path.join(HERE, 'validation')
PJ = os.path.join(OUT, 'puzzles.json')

W, H = 256, 384

# 盘面几何：(格边长, 左上角 x, 左上角 y)。实测来源见 README「盘面几何」。
#   10×10：格线 x=87,103,…,247 / y=200,216,…,360，红粗线 x=167（=87+5·16）
#   15×15：红粗线 x=142,192（间距 50=5·10）→ 边长 10、左上 x=92；y=250,300 → 左上 y=200
#   20×20：红粗线 x=88(左边框),128,168,208、y=240,280,320 → 边长 8、左上 (88,200)
#   25×25：红粗线 x=110,145,180,215（间距 35=5·7）→ 边长 7、左上 (75,193)
GEO = {
    10: (16.0, 87.0, 200.0),
    15: (10.0, 92.0, 200.0),
    20: (8.0, 88.0, 200.0),
    25: (7.0, 75.0, 193.0),
}
SIZE_DIR = {10: 'mode1_10x10', 15: 'mode2_15x15', 20: 'mode3_20x20', 25: 'mode4_25x25'}
# puzzles.json 里各尺寸的起始下标（10×10 50 题 / 15×15 100 / 20×20 100 / 25×25 50）
SIZE_OFF = {10: 0, 15: 50, 20: 150, 25: 250}

COARSE_FPS = 10
FINE_FPS = 30
FINE_SPAN = 1.0            # 精扫窗口长度（秒）
AGREE_OK = 0.999           # 逐格全对


# ---------------------------------------------------------------- 解码

def decode(path, fps, ss=None, t=None):
    """解成 (n,H,W,3) int16。ss/t 给定时只解这一段（输入侧 seek，快）。"""
    cmd = ['ffmpeg', '-v', 'error']
    if ss is not None:
        cmd += ['-ss', '%.3f' % ss]
    cmd += ['-i', path]
    if t is not None:
        cmd += ['-t', '%.3f' % t]
    cmd += ['-vf', 'fps=%d' % fps, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    r = subprocess.run(cmd, capture_output=True)
    buf = r.stdout
    n = len(buf) // (W * H * 3)
    if n == 0:
        return np.zeros((0, H, W, 3), np.int16)
    return np.frombuffer(buf[:n * W * H * 3], np.uint8).reshape(n, H, W, 3).astype(np.int16)


# ---------------------------------------------------------------- 盘面解码

def cell_xy(n, s, x0, y0):
    cs = x0 + (np.arange(n) + 0.5) * s
    rs = y0 + (np.arange(n) + 0.5) * s
    X = np.clip(np.rint(np.tile(cs, (n, 1))).astype(int), 0, W - 1)
    Y = np.clip(np.rint(np.tile(rs[:, None], (1, n))).astype(int), 0, H - 1)
    return X, Y


def read_board(fr, n, s, x0, y0, grid):
    """逐帧解码盘面，返回 (ag, miss, extra, med, paper)。

    ag    逐格一致率；miss 该涂没涂的格数；extra 多涂的格数；
    med   空格（非黑格）的中位色；
    paper med 是否仍属米白系（R−B ≥ 0 且够亮），用来兜住「已浸染」的帧。
    """
    X, Y = cell_xy(n, s, x0, y0)
    p = fr[:, Y, X]                              # (F,n,n,3)
    ink = np.zeros(p.shape[:3], bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            q = fr[:, np.clip(Y + dy, 0, H - 1), np.clip(X + dx, 0, W - 1)]
            ink |= (q.max(axis=-1) < 115) & (q[..., 0] > q[..., 1] + 8)

    ag = (ink == grid[None, :, :]).mean(axis=(1, 2))
    miss = (grid[None, :, :] & ~ink).sum(axis=(1, 2))
    extra = (~grid[None, :, :] & ink).sum(axis=(1, 2))
    med = np.full((len(fr), 3), np.nan)
    for i in range(len(fr)):
        m = ~ink[i]
        if m.sum():
            med[i] = np.median(p[i][m], axis=0)
    paper = (med[:, 0] >= 200) & ((med[:, 0] - med[:, 2]) >= 0)
    return ag, miss, extra, med, paper


def runs_of(mask, gap=3):
    """把布尔序列切成连续段（允许 ≤gap-1 帧抖动），返回 [(start, end)]。"""
    idx = np.where(mask)[0]
    if len(idx) == 0:
        return []
    out = []
    s = prev = int(idx[0])
    for x in idx[1:]:
        x = int(x)
        if x - prev <= gap:
            prev = x
        else:
            out.append((s, prev))
            s = prev = x
    out.append((s, prev))
    return out


def pick_index(ag, paper, gap=3):
    """在「整盘全对」的连续段里挑一帧：从后往前找第一个含「纸色未浸染」帧的段，
    取该段内第一帧 paper 成立的帧（= 最后一格落笔、浸染还没动到空格的瞬间）。

    为什么必须按 paper 过滤整段：上色完成后图案里的深色格（棕发、黑衣）依旧算「涂黑」，
    对某些题而言整盘黑格恰好全落在深色区，ag 仍会等于 1.0；只按 ag 取末段会拿到
    已经完全上色、底色发绿的画面。
    """
    for a, b in reversed(runs_of(ag >= AGREE_OK, gap)):
        cand = [i for i in range(a, b + 1) if paper[i]]
        if cand:
            return cand[0]
    return None


# ---------------------------------------------------------------- 落盘

def save_frame(a, dst):
    """RGB565 → 256 色中位切索引 PNG（与 Vol.9 数独2 的落盘口径一致）。"""
    q = a.copy()
    q[:, :, 0] = (a[:, :, 0] >> 3) << 3
    q[:, :, 1] = (a[:, :, 1] >> 2) << 2
    q[:, :, 2] = (a[:, :, 2] >> 3) << 3
    im = Image.fromarray(q.astype(np.uint8))
    im.quantize(colors=256, method=Image.MEDIANCUT).save(
        dst, 'PNG', optimize=True, compress_level=9)


# ---------------------------------------------------------------- 单支录播

PUZZLE_GRIDS = None


def _init():
    global PUZZLE_GRIDS
    with open(PJ, encoding='utf-8') as f:
        PUZZLE_GRIDS = [e['grid'] for e in json.load(f)]


def process(job):
    path, size, num = job
    n = size
    s, x0, y0 = GEO[n]
    idx = SIZE_OFF[n] + num - 1
    grid = np.array(PUZZLE_GRIDS[idx], bool)
    tag = dict(path=os.path.basename(path), size=n, num=num, idx=idx)

    fr = decode(path, COARSE_FPS)
    if len(fr) == 0:
        return dict(tag, ok=False, why='解码失败')
    ag, miss, extra, med, paper = read_board(fr, n, s, x0, y0, grid)
    kc = pick_index(ag, paper)
    if kc is None:
        k = int(np.argmax(ag))
        return dict(tag, ok=False,
                    why='全片无「整盘全对且纸色未浸染」的帧（最高一致率 %.3f @%.1fs，缺 %d 格）'
                        % (ag[k], k / float(COARSE_FPS), int(miss[k])))
    t0 = kc / float(COARSE_FPS)                   # 粗扫定位（10 fps 精度）

    # 30 fps 精扫 ±FINE_SPAN/2，重新精确取帧
    ss = max(0.0, t0 - FINE_SPAN / 2)
    fine = decode(path, FINE_FPS, ss=ss, t=FINE_SPAN)
    best, mode = None, 'coarse'
    if len(fine):
        fag, fmiss, fextra, fmed, fpaper = read_board(fine, n, s, x0, y0, grid)
        k = pick_index(fag, fpaper)
        if k is not None:
            best = dict(frame=fine[k], t=ss + k / float(FINE_FPS), ag=float(fag[k]),
                        miss=int(fmiss[k]), extra=int(fextra[k]),
                        paper=[int(v) for v in fmed[k]])
            mode = 'exact'
    if best is None:                              # 精扫窗口里没找到 → 用粗扫结果
        best = dict(frame=fr[kc], t=t0, ag=float(ag[kc]), miss=int(miss[kc]),
                    extra=int(extra[kc]), paper=[int(v) for v in med[kc]])

    dst_dir = os.path.join(OUT, SIZE_DIR[n])
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, 'l%03d_clear.png' % num)
    save_frame(best['frame'], dst)
    return dict(tag, ok=True, t=round(best['t'], 3), agree=round(best['ag'], 4),
                missing=best['miss'], extra=best['extra'], paper=best['paper'],
                mode=mode, dst=os.path.relpath(dst, HERE))


# ---------------------------------------------------------------- 主流程

def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    jobs = []
    for bgm in sorted(os.listdir(REC)):
        d = os.path.join(REC, bgm)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            m = re.match(r'^v6_(\d+)_(\d{3})\.mp4$', f)
            if not m:
                continue
            size, num = int(m.group(1)), int(m.group(2))
            if size not in GEO:
                continue
            if only and only not in ('%d' % size, SIZE_DIR[size]):
                continue
            jobs.append((os.path.join(d, f), size, num))
    print('待处理 %d 支录播' % len(jobs))

    results = []
    nproc = min(8, os.cpu_count() or 1)
    with ProcessPoolExecutor(max_workers=nproc, initializer=_init) as ex:
        for i, r in enumerate(ex.map(process, jobs, chunksize=1), 1):
            results.append(r)
            if r['ok']:
                flag = '' if r['mode'] == 'exact' else '  ← %s' % r['mode']
                print('[%3d/%3d] %-24s %s l%03d  t=%6.2fs  agree=%.3f 缺%d 纸色%s%s'
                      % (i, len(jobs), r['path'], SIZE_DIR[r['size']], r['num'],
                         r['t'], r['agree'], r['missing'], tuple(r['paper']), flag))
            else:
                print('[%3d/%3d] %-24s 失败：%s' % (i, len(jobs), r['path'], r['why']))

    ok = [r for r in results if r['ok']]
    bad = [r for r in results if not r['ok']]
    with open(os.path.join(HERE, 'extract_clear_report.json'), 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print('\n成功 %d / %d，失败 %d' % (len(ok), len(results), len(bad)))
    for r in bad:
        print('  失败：%s  %s' % (r['path'], r['why']))
    per = {}
    for r in ok:
        per[SIZE_DIR[r['size']]] = per.get(SIZE_DIR[r['size']], 0) + 1
    for k in sorted(per):
        print('  %s: %d 张' % (k, per[k]))


if __name__ == '__main__':
    main()
