import os,sys,time
sys.path.insert(0,'/workspace/hudson_tas/解谜系列Vol.05：数回/ai-tas')
os.chdir('/workspace/hudson_tas/解谜系列Vol.05：数回/ai-tas')
import numpy as np
import ds, slither_big36 as SB, nav18 as N, record_big as RB, record18_v4 as V, slither18 as s18

s18.is_select_ui() or N.boot_to_select()
RB.to_select_of('muzukashii'); N.goto_window(1); N.leave_level()
N.enter_level(18); RB.ensure_board(18,'muzukashii')
time.sleep(1.2)
M0=SB.measure(1640)
print('M0(实测)',M0,flush=True)

M=dict(X0=11,Y0=9,r0=0,c0=0)   # 标定 r0=0 视口
def redcount(img,x,y0,y1,rad=2):
    R,G,B=img[:,:,0],img[:,:,1],img[:,:,2]
    m=(R>185)&(G<100)&(B<100)&(R>G+90)
    return int(m[max(0,y0-rad):min(192,y1+rad), max(0,x-rad):x+rad+1].sum())

# 答案里 v(9,c) 的列: [3,4,9,12,14,15,16,18,19,20,25,27,28,29,30,34,35,36]
tests=[(3,156),(9,156),(16,156),(20,156),(34,156)]
base=SB.bot_rgb()
for c,y in tests:
    x=M['X0']+16*(c-M['c0'])
    before=redcount(base,x,153,162)
    ds.tap(x,y,hold=0.08,after=0.35)
    cur=SB.bot_rgb()
    after=redcount(cur,x,153,162)
    print(f'v(9,{c}) x={x} 点y={y}: 红像素 {before}->{after} (差{after-before:+d})',flush=True)
    base=cur
ds.grab('probe_row10_end')
print('done',flush=True)
