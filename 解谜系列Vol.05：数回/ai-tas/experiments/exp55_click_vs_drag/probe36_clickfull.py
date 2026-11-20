import os,sys,time,subprocess
sys.path.insert(0,'/workspace/hudson_tas/解谜系列Vol.05：数回/ai-tas')
os.chdir('/workspace/hudson_tas/解谜系列Vol.05：数回/ai-tas')
import ds, slither_big36 as SB, nav18 as N, record_big as RB, record18_v4 as V, slither18 as s18

GAP=float(os.environ.get('G','0.02')); HOLD=float(os.environ.get('H','0.06'))
AFTER=float(os.environ.get('A','0.08'))
LVL=int(os.environ.get('LVL','18')); IDX=1622+LVL

# ---- monkey-patch：只把逐边拖拽换成「点格线段中点」，其余 draw_all 闭环不动 ----
NCALL=[0]
def click_line(kind,r,c,M):
    x1,y1,x2,y2=SB.edge_px(kind,r,c,M)
    mx=int(round((x1+x2)/2.0)); my=int(round((y1+y2)/2.0))
    mx=max(M['X0']+1,min(SB.XMAX-1,mx))
    my=max(M['Y0']+1,min(SB.YMAX-1,my))
    subprocess.run(['xdotool','mousemove',str(ds.WIN_X+mx),str(ds.WIN_Y+192+my),
                    'sleep',str(GAP),'mousedown','1','sleep',str(HOLD),'mouseup','1'],
                   env=ds.ENV)
    time.sleep(AFTER); NCALL[0]+=1
SB.draw_line=click_line

print(f'G={GAP} H={HOLD} A={AFTER} LVL={LVL} IDX={IDX} (点击版draw_line, draw_all闭环)',flush=True)
s18.is_select_ui() or N.boot_to_select()
RB.to_select_of('muzukashii'); N.goto_window(1); N.leave_level()
N.enter_level(LVL); time.sleep(1.0)
ok=RB.ensure_board(LVL,'muzukashii')
print('ensure_board',ok,flush=True)

t0=time.time()
unc,miss,stopped,visited=SB.draw_all(IDX,settled=None,verbose=True)
draw_s=time.time()-t0
ds.grab(f'/tmp/clickfull_l{LVL}_board')
real=SB.top_line_set(); ans=set(SB.edges_of(IDX))
print(f'绘制{draw_s:.1f}s 点击次数{NCALL[0]} 未覆盖{len(unc) if unc else 0} 仍缺{miss} '
      f'上屏: 命中{len(real&ans)} 缺{len(ans-real)} 多{len(real-ans)}',flush=True)
print('  缺样例',sorted(ans-real)[:12],flush=True)
print('  多样例',sorted(real-ans)[:12],flush=True)
