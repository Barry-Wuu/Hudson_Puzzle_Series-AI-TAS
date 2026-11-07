#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.4 validation 逐关通关证据抽取。

从 7 个录播目录的每关 mp4 抽末帧（-sseof -0.4，与 qc_gen.py 判据同一位置），
按难度归入 mode1_tutorial / mode2_easy / mode3_medium / mode4_hard，
命名 l<NNN>_clear.png。每张即「上屏已解答案盘 + 下屏クリアタイム/金星/総得点」。

入門第 1 問没有归档视频（早期批量从 002 起录），改用实机重打捕获的
原生 256×384 满星结算截图 intro001_source.png（归档在本目录）补齐，
并在报告中标注来源。该帧抓在星星逐颗点亮动画结束之后（4★ 全亮）。

用法：cd validation && python3 extract_clear.py
产出：310 张 l<NNN>_clear.png + extract_report.json（逐张尺寸/星数/体积/来源）
"""
import glob
import json
import os
import shutil
import subprocess

from PIL import Image

import check_stars

BASE = os.path.dirname(os.path.abspath(__file__))

# (难度目录, 满星, 源目录, 首关, 末关, 备注)
SPECS = [
    ('mode1_tutorial', 4, '/workspace/Vol.4_入門录播',           1,  20, '5×5 / 7×7'),
    ('mode2_easy',     4, '/workspace/Vol.4_やさしい录播',       1,  30, '9×9'),
    ('mode2_easy',     4, '/workspace/Vol.4_やさしい11x11录播', 31,  90, '11×11'),
    ('mode3_medium',   5, '/workspace/Vol.4_ふつう11x11录播',    1,  60, '11×11'),
    ('mode3_medium',   5, '/workspace/Vol.4_ふつう11x19录播',   61, 120, '11×19'),
    ('mode4_hard',     6, '/workspace/Vol.4_むずかしい11x19录播', 1, 20, '11×19'),
    ('mode4_hard',     6, '/workspace/Vol.4_むずかしい13x21录播',21, 80, '13×21'),
]
INTRO001_SRC = os.path.join(BASE, 'intro001_source.png')


def find_single(d, k, mode):
    """按关号找唯一单关 mp4；入門 001 走实机截图特例。"""
    if mode == 'mode1_tutorial' and k == 1:
        return INTRO001_SRC if os.path.exists(INTRO001_SRC) else None
    fs = [f for f in glob.glob(os.path.join(d, '*%03d*256x384.mp4' % k))
          if '合集' not in f]
    return fs[0] if len(fs) == 1 else None


def main():
    report = {'files': [], 'bad': [], 'missing': [], 'specs': []}
    for mode, need, d, lo, hi, masu in SPECS:
        outdir = os.path.join(BASE, mode)
        os.makedirs(outdir, exist_ok=True)
        report['specs'].append(dict(mode=mode, full_stars=need, lo=lo, hi=hi,
                                    masu=masu, src_dir=d))
        for k in range(lo, hi + 1):
            src = find_single(d, k, mode)
            out = os.path.join(outdir, 'l%03d_clear.png' % k)
            if not src:
                report['missing'].append('%s/l%03d' % (mode, k))
                print('  缺源: %s l%03d' % (mode, k), flush=True)
                continue
            if src.endswith('.mp4'):
                subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error',
                                '-sseof', '-0.4', '-i', src, '-frames:v', '1',
                                '-y', out], check=True, timeout=60)
            else:
                shutil.copyfile(src, out)
            im = Image.open(out).convert('RGB')
            stars = check_stars.star_count(out)
            rec = dict(mode=mode, n=k, src=os.path.basename(src),
                       src_kind='mp4末帧' if src.endswith('.mp4') else '实机原生截图',
                       size=list(im.size), stars=stars, need=need,
                       bytes=os.path.getsize(out))
            report['files'].append(rec)
            if im.size != (256, 384) or stars != need:
                report['bad'].append(rec)
        print('%s %s %03d~%03d 完成' % (mode, masu, lo, hi), flush=True)

    with open(os.path.join(BASE, 'extract_report.json'), 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print('\n共 %d 张，缺源 %d，异常 %d' %
          (len(report['files']), len(report['missing']), len(report['bad'])), flush=True)
    if report['bad']:
        print('异常明细:', report['bad'][:12], flush=True)
    if report['missing']:
        print('缺源明细:', report['missing'][:12], flush=True)


if __name__ == '__main__':
    main()
