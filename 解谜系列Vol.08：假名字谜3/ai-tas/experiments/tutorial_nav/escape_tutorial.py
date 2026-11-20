#!/usr/bin/env python3.11
"""自动尝试各种方式脱离教程页, 用上屏左上角橙色标题像素检测。"""
import sys, time
import numpy as np
from PIL import Image
import ds


def is_tutorial():
    """教程页: 上屏左上角有橙色『チュートリアル』标题(放大图 x10-260,y10-45)。
    ds.grab 返回 256x384, 上屏是 y=0..191。标题在上屏左上。"""
    im = ds.grab(None)
    arr = np.asarray(im.convert('RGB')).astype(int)
    # 上屏左上区域找橙色 (R高,G中,B低)
    reg = arr[8:40, 8:120]
    r, g, b = reg[:,:,0], reg[:,:,1], reg[:,:,2]
    orange = ((r > 150) & (g > 60) & (g < 180) & (b < 100)).sum()
    return orange, im


def save(im, tag):
    im.save(f'/workspace/hudson_tas/解谜系列Vol.08：假名字谜3/esc_{tag}.png')


def main():
    ds.start()
    # 候选操作序列, 每个是一个 (名字, 函数)
    ops = []
    for k in ['e', 'E', 'q', 'Return', 'BackSpace', 'x', 'z', 'w', 'a', 's', 'd', 'r', 'R', 'c', 'v']:
        ops.append((f'key_{k}', lambda k=k: ds.press(k, wait=0.6)))
    # 触摸スキップ区(上屏不可触摸, 试下屏对应位置)
    ops.append(('tap_skip_down', lambda: ds.tap(200, 150, after=0.7)))
    ops.append(('tap_bottom', lambda: ds.tap(128, 188, after=0.7)))

    for name, fn in ops:
        before, im = is_tutorial()
        fn()
        after, im2 = is_tutorial()
        tag = name.replace('/', '_')
        save(im2, tag)
        print(f'{name:18s} orange {before:4d}->{after:4d}', flush=True)
        if after < 30:  # 橙色标题消失 = 离开教程
            print(f'*** ESCAPED by {name} ***', flush=True)
            return name
    return None


if __name__ == '__main__':
    main()
