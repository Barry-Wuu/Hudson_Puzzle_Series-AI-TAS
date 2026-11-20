#!/usr/bin/env python3.11
"""第1关系统填字。格坐标(24+26c,19+26r),首屏c0-5 r0-3。
机制:点数字格选中 -> 点假名键2次填入。"""
import ds, time, subprocess, json
import solve_vol8 as s

def focus():
    w=ds.ensure_window()
    subprocess.run(['xdotool','windowfocus',w],env=ds.ENV); time.sleep(0.2)
def tap(x,y,after=0.4):
    ds.tap(x,y,hold=0.08,after=after,gap=0.04)
def fill_num(num, r, c, kana):
    x,y=24+26*c,19+26*r
    tap(x,y,0.4)                       # 选中数字格
    s.tap_kana(kana,twice=True,after=0.5)
    time.sleep(0.25)
    print(f'  数字{num}@({r},{c})=({x},{y}) 填{kana}',flush=True)

def main():
    focus()
    p=json.load(open(s.ANS,encoding='utf-8'))[0]
    w,h=p['w'],p['h']; g=p['grid']; mp=p['mapping']
    used=sorted(set(v&0x7f for v in g if (v&0x7f) in range(1,17)))
    done=[]
    for num in used:
        cells=[(r,c) for r in range(min(4,h)) for c in range(min(6,w))
               if g[r*w+c]!=0x7f and (g[r*w+c]&0x7f)==num]
        if not cells: 
            print(f'数字{num}: 需滚动',flush=True); continue
        r,c=cells[0]
        kana=mp.get(num,mp.get(str(num)))
        fill_num(num,r,c,kana)
        done.append(num)
    ds.grab('q1_visible_filled')
    print('已填:',done,flush=True)
    print('待滚动:',sorted(set(used)-set(done)),flush=True)
if __name__=='__main__':
    main()
