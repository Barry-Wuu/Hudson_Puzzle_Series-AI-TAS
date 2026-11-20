#!/usr/bin/env python3.11
"""Vol.08 第1关端到端自动填字 —— 蓝箭头滚动视口版。
机制(2026-11-20实测):
  - 下屏盘面视口6列x4行, 完整10x10在上屏; 盘面框四边中点有橙/灰三角箭头:
      上(90,4) 下(90,107) 左(11,55) 右(165,55)  [下屏相对坐标]
      点一次滚动1格; 箭头仅在"还能滚的方向"显示。
  - 格屏幕坐标 = (24+26*(c-dc), 19+26*(r-dr)), 视口 dc∈[0,4] dr∈[0,6]
  - 填字 = 点数字格选中 -> 点对应假名键2次(全局替换该数字)
"""
import ds, time, subprocess, json
import solve_vol8 as s

ARROW_UP=(90,4); ARROW_DOWN=(90,107); ARROW_LEFT=(11,55); ARROW_RIGHT=(165,55)
GRID_X0, GRID_Y0, PITCH = 24, 19, 26
MAX_DR, MAX_DC = 6, 4

def focus():
    w=ds.ensure_window()
    subprocess.run(['xdotool','windowfocus',w],env=ds.ENV); time.sleep(0.15)

def tap(x,y,a=0.35):
    ds.tap(x,y,hold=0.07,after=a,gap=0.04)

class View:
    def __init__(self):
        self.dr=0; self.dc=0  # 假设从干净盘面(0,0)开始; main里会先复位
    def reset(self):
        # 连点上/左箭头到顶(多于上限)
        for _ in range(10): tap(*ARROW_UP,0.12)
        for _ in range(10): tap(*ARROW_LEFT,0.12)
        self.dr=0; self.dc=0
    def go(self,tr,tc):
        # 目标视口左上角 tr,tc (截断到上限)
        tr=min(max(tr,0),MAX_DR); tc=min(max(tc,0),MAX_DC)
        while self.dr<tr: tap(*ARROW_DOWN,0.12); self.dr+=1
        while self.dr>tr: tap(*ARROW_UP,0.12); self.dr-=1
        while self.dc<tc: tap(*ARROW_RIGHT,0.12); self.dc+=1
        while self.dc>tc: tap(*ARROW_LEFT,0.12); self.dc-=1
    def cell(self,r,c):
        return (GRID_X0+PITCH*(c-self.dc), GRID_Y0+PITCH*(r-self.dr))

def pick_cell(cells):
    # 选一个格, 返回(格, 视口dr,dc) 使视口移动代价最小且格在视口内
    best=None
    for (r,c) in cells:
        # 视口需满足 c-dc∈[0,5], r-dr∈[0,3]
        dc=min(max(c-2,0),MAX_DC); dr=min(max(r-1,0),MAX_DR)
        if not (0<=c-dc<6 and 0<=r-dr<4):
            dc=min(c,MAX_DC); dr=min(r,MAX_DR)
        cost=abs(dr)+abs(dc)
        if best is None or cost<best[0]:
            best=(cost,r,c,dr,dc)
    return best

def main():
    focus()
    p=json.load(open(s.ANS,encoding='utf-8'))[0]
    g=p['grid']; w=p['w']; h=p['h']; mp=p['mapping']
    positions={}
    for num in range(1,17):
        positions[num]=[(r,c) for r in range(h) for c in range(w)
                        if g[r*w+c]!=0x7f and (g[r*w+c]&0x7f)==num]
    v=View()  # 干净盘面视口天然(0,0)
    print('起始视口(0,0)',flush=True)
    done=[]
    for num in range(1,17):
        cells=positions[num]
        cost,r,c,dr,dc=pick_cell(cells)
        v.go(dr,dc)
        x,y=v.cell(r,c)
        if not (0<=x<256 and 0<=y<192):
            print(f'数字{num} 格({r},{c})->屏幕({x},{y}) 越界,跳过',flush=True); continue
        tap(x,y,0.35)  # 选中数字格
        kana=mp.get(num,mp.get(str(num)))
        s.tap_kana(kana,twice=True,after=0.45)
        time.sleep(0.2)
        done.append(num)
        print(f'数字{num} 格({r},{c}) 视口({dr},{dc}) 屏幕({x},{y}) 填{kana} OK',flush=True)
    ds.grab('full_all_filled')
    print('完成:',done,flush=True)

if __name__=='__main__':
    main()
