import os,sys,time,subprocess
sys.path.insert(0,'/workspace/hudson_tas/解谜系列Vol.05：数回/ai-tas')
os.chdir('/workspace/hudson_tas/解谜系列Vol.05：数回/ai-tas')
import ds, slither_big36 as SB, nav18 as N, record_big as RB, record18_v4 as V, slither18 as s18

GAP=float(os.environ.get('G','0.02')); HOLD=float(os.environ.get('H','0.06'))
AFTER=float(os.environ.get('A','0.10')); BATCH=int(os.environ.get('B','24')); LEAD=0.20
LVL=int(os.environ.get('LVL','18')); IDX=1622+LVL
DO_JUDGE=os.environ.get('JUDGE','0')=='1'

def click_point(k,r,c,M):
    """边与可画矩形 [X0,XMAX]x[Y0,YMAX] 交段中点。放宽端点判据，第10行可见段也能点。"""
    x1,y1,x2,y2=SB.edge_px(k,r,c,M)
    if k=='h':
        xa=max(int(x1), M['X0']); xb=min(int(x2), SB.XMAX)
        if xb-xa<4: return None
        return ((xa+xb)//2, int(y1))
    else:
        ya=max(int(y1), M['Y0']); yb=min(int(y2), SB.YMAX)
        if yb-ya<4: return None
        return (int(x1), (ya+yb)//2)

def click_cmd(points,lead=0):
    cmd=['xdotool']
    for i,(mx,my) in enumerate(points):
        sx,sy=ds.WIN_X+mx,ds.WIN_Y+192+my
        g=GAP+(lead if i==0 else 0)
        cmd+=['mousemove',str(sx),str(sy),'sleep',str(g),'mousedown','1','sleep',str(HOLD),'mouseup','1','sleep',str(AFTER)]
    return cmd

def park(): subprocess.run(['xdotool','mousemove',str(ds.WIN_X+250),str(ds.WIN_Y+380)],env=ds.ENV)

def draw_click(idx, verbose=True):
    edges=SB.edges_of(idx); rem=set(edges); ds.ensure_window(); tp=0; nv=0
    for step,action in enumerate(SB.SCROLL_SEQ):
        if V.settled(): break
        if action:
            ds.tap(*SB.TAPS[action],hold=0.18,after=1.2); time.sleep(0.7)
        if step not in SB.DRAW_VIEWS: continue
        M=SB.DRAW_VIEWS[step]              # 标定视口，不 measure（24x14 成功经验）
        pts=[]; picked=[]
        for e in edges:
            if e not in rem: continue
            p=click_point(*e,M)
            if p is None: continue
            pts.append(p); picked.append(e)
        for i in range(0,len(pts),BATCH):
            subprocess.run(click_cmd(pts[i:i+BATCH],LEAD),env=ds.ENV,check=True)
        park(); time.sleep(0.2); tp+=len(pts); nv+=1
        for e in picked: rem.discard(e)
        if verbose: print(f'  视口#{step} 标定(c0={M["c0"]},r0={M["r0"]}) 点{len(pts)} 剩{len(rem)}',flush=True)
    return tp,nv,len(rem)

if __name__=='__main__':
    print(f'G={GAP} H={HOLD} A={AFTER} LVL={LVL} IDX={IDX}',flush=True)
    s18.is_select_ui() or N.boot_to_select()
    RB.to_select_of('muzukashii'); N.goto_window(1); N.leave_level()
    N.enter_level(LVL); RB.ensure_board(LVL,'muzukashii')
    time.sleep(1.2)
    a=SB.bot_rgb(); R,G,B=a[:,:,0],a[:,:,1],a[:,:,2]
    print('净盘红线像素',int(((R>190)&(G<95)&(B<95)&(R>G+100)).sum()),flush=True)
    t0=time.time(); tp,nv,rem=draw_click(IDX); draw_s=time.time()-t0
    # 画完立即上屏比对（未 judge，盘面还在）
    ds.grab(f'/tmp/cal_click_l{LVL}_board')
    real=SB.top_line_set(); ans=set(SB.edges_of(IDX))
    print(f'绘制{draw_s:.1f}s 点{tp}边 视口{nv} 剩{rem} 上屏: 命中{len(real&ans)} 缺{len(ans-real)} 多{len(real-ans)}',flush=True)
    print('  缺样例',sorted(ans-real)[:10],flush=True)
    print('  多样例',sorted(real-ans)[:10],flush=True)
    if DO_JUDGE:
        cleared,dt,kind=V.judge()
        print(f'判定 cleared={cleared} kind={kind} 耗时{dt:.1f}s',flush=True)
