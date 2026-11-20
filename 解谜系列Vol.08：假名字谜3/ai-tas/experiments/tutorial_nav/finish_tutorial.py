#!/usr/bin/env python3.11
"""用 XTEST 连续按 A(X) 翻完教程所有页, 检测离开教程。"""
import sys, time, subprocess
import numpy as np
import ds

BASE = '/workspace/hudson_tas/解谜系列Vol.08：假名字谜3'

def orange():
    im = ds.grab(None)
    a = np.asarray(im.convert('RGB')).astype(int)
    reg = a[8:42, 8:130]
    return int(((reg[:,:,0]>150)&(reg[:,:,1]>60)&(reg[:,:,1]<190)&(reg[:,:,2]<110)).sum()), im

def main():
    ds.kill(); ds.start(); time.sleep(6)
    w = ds.ensure_window()
    subprocess.run(['xdotool','windowfocus',w],env=ds.ENV); time.sleep(0.3)
    # 标题 -> 菜单 -> スタート
    ds.tap(128,150,after=1.0)
    ds.tap(128,48,after=2.0)
    subprocess.run(['xdotool','windowfocus',w],env=ds.ENV); time.sleep(0.2)
    cnt, im = orange()
    print('start orange', cnt, flush=True)
    for i in range(40):
        if not ds.win(): print('dead',flush=True); break
        subprocess.run(['xdotool','key','x'],env=ds.ENV)  # XTEST A
        time.sleep(0.55)
        cnt, im = orange()
        im.save(f'{BASE}/fin_{i:02d}.png')
        print(f'{i:02d} orange={cnt}', flush=True)
        if cnt < 30:
            print(f'*** LEFT TUTORIAL at step {i} ***', flush=True)
            return
    print('still in tutorial', flush=True)

if __name__ == '__main__':
    main()
