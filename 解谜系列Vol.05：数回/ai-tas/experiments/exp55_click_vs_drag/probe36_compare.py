import os,sys,time
sys.path.insert(0,'/workspace/hudson_tas/解谜系列Vol.05：数回/ai-tas')
os.chdir('/workspace/hudson_tas/解谜系列Vol.05：数回/ai-tas')
import ds, slither_big36 as SB, nav18 as N, record_big as RB, record18_v4 as V, slither18 as s18

MODE = os.environ.get('MODE','drag')   # drag | click
LVL=18; IDX=1640
print('MODE',MODE,flush=True)

s18.is_select_ui() or N.boot_to_select()
RB.to_select_of('muzukashii'); N.goto_window(1); N.leave_level()
N.enter_level(LVL); RB.ensure_board(LVL,'muzukashii')
time.sleep(1.2)

# 确认净盘：下屏红线像素=0
a=SB.bot_rgb(); R,G,B=a[:,:,0],a[:,:,1],a[:,:,2]
red=int(((R>190)&(G<95)&(B<95)&(R>G+100)).sum())
print('净盘红线像素',red,flush=True)

t0=time.time()
if MODE=='drag':
    unc,miss,stopped,visited=SB.draw_all(IDX,settled=None,verbose=False)
else:
    import importlib.util
    spec=importlib.util.spec_from_file_location('pv','/tmp/probe36_visible_lib.py')
    pv=importlib.util.module_from_spec(spec); spec.loader.exec_module(pv)
    pv.draw_click(IDX)
draw_s=time.time()-t0

# 画完立即抓上屏比对（此时盘面还在，未 judge）
ds.grab('/tmp/probe36_compare_board')
real=SB.top_line_set(); ans=set(SB.edges_of(IDX))
print(f'绘制耗时{draw_s:.1f}s 上屏线集: 命中{len(real&ans)} 缺{len(ans-real)} 多{len(real-ans)}',flush=True)
print('  缺样例',sorted(ans-real)[:10],flush=True)
print('  多样例',sorted(real-ans)[:10],flush=True)
