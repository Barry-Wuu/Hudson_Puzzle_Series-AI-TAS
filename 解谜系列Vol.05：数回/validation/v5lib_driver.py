#!/usr/bin/env python3
# Vol.05 数回 (SLITHERLINK / A3LJ) 实机驱动库 —— 复用 Vol.06 验证过的 tap 写法
import os, subprocess, time
import numpy as np
from PIL import Image

DISPLAY = ':99'
OFF = (512, 320)
ENV = dict(os.environ, DISPLAY=DISPLAY)


def sub(*a):
    return subprocess.run(a, env=ENV, capture_output=True, text=True)


def tap(x, y, g=0.09, h=0.05):
    sub('xdotool', 'mousemove', str(x + OFF[0]), str(y + OFF[1]),
        'sleep', f'{g:.3f}', 'mousedown', '1', 'sleep', f'{h:.3f}', 'mouseup', '1')


def taps(cells, g=0.012, h=0.020, a=0.003, batch=40):
    cells = list(cells)
    for i in range(0, len(cells), batch):
        args = []
        for (x, y) in cells[i:i + batch]:
            args += ['mousemove', str(x + OFF[0]), str(y + OFF[1]),
                     'sleep', f'{g:.3f}', 'mousedown', '1', 'sleep', f'{h:.3f}',
                     'mouseup', '1', 'sleep', f'{a:.3f}']
        if args:
            sub('xdotool', *args)
            time.sleep(0.06)


def cap(p='/tmp/_v5.png'):
    sub('import', '-window', 'root', '-crop', '256x384+512+320', p)
    return np.array(Image.open(p).convert('RGB')).astype(int)


def focus():
    r = sub('xdotool', 'search', '--name', 'Desmume')
    w = r.stdout.strip().splitlines()[0] if r.stdout.strip() else None
    if w:
        sub('xdotool', 'windowfocus', w)
    return w
