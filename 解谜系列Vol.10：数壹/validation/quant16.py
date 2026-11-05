#!/usr/bin/env python3
"""validation 截图 16 位色量化（NDS 原生 BGR555）。

用法：cd validation && python3 quant16.py [--dry]

为什么是 5 bit/通道：
  · DS 硬件帧缓冲就是 15 位色（BGR555），截图链路 512×768 窗口 → h264 → 256×384
    带进了 8 bit 的插值/压缩噪声（每张 1.4~1.9 万色），体积虚高。
  · 把每通道压回 5 bit（(v>>3)<<3|4，落在 5 bit 桶中心），色数降到 ~2500，
    体积约减半，且与 DS 真实发色一致。

为什么不做 128 色索引（Vol.11/12/13 的口径）：
  · 那些卷是「原生 256×384 截图」，画面本身 ≤150 色，256 色调色板容纳得下，量化近乎恒等。
  · 本卷图源是 h264 视频帧，色数上万；压到 128 色后星形金色被压出色域，
    check_stars.py 的判星会大面积失效（实测 300 张里有 115 张读错），故只做 16 位量化。

校验：量化后 python3 check_stars.py 结果与量化前逐张一致（入門 20×3★ / やさしい 100×4★ /
      ふつう 50×5★ + 50 完成图 / むずかしい 80×6★）。
"""
import glob
import io
import os
import sys

import numpy as np
from PIL import Image


def q555(im):
    a = np.asarray(im.convert('RGB')).astype(np.uint16)
    return Image.fromarray(np.clip(((a >> 3) << 3) | 4, 0, 255).astype(np.uint8), 'RGB')


def already(im):
    """已是量化态（三通道低 3 位均为 100）则无需再处理。"""
    a = np.asarray(im, dtype=np.uint16)
    return bool(((a & 7) == 4).all())


def main(root='.', dry=False):
    files = sorted(glob.glob(os.path.join(root, '**', '*.png'), recursive=True))
    t0 = t1 = n_skip = 0
    for f in files:
        t0 += os.path.getsize(f)
        im = Image.open(f)
        im.load()                      # 关键：先把像素读进内存，绝不惰性持有文件句柄
        im = im.convert('RGB')
        if already(im):
            t1 += os.path.getsize(f)
            n_skip += 1
            continue
        out = q555(im)
        buf = io.BytesIO()
        out.save(buf, 'PNG', optimize=True)
        t1 += len(buf.getvalue())
        if not dry:
            # 原子替换：先写同目录临时文件，落盘后再 rename，避免中途中断留下 0 字节
            tmp = f + '.tmp'
            with open(tmp, 'wb') as fh:
                fh.write(buf.getvalue())
            os.replace(tmp, f)
    print(f'{len(files)} 张（跳过已量化 {n_skip}）：{t0/1048576:.2f}MB → {t1/1048576:.2f}MB'
          f'（−{100*(1-t1/t0):.1f}%）' + ('（dry-run，未写盘）' if dry else ''))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '.', '--dry' in sys.argv)
