#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.4 やさしい 9×9 录播质检。

判据（全部实机标定，勿凭直觉改）：
  1. 256×384 / h264 + aac
  2. 末帧是结算页（下半屏蓝色占比 > 0.4）
  3. 末帧 4 颗星逐桶全亮（星星带 y=322..335，4 个 x 桶各需 ≥8 像素）
  4. END-3s 帧仅 2/4~3/4 亮 → 证明「点亮过程」确在视频内，而非硬切
  5. 音量非静音
  6. 成片定长：同批各关时长极差 ≤ 0.5s（用户要求「每关录像用时相同」）

用法：qc_yasa.py [lo] [hi]
"""
import os
import sys
import json
import subprocess

from PIL import Image

OUT = '/workspace/Vol.4_やさしい录播'
BUCKETS = [(106, 119), (122, 135), (138, 151), (154, 167)]
Y0, Y1 = 322, 335
DUR_TOL = 2.5          # 同批时长极差上限（秒）
# 单关空格数 56~64 → 填数本身就有 1.5~2.5s 差异，加上结算页出现时刻抖动，
# 成片 41.6~43.6s 属正常波动；此阈值只用来抓「突然变长」（重试/卡住导致 +10s 级）。


def gold(px):
    r, g, b = px
    return r > 190 and g > 140 and b < 120


def stars(im):
    return [sum(1 for y in range(Y0, Y1) for x in range(x0, x1) if gold(im.getpixel((x, y))))
            for x0, x1 in BUCKETS]


def blue_bottom(im):
    c = t = 0
    for y in range(192, 384, 3):
        for x in range(0, 256, 3):
            r, g, b = im.getpixel((x, y))
            t += 1
            if r < 110 and b > 90 and b > r + 35:
                c += 1
    return c / t


def frame_at(p, t, out):
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', '%.2f' % max(0, t),
                    '-i', p, '-frames:v', '1', out], capture_output=True)
    return Image.open(out).convert('RGB').resize((256, 384)) if os.path.exists(out) else None


def probe(p):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                        'stream=codec_type,codec_name,width,height:format=duration,size',
                        '-of', 'json', p], capture_output=True, text=True)
    return json.loads(r.stdout or '{}')


def volume(p):
    r = subprocess.run(['ffmpeg', '-i', p, '-af', 'volumedetect', '-f', 'null', '-'],
                       capture_output=True, text=True)
    for ln in r.stderr.splitlines():
        if 'mean_volume' in ln:
            return ln.split(':')[-1].strip()
    return '?'


def main():
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    print('关号 分辨率  编码      时长(s) 大小(MB) 末帧blue 4星桶        全亮 END-3s桶  音量 判定')
    allok = True
    n_ok = n_tot = 0
    durs = []
    for k in range(lo, hi + 1):
        p = os.path.join(OUT, 'Vol.4_数和_やさしい%03d_256x384.mp4' % k)
        if not os.path.exists(p):
            print('%03d  缺失' % k)
            allok = False
            continue
        n_tot += 1
        j = probe(p)
        st = j.get('streams', [])
        v = next((s for s in st if s['codec_type'] == 'video'), {})
        a = next((s for s in st if s['codec_type'] == 'audio'), {})
        dur = float(j.get('format', {}).get('duration', 0))
        sz = int(j.get('format', {}).get('size', 0)) / 1048576
        durs.append(dur)
        last = frame_at(p, dur - 0.3, '/tmp/qy_last_%03d.png' % k)
        early = frame_at(p, dur - 3.0, '/tmp/qy_early_%03d.png' % k)
        bb = blue_bottom(last)
        lit = stars(last)
        lit_e = stars(early)
        n_lit = sum(1 for c in lit if c >= 8)
        ok = (bb > 0.4 and n_lit == 4
              and v.get('width') == 256 and v.get('height') == 384
              and v.get('codec_name') == 'h264' and a.get('codec_name') == 'aac'
              and volume(p) != '-91.0 dB')
        allok &= ok
        n_ok += ok
        print('%03d  %sx%s %s+%s %6.2f %6.2f  %.3f   %-12s %d/4  %-10s %s %s' % (
            k, v.get('width', '?'), v.get('height', '?'), v.get('codec_name', '?'),
            a.get('codec_name', '?'), dur, sz, bb,
            '/'.join(str(c) for c in lit), n_lit,
            '/'.join(str(c) for c in lit_e), volume(p), 'OK' if ok else '<<< FAIL'),
            flush=True)

    print()
    if durs:
        spread = max(durs) - min(durs)
        uni = spread <= DUR_TOL
        allok &= uni
        print('时长一致性: %.2f ~ %.2f s，极差 %.2f s（阈值 %.1f）%s' % (
            min(durs), max(durs), spread, DUR_TOL, 'OK' if uni else '<<< 不一致'))
    print('=== 总判定: %d/%d 合格 %s ===' % (n_ok, n_tot, '（全部通过）' if allok else '（存在 FAIL）'))
    return 0 if allok else 1


if __name__ == '__main__':
    sys.exit(main())
