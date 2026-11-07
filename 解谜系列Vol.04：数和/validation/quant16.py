#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.4 validation 截图 16 位色量化（NDS 原生 BGR555）。

用法：cd validation && python3 quant16.py [--dry]

口径与 Vol.10 一致：
  · 309 张图源是 h264 视频帧（每张上万色，含压缩噪声），1 张是原生截图。
    把每通道压回 5 bit（(v>>3)<<3|4，落在 5 bit 桶中心），色数降到 ~2500，
    体积约减半，且与 DS 真实发色一致。
  · 不做 Vol.11/12/13 的 128 色索引：那几卷是原生 256×384 截图（≤150 色），
    调色板量化近乎恒等；本卷视频帧色数上万，压到 128 色会把金星橙色压出色域，
    check_stars.py 的判星会大面积失效。
  · 量化前后 check_stars.py 判星结果必须逐张一致（见 README 复核一节）。
  · 原子替换：临时文件 + os.replace，避免中断留下 0 字节图。
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
        im.load()
        im = im.convert('RGB')
        if already(im):
            t1 += os.path.getsize(f)
            n_skip += 1
            continue
        buf = io.BytesIO()
        q555(im).save(buf, 'PNG', optimize=True)
        t1 += len(buf.getvalue())
        if not dry:
            tmp = f + '.tmp'
            with open(tmp, 'wb') as fh:
                fh.write(buf.getvalue())
            os.replace(tmp, f)
    print('%d 张（跳过已量化 %d）：%.2fMB → %.2fMB（−%.1f%%）%s' %
          (len(files), n_skip, t0 / 1048576, t1 / 1048576,
           100 * (1 - t1 / t0), '（dry-run，未写盘）' if dry else ''))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '.', '--dry' in sys.argv)
