#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把仓库内所有位图 PNG 统一压成 8-bit 索引（≤256 色）。

口径：
  * 已是 P（索引）或 L（8 位灰度）的图**不动** —— P 本来就 ≤256 色，L 是 256 级灰度。
  * RGB / RGBA：中位切（MEDIANCUT）量化到 256 色，无抖动。
    - 若原图去重色数 ≤256，该量化是**逐像素无损**的（PSNR = ∞），只做重编码。
    - 有透明通道的图走 RGBA→P，保留透明索引。
  * 逐张记 PSNR / 最大单通道偏差，写进 tools/png256_report.json，供事后核查。

用法：
  python3 tools/png256.py --dry        # 只统计，不落盘
  python3 tools/png256.py              # 就地改写（git 可回滚）
  python3 tools/png256.py --dry --all  # 连已 P/L 的也算进统计
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {'.git', '__pycache__', 'node_modules'}


def png_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.lower().endswith('.png'):
                yield os.path.join(dirpath, fn)


def psnr(a, b):
    m = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return 999.0 if m == 0 else 10 * np.log10(255.0 ** 2 / m)


def convert(path, dry):
    size0 = os.path.getsize(path)
    im = Image.open(path)
    mode = im.mode
    if mode in ('P', 'L', '1', 'LA'):
        return dict(path=path, mode=mode, skipped=True, size0=size0, size1=size0,
                    colors=None, psnr=None, maxdiff=None)
    has_alpha = mode in ('RGBA', 'LA', 'PA')
    rgb = im.convert('RGBA' if has_alpha else 'RGB')
    arr = np.array(rgb)
    plane = arr[:, :, :3].reshape(-1, 3)
    ncol = len(np.unique(plane, axis=0))
    q = rgb.quantize(colors=256, method=Image.MEDIANCUT)
    back = np.array(q.convert('RGBA' if has_alpha else 'RGB'))
    diff = np.abs(arr.astype(np.int16) - back.astype(np.int16))
    p = round(float(psnr(arr, back)), 2)
    md = int(diff.max())
    if not dry:
        q.save(path, 'PNG', optimize=True, compress_level=9)
        size1 = os.path.getsize(path)
    else:
        import io
        buf = io.BytesIO()
        q.save(buf, 'PNG', optimize=True, compress_level=9)
        size1 = buf.tell()
    return dict(path=path, mode=mode, skipped=False, size0=size0, size1=size1,
                colors=ncol, psnr=p, maxdiff=md)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--all', action='store_true', help='统计里也带上已 P/L 的图')
    args = ap.parse_args()

    rows = []
    files = sorted(png_files())
    for i, f in enumerate(files, 1):
        try:
            rows.append(convert(f, args.dry))
        except Exception as e:
            print('ERR %s: %s' % (f, e), file=sys.stderr)
        if i % 200 == 0:
            print('  %d/%d ...' % (i, len(files)), flush=True)

    conv = [r for r in rows if not r['skipped']]
    t0 = sum(r['size0'] for r in conv)
    t1 = sum(r['size1'] for r in conv)
    print('\nPNG 总数 %d：压缩 %d 张，跳过（已是 P/L）%d 张' % (len(rows), len(conv), len(rows) - len(conv)))
    if not conv:
        print('无可压缩对象（全仓已是 8-bit 索引/灰度）')
    else:
        print('压缩子集：%.1f MB → %.1f MB（%.1f%%，%.2f×）' % (t0 / 1048576, t1 / 1048576,
                                                          100.0 * t1 / t0, t0 / max(t1, 1)))
    if conv:
        ps = np.array([r['psnr'] for r in conv])
        lossless = [r for r in conv if r['psnr'] > 900]
        print('无损（原图 ≤256 色）：%d 张' % len(lossless))
        rest = np.array([r['psnr'] for r in conv if r['psnr'] <= 900])
        if len(rest):
            print('有损部分 PSNR：均 %.2f  最低 %.2f  p5 %.2f  p50 %.2f（%d 张）' % (
                rest.mean(), rest.min(), np.percentile(rest, 5), np.median(rest), len(rest)))
            worst = sorted([r for r in conv if r['psnr'] <= 900], key=lambda r: r['psnr'])[:8]
            print('最低 8 张：')
            for r in worst:
                print('   %6.2f dB  maxdiff %3d  %5.1f→%5.1f KB  %s' % (
                    r['psnr'], r['maxdiff'], r['size0'] / 1024, r['size1'] / 1024,
                    os.path.relpath(r['path'], ROOT)))

    by_vol = {}
    for r in rows:
        vol = os.path.relpath(r['path'], ROOT).split(os.sep)[0]
        d = by_vol.setdefault(vol, [0, 0, 0])
        d[0] += 1
        d[1] += r['size0']
        d[2] += r['size1']
    print('\n分卷：')
    for k in sorted(by_vol):
        n, a, b = by_vol[k]
        print('  %-24s %4d 张  %6.1f → %5.1f MB' % (k, n, a / 1048576, b / 1048576))
    all0 = sum(r['size0'] for r in rows)
    all1 = sum(r['size1'] for r in rows)
    print('全仓 %d 张：%.1f → %.1f MB' % (len(rows), all0 / 1048576, all1 / 1048576))

    if not args.dry:
        out = os.path.join(ROOT, 'tools', 'png256_report.json')
        with open(out, 'w', encoding='utf-8') as fh:
            json.dump([dict(r, path=os.path.relpath(r['path'], ROOT)) for r in rows],
                      fh, ensure_ascii=False, indent=1)
        print('明细:', out)


if __name__ == '__main__':
    main()
