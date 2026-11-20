#!/usr/bin/env python3.11
"""Vol.08 干净端到端: 重启->跳教程->进第1关->系统填字。
机制(2026-11-20确认): 点数字格选中该数字 -> 点对应假名键2次填入。
格坐标: 下屏相对 (22+30c, 12+30r), 首屏可见 c0-5 r0-3。
"""
import ds, time, subprocess, json
import solve_vol8 as s

W=None
def focus():
    global W
    W=ds.ensure_window()
    subprocess.run(['xdotool','windowfocus',W],env=ds.ENV); time.sleep(0.25)
def tap(x,y,after=0.5):
    ds.tap(x,y,hold=0.08,after=after,gap=0.04)
def skip_tutorial():
    # 标题->菜单过渡页: 触摸推进到实操页
    for i in range(4):
        tap(128,100,0.6)
        # 检测是否到辅助选择
    # 实操页长按w跳过
    subprocess.run(['xdotool','keydown','w'],env=ds.ENV); time.sleep(1.8)
    subprocess.run(['xdotool','keyup','w'],env=ds.ENV); time.sleep(1.2)
def nav_q1():
    # 辅助选择: 找サポートなし(通常图195,290->97,145), 点两次
    tap(97,145,0.4); tap(97,145,1.2)
    # 主菜单 通常問題(137,75)
    tap(137,75,0.4); tap(137,75,0.8)
    # 难度 やさしい(137,61)
    tap(137,61,0.4); tap(137,61,0.8)
    # 选关 第1关(18,75)
    tap(18,75,0.4); tap(18,75,1.5)

def solve_visible():
    p=json.load(open(s.ANS,encoding='utf-8'))[0]
    w,h=p['w'],p['h']; g=p['grid']; mp=p['mapping']
    used=sorted(set(v&0x7f for v in g if (v&0x7f) in range(1,17)))
    done=set()
    for num in used:
        # 首屏可见格
        cells=[(r,c) for r in range(min(4,h)) for c in range(min(6,w))
               if g[r*w+c]!=0x7f and (g[r*w+c]&0x7f)==num]
        if not cells:
            print(f'数字{num}: 首屏无格,跳过',flush=True); continue
        r,c=cells[0]
        x,y=22+30*c,12+30*r
        tap(x,y,0.45)              # 选中该数字
        kana=mp.get(num,mp.get(str(num)))
        s.tap_kana(kana,twice=True,hold=0.08,after=0.5)
        time.sleep(0.3)
        done.add(num)
        print(f'  数字{num}@{r},{c}->({x},{y}) 填{kana}',flush=True)
    ds.grab('clean_filled')
    print('已填:',sorted(done),flush=True)
    print('未填(需滚动):',sorted(set(used)-done),flush=True)

if __name__=='__main__':
    ds.kill(); ds.start(); focus()
    tap(128,150,1.0)   # 标题
    skip_tutorial(); focus()
    ds.grab('cs_after_skip')
    nav_q1(); focus()
    ds.grab('cs_q1')
    solve_visible()
