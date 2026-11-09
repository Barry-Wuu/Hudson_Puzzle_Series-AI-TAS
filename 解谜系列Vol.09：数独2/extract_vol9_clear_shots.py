#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 410 支通关录播里，为每一关抽一张「正解」画面，按难度分目录存进 validation/。

识别方法（沿用 Vol.03 数独1 的口径）：游戏 UI 五颜六色，颜色统计 / OCR / 模板匹配都不可靠，
唯一稳定信号是「正解」二字的**黄色填充**（低蓝值的纯黄，区别于奶油色面板与城市窗灯）。
正解帧的黄填充量（约 4000）远高于对局背景（约 500），所以每关在片尾窗口内多点采样、
取黄填充量最大的那一帧。

录制与剪辑保证了「正解」必在片尾 6 秒内（剪法就是「星星显示完 + 6s」），
因此只在 [d-7, d-0.1] 采样，不必全片扫描。

文件名沿用其它卷约定：lNNN_clear.png（NNN 为该难度内编号 001..N）。
"""
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
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
# 「正解」二字在下屏中部：整幅 256x384 的归一化坐标
BOX = (0.20, 0.55, 0.80, 0.86)
COARSE_STEP = 1.0   # 粗采样步长（秒）
FINE_STEP = 0.25    # 细采样步长（秒）


def dur(v):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'default=nw=1:nk=1', v], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def grab(v, t, dst):
    """输入后定位，帧精确（避免关键帧吸附抽到相邻画面）。"""
    subprocess.run(['ffmpeg', '-y', '-i', v, '-ss', '%.2f' % t, '-frames:v', '1',
                    '-q:v', '2', dst, '-loglevel', 'error'], check=True)


def yellow_fill(p, box=BOX):
    im = Image.open(p).convert('RGB')
    W, H = im.size
    px = im.load()
    x0, x1 = int(W * box[0]), int(W * box[2])
    y0, y1 = int(H * box[1]), int(H * box[3])
    c = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = px[x, y]
            if r > 195 and g > 145 and b < 95:
                c += 1
    return c


def best_in(v, t0, t1, step, tmp_prefix):
    best, bestt = -1, t0
    t = t0
    while t <= t1:
        tmp = '%s_%d.png' % (tmp_prefix, int(t * 100))
        try:
            grab(v, t, tmp)
            s = yellow_fill(tmp)
            if s > best:
                best, bestt = s, t
        except Exception:
            pass
        t += step
    return best, bestt


def process(arg):
    v, diff, num = arg
    d = dur(v)
    if d <= 1:
        return (v, 0, -1, 'duration?')
    t0 = max(1.0, d - 7.0)
    prefix = '/tmp/v9y_%s_%03d' % (DIFF_MAP[diff], num)
    s1, t1 = best_in(v, t0, max(t0, d - 0.15), COARSE_STEP, prefix)
    lo = max(t0, t1 - COARSE_STEP)
    hi = min(d - 0.10, t1 + COARSE_STEP)
    s2, t2 = best_in(v, lo, hi, FINE_STEP, prefix)
    s, t = (s2, t2) if s2 >= s1 else (s1, t1)
    dst_dir = os.path.join(OUT, DIFF_MAP[diff])
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, 'l%03d_clear.png' % num)
    grab(v, t, dst)
    for f in os.listdir('/tmp'):
        if f.startswith(os.path.basename(prefix)):
            try:
                os.remove('/tmp/' + f)
            except OSError:
                pass
    return (v, s, t, dst)


def main():
    jobs = []
    for f in sorted(os.listdir(SRC)):
        m = re.match(r'^Vol\.9_数独2_(.+?)_(\d{3})_通关实况_256x384\.mp4$', f)
        if m and m.group(1) in DIFF_MAP:
            jobs.append((os.path.join(SRC, f), m.group(1), int(m.group(2))))
    print('待抽帧 %d 支' % len(jobs))
    ok, weak = 0, []
    with ThreadPoolExecutor(12) as ex:
        for i, (v, s, t, dst) in enumerate(ex.map(process, jobs), 1):
            if s >= 1500:
                ok += 1
            else:
                weak.append((os.path.basename(v), s, t))
            if i % 50 == 0:
                print('  %d/%d ...' % (i, len(jobs)), flush=True)
    print('完成：%d 支，黄填充达标 %d，偏弱 %d' % (len(jobs), ok, len(weak)))
    for w in weak[:15]:
        print('   偏弱：%s  yellow=%d  t=%.2f' % w)


if __name__ == '__main__':
    main()
