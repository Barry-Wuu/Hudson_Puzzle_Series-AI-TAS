#!/usr/bin/env python3.11
"""XTEST 扫描所有键, 找到能跳过教程的键(上屏橙色チュートリアル标题消失)。
Escape 会退出模拟器, 排除。每次按键后检测上屏左上橙色像素。"""
import sys, time, subprocess
import numpy as np
from PIL import Image
import ds

BASE = '/workspace/hudson_tas/解谜系列Vol.08：假名字谜3'

def orange_count():
    im = ds.grab(None)
    arr = np.asarray(im.convert('RGB')).astype(int)
    reg = arr[8:42, 8:130]  # 上屏左上标题区
    r, g, b = reg[:,:,0], reg[:,:,1], reg[:,:,2]
    return int(((r>150)&(g>60)&(g<190)&(b<110)).sum()), im

def main():
    ds.start()
    w = ds.ensure_window()
    subprocess.run(['xdotool', 'windowfocus', w], env=ds.ENV)
    time.sleep(0.3)
    keys = ['q','w','a','s','d','z','x','c','v','r','e','t','y','u','i','o','p',
            'f','g','h','j','k','l','Return','BackSpace','space','Tab',
            '1','2','3','0','minus','equal','bracketleft','bracketright',
            'F1','F2','F3','F4','F5']
    base, im = orange_count()
    print('base orange', base, flush=True)
    results = []
    for k in keys:
        # 检查模拟器还活着
        if not ds.win():
            print('emulator dead at', k, flush=True); break
        subprocess.run(['xdotool', 'key', k], env=ds.ENV)  # XTEST
        time.sleep(0.45)
        cnt, im = orange_count()
        img = im.copy()
        img.save(f'{BASE}/skipscan_{k}.png')
        results.append((k, cnt))
        print(f'{k:12s} {cnt:4d}', flush=True)
        if cnt < base * 0.3:  # 标题消失
            print(f'*** SKIP by {k} ***', flush=True)
            return k
    print('no skip key found', flush=True)
    return None

if __name__ == '__main__':
    main()
