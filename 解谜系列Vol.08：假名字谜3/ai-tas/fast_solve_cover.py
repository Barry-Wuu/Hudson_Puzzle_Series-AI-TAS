#!/usr/bin/env python3.11
"""Vol.08 真正最速填字 —— 集合覆盖 + 填满再滚。

核心(用户指正): 旧 fast_solve_vol8.py 对每个数字选1个代表格再对16格做TSP(17步),
但它在一个视口里只填1个数字就滚走。正确做法: 视口6x4, 一个数字只要有任一格
落在视口内就能填; 选最少视口停靠点覆盖全部数字, 每个停靠点把可见数字全填完再滚。

第1关: 17步 -> 5步。挡板见 analyze_cover.py。
"""
import time, subprocess, json, sys
import ds
import solve_vol8 as s
from plan_stops import plan_stops

LEVEL = int(sys.argv[1]) if len(sys.argv) > 1 else 1
AFTER = float(sys.argv[2]) if len(sys.argv) > 2 else 0.40

ARROW_UP=(90,4); ARROW_DOWN=(90,107); ARROW_LEFT=(11,55); ARROW_RIGHT=(165,55)
GX0,GY0,PITCH=24,19,26
MAX_DR,MAX_DC=6,4
HOLD,GAP=0.06,0.04


def lite_tap(x,y,after=AFTER):
    subprocess.run(["xdotool","mousemove",str(ds.WIN_X+x),str(ds.WIN_Y+192+y),
        "sleep",str(GAP),"mousedown","1","sleep",str(HOLD),"mouseup","1"],env=ds.ENV)
    time.sleep(after)


def kana_tap(kana,mp):
    kk=s.HIRA2KATA.get(kana,kana)
    pos=s.KANA_POS.get(kk)
    if not pos:
        print(f"  !! {kana}({kk}) 无键位",flush=True); return False
    lite_tap(*pos); lite_tap(*pos)
    return True


class View:
    def __init__(self): self.dr=0; self.dc=0
    def go(self,tr,tc):
        tr=min(max(tr,0),MAX_DR); tc=min(max(tc,0),MAX_DC)
        while self.dr<tr: lite_tap(*ARROW_DOWN); self.dr+=1
        while self.dr>tr: lite_tap(*ARROW_UP); self.dr-=1
        while self.dc<tc: lite_tap(*ARROW_RIGHT); self.dc+=1
        while self.dc>tc: lite_tap(*ARROW_LEFT); self.dc-=1
    def cell(self,r,c): return (GX0+PITCH*(c-self.dc), GY0+PITCH*(r-self.dr))


def visible(pos_n, dr, dc):
    """数字n在视口(dr,dc)内可见的格子列表"""
    return [(r,c) for r,c in pos_n if dr<=r<=dr+3 and dc<=c<=dc+5]


def main():
    w=ds.ensure_window()
    subprocess.run(["xdotool","windowfocus",w],env=ds.ENV)
    time.sleep(0.15)
    p=json.load(open(s.ANS,encoding="utf-8"))[LEVEL-1]
    g,wd,ht,mp=p["grid"],p["w"],p["h"],p["mapping"]
    pos={n:[(r,c) for r in range(ht) for c in range(wd)
             if g[r*wd+c]!=0x7f and (g[r*wd+c]&0x7f)==n] for n in range(1,17)}
    stops,est=plan_stops(pos)
    print(f"第{LEVEL}关 {wd}x{ht}  停靠视口={stops} 预计滚动{est}步",flush=True)

    v=View(); t0=time.time(); scroll=0; filled=set()
    for stop in stops:
        scroll+=abs(stop[0]-v.dr)+abs(stop[1]-v.dc)
        v.go(*stop)
        # 该视口内, 把所有可见且未填的数字全填了
        for n in sorted(pos):
            if n in filled: continue
            vis=visible(pos[n],v.dr,v.dc)
            if not vis: continue
            # 选视口内坐标最靠左上(点击稳)的一格
            r,c=vis[0]
            x,y=v.cell(r,c)
            if not (0<=x<256 and 0<=y<192): continue
            lite_tap(x,y)
            kana_tap(mp.get(n,mp.get(str(n))),mp)
            filled.add(n)
    dt=time.time()-t0
    ds.grab("cover_filled")
    print(f"填字墙钟 {dt:.2f}s, 视口滚动 {scroll} 步, 填 {len(filled)}/16 数字",flush=True)


if __name__=="__main__": main()
