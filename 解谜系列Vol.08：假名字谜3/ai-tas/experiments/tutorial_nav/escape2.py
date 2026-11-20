#!/usr/bin/env python3.11
"""用 XTEST (不带 --window) 发送按键, 找能跳过教程的键。SDL 忽略 XSendEvent, 只收 XTEST。"""
import sys, time, subprocess
import ds

def main():
    ds.start()
    w = ds.ensure_window()
    subprocess.run(['xdotool', 'windowfocus', w], env=ds.ENV)
    time.sleep(0.3)
    keys = ['e','r','q','Return','BackSpace','space','x','z','w','a','s','d',
            'F1','F2','Escape','Tab','e','e']
    for k in keys:
        subprocess.run(['xdotool', 'key', k], env=ds.ENV)  # XTEST!
        time.sleep(0.6)
        ds.grab(f'xt_{k}')
        print('key', k, flush=True)

if __name__ == '__main__':
    main()
