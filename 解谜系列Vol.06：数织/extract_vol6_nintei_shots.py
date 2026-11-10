#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抽「認定問題」的 validation 图：4 张各段位「正解」+ 全段位制覇的選段位菜单与收尾演出。

素材在仓库外的 `/workspace/Vol.6_段位认定/`。認定問題是独立题库（不在 quest/*.bin 的 300 题里），
没有答案盘可对，所以不能像各关那样逐格校验；这里按画面的时序特征定位：

  · 「正解」横幅：盘面中部的橙底红边字样。取 y∈[245,330]、x∈[50,210] 的橙色像素占比，
    >0.10 的连续段（≥20 帧）就是横幅在场的时间，取段内正中一帧 —— 此时图案已完全上色、
    横幅盖在盘面上，与其它卷 Vol.N_認定_<段位>_正解.png 的口径一致。
  · 全段位制覇：从 `全段位制覇_通关演出` 里取「選段位」菜单（四个段位齐列）+ 末尾的
    标题演出（黑底 + イラストロジック logo），后者只在四段位全通后才会播。

> 各关的 clear 图是「刚涂满黑格、还没变色」，認定图是「正解」——两者口径不同是有意的：
> 認定图要证明的是段位达成，必须带上正解画面；各关要证明的是盘面填对，黑格态才可逐格校验。

用法：python3 extract_vol6_nintei_shots.py
"""
import os
import subprocess

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'validation')
SRC = '/workspace/Vol.6_段位认定'

W, H = 256, 384
FPS = 30

VIDEOS = {
    'ブロンズ': 'Vol.6_数织_認定問題_ブロンズ_通关实况_256x384.mp4',
    'シルバー': 'Vol.6_数织_認定問題_シルバー_通关实况_256x384.mp4',
    'ゴールド': 'Vol.6_数织_認定問題_ゴールド_通关实况_256x384.mp4',
    'プラチナ': 'Vol.6_数织_認定問題_プラチナ_通关实况_256x384.mp4',
}
ALL_VIDEO = 'Vol.6_数织_全段位制覇_通关演出_256x384.mp4'


def decode(path, fps=FPS):
    cmd = ['ffmpeg', '-v', 'error', '-i', path, '-vf', 'fps=%d' % fps,
           '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    r = subprocess.run(cmd, capture_output=True)
    buf = r.stdout
    n = len(buf) // (W * H * 3)
    return np.frombuffer(buf[:n * W * H * 3], np.uint8).reshape(n, H, W, 3).astype(np.int16)


def banner(a):
    """「正解」横幅：盘面中部的橙底占比（逐帧）。"""
    sub = a[:, 245:330, 50:210]
    R, G, B = sub[..., 0], sub[..., 1], sub[..., 2]
    return ((R > 190) & (G > 110) & (G < 215) & (B < 115)).mean(axis=(1, 2))


def runs_of(mask, gap=3):
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


def save_rgb565(a, dst):
    """RGB565 → 256 色中位切索引 PNG（与各关 clear 图、其它卷同一落盘口径）。"""
    q = a.copy()
    q[:, :, 0] = (a[:, :, 0] >> 3) << 3
    q[:, :, 1] = (a[:, :, 1] >> 2) << 2
    q[:, :, 2] = (a[:, :, 2] >> 3) << 3
    im = Image.fromarray(q.astype(np.uint8))
    im.quantize(colors=256, method=Image.MEDIANCUT).save(
        dst, 'PNG', optimize=True, compress_level=9)


def main():
    os.makedirs(OUT, exist_ok=True)
    written = []
    for rank, fn in VIDEOS.items():
        p = os.path.join(SRC, fn)
        if not os.path.exists(p):
            print('缺素材：', p)
            continue
        a = decode(p)
        rs = [r for r in runs_of(banner(a) > 0.10, gap=10) if r[1] - r[0] >= 20]
        if not rs:
            print('%-6s 找不到正解横幅' % rank)
            continue
        b0, b1 = rs[0]
        k = (b0 + b1) // 2
        dst = os.path.join(OUT, 'Vol.6_認定_%s_正解.png' % rank)
        save_rgb565(a[k], dst)
        written.append(dst)
        print('%-6s 正解 t=%6.2fs（横幅 %5.2f–%5.2fs）' % (rank, k / float(FPS),
                                                     b0 / float(FPS), b1 / float(FPS)))

    p = os.path.join(SRC, ALL_VIDEO)
    if os.path.exists(p):
        a = decode(p)
        dst = os.path.join(OUT, 'Vol.6_認定_4段位全認定_選段位.png')
        save_rgb565(a[min(len(a) - 1, 3 * FPS)], dst)
        written.append(dst)
        print('選段位菜单 t=3.00s')

        tail = a[max(0, len(a) - 6 * FPS):]
        mx = tail.max(axis=-1)
        dark = (mx < 90).mean(axis=(1, 2))
        blue = ((tail[..., 2] > 120) & (tail[..., 2] > tail[..., 0] + 40)).mean(axis=(1, 2))
        sel = None
        for i in range(len(tail)):
            if 0.25 < dark[i] < 0.97 and blue[i] < 0.5:
                sel = i
        if sel is not None:
            dst = os.path.join(OUT, 'Vol.6_認定_全段位制覇_エンディング.png')
            save_rgb565(tail[sel], dst)
            written.append(dst)
            print('收尾演出 t=%.2fs' % ((len(a) - len(tail) + sel) / float(FPS)))
    else:
        print('缺素材：', p)

    print('\n共写出 %d 张：' % len(written))
    for f in written:
        print('  ', os.path.basename(f))


if __name__ == '__main__':
    main()
