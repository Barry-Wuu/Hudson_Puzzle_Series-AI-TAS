#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 410 支通关录播里，为每一关抽一张「正解」画面，按难度分目录存进 validation/。

识别方法（沿用 Vol.03 数独1 的口径，但补了一条关键约束）：游戏 UI 五颜六色，
颜色统计 / OCR / 模板匹配都不可靠，唯一稳定信号是「正解」二字的**黄色填充**
（低蓝值的纯黄，区别于奶油色面板）。

⚠ 与 Vol.03 的差别：数独2 的「正解」弹出后会**整屏变暗**（约 50% 亮度）停留数秒。
只取「黄填充最大帧」会正好落在变暗区间（多帧黄填充完全相同），交付的截图就全是
发灰的暗屏。故判据改成两步：

  ① 黄填充达到本片峰值的 85% 以上 —— 确认「正解」二字已完整弹出；
  ② 在这些帧里取**整屏平均亮度最高**的一帧（并列取最早）—— 即变暗之前的原亮度画面。

实现上不再多次调用 ffmpeg 抽候选帧，而是把片尾窗口一次性按 20 fps 解码成 rawvideo
读进内存逐帧打分，直接落盘最优帧：既少了 N 次进程开销，也保证落盘帧就是被打分的那一帧
（不会因两次 -ss 定位不一致而错位）。

文件名沿用其它卷约定：lNNN_clear.png（NNN 为该难度内编号 001..N）。
"""
import os
import re
import sys
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image

SRC = '/workspace/Vol.9_全关录播_去愣住版'
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'validation')

DIFF_MAP = {
    '練習問題': 'mode1_practice',
    'やさしい': 'mode2_easy',
    'ふつう': 'mode3_medium',
    'むずかしい': 'mode4_hard',
    '超難問': 'mode5_extreme',
}
W, H = 256, 384
# 「正解」二字在下屏中部：整幅 256x384 的归一化坐标
BOX = (0.20, 0.55, 0.80, 0.86)
TAIL = 10.0        # 片尾取样窗口（秒）
FPS = 20           # 窗口内采样帧率（50 ms 一帧，足以落在「正解弹出→变暗」之间）
YELLOW_FRAC = 0.85  # 黄填充需达到本片峰值的比例
YELLOW_MIN = 1500   # 本片峰值下限，低于此视为没抓到「正解」
BRIGHT_TOL = 1.0    # 亮度并列容差（灰度级），并列时取最早


def dur(v):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'default=nw=1:nk=1', v], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def decode_tail(v, t0):
    """把 [t0, 结尾] 按 FPS 解码成 (N,H,W,3) uint8。"""
    cmd = ['ffmpeg', '-v', 'error', '-ss', '%.3f' % t0, '-i', v,
           '-vf', 'fps=%d' % FPS, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    buf = subprocess.run(cmd, capture_output=True).stdout
    n = len(buf) // (W * H * 3)
    return np.frombuffer(buf[:n * W * H * 3], np.uint8).reshape(n, H, W, 3)


def score(frames):
    """返回每帧的 (黄填充像素数, 整屏平均亮度)。"""
    r = frames[:, :, :, 0].astype(np.int32)
    g = frames[:, :, :, 1].astype(np.int32)
    b = frames[:, :, :, 2].astype(np.int32)
    y0, y1 = int(H * BOX[1]), int(H * BOX[3])
    x0, x1 = int(W * BOX[0]), int(W * BOX[2])
    sub = (r > 195) & (g > 145) & (b < 95)
    yellow = sub[:, y0:y1, x0:x1].sum(axis=(1, 2))
    luma = (r * 299 + g * 587 + b * 114) // 1000
    return yellow, luma.mean(axis=(1, 2))


def pick(yellow, luma):
    """先按黄填充峰值 85% 筛出「正解已弹出」的帧，再在这些帧里取最亮的一帧。"""
    ymax = int(yellow.max()) if len(yellow) else 0
    if ymax < YELLOW_MIN:
        return None, ymax, 0.0
    cand = np.where(yellow >= YELLOW_FRAC * ymax)[0]
    lmax = luma[cand].max()
    cand = cand[luma[cand] >= lmax - BRIGHT_TOL]
    k = int(cand[0])
    return k, ymax, float(luma[k])


def save_rgb565(a, dst):
    """落盘前压到 16 位色深（RGB565）。

    NDS 输出本是 15-bit，这些帧却是从 H.264 yuv420p 录播里解出来的，「上万色」绝大多数
    是色度子采样噪声。砍回 5/6/5 位等于把编码噪声抹掉，画面内容不受影响。
    """
    q = a.copy()
    q[:, :, 0] = (a[:, :, 0] >> 3) << 3
    q[:, :, 1] = (a[:, :, 1] >> 2) << 2
    q[:, :, 2] = (a[:, :, 2] >> 3) << 3
    Image.fromarray(q).save(dst, 'PNG', optimize=True, compress_level=9)


# 调色板色数：256 = 进一步压成 8-bit 索引 PNG（默认）；0 = 只做 RGB565，不压调色板。
PALETTE = int(os.environ.get('V9_PALETTE', '256'))


def save_frame(a, dst):
    """RGB565 之后可选再做 256 色调色板压缩。

    量化前的实测口径（410 张全量）：中位切调色板、无抖动，体积 45.6MB → 25.1MB（55%）；
    PSNR 33.1 dB、SSIM 0.989、ΔE76 中位 0.68；黄面板 / 蓝面板 / 盘面白底等平坦区域
    的平均色偏移 ≤1 个色阶（肉眼不可见），差异集中在文字与网格的边缘像素。
    100% / 200% 观看与原件无差别，400% 以上放大才看得出极轻微边缘色带。
    设 V9_PALETTE=0 可退回「仅 RGB565」的版本。
    """
    save_rgb565(a, dst)
    if 0 < PALETTE <= 256:
        im = Image.open(dst).convert('RGB')
        im.quantize(colors=PALETTE, method=Image.MEDIANCUT).save(
            dst, 'PNG', optimize=True, compress_level=9)


def process(arg):
    v, diff, num = arg
    d = dur(v)
    if d <= 1:
        return (v, 0, -1.0, -1, None, None)
    t0 = max(1.0, d - TAIL)
    frames = decode_tail(v, t0)
    if len(frames) == 0:
        return (v, 0, -1.0, -1, None, None)
    yellow, luma = score(frames)
    k, ymax, lk = pick(yellow, luma)
    if k is None:
        k = int(np.argmax(yellow))
    dst_dir = os.path.join(os.environ.get('V9_OUT', OUT), DIFF_MAP[diff])
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, 'l%03d_clear.png' % num)
    save_frame(frames[k], dst)
    t = t0 + k / float(FPS)
    return (v, int(yellow[k]), t, k, dst, ymax)


def main():
    jobs = []
    for f in sorted(os.listdir(SRC)):
        m = re.match(r'^Vol\.9_数独2_(.+?)_(\d{3})_通关实况_256x384\.mp4$', f)
        if m and m.group(1) in DIFF_MAP:
            jobs.append((os.path.join(SRC, f), m.group(1), int(m.group(2))))
    print('待抽帧 %d 支' % len(jobs))
    ok, weak, recs = 0, [], []
    with ThreadPoolExecutor(12) as ex:
        for i, (v, s, t, k, dst, ymax) in enumerate(ex.map(process, jobs), 1):
            if s >= 1500:
                ok += 1
            else:
                weak.append((os.path.basename(v), s, t))
            recs.append(dict(video=os.path.basename(v), yellow=s, ymax=ymax,
                             t=round(t, 2), frame=k, out=os.path.basename(os.path.dirname(dst)) + '/' + os.path.basename(dst)))
            if i % 50 == 0:
                print('  %d/%d ...' % (i, len(jobs)), flush=True)
    print('完成：%d 支，黄填充达标 %d，偏弱 %d' % (len(jobs), ok, len(weak)))
    for w in weak[:15]:
        print('   偏弱：%s  yellow=%d  t=%.2f' % w)
    p = os.path.join(HERE, 'shots_index.json')
    json.dump(recs, open(p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('选取记录:', p)


if __name__ == '__main__':
    main()
