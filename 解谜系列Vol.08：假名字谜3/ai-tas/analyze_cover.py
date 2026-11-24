import json, itertools, solve_vol8 as s
p=json.load(open(s.ANS,encoding='utf-8'))[0]
g,wd,ht=p['grid'],p['w'],p['h']
MAX_DR,MAX_DC=6,4
pos={n:[(r,c) for r in range(ht) for c in range(wd) if g[r*wd+c]!=0x7f and (g[r*wd+c]&0x7f)==n] for n in range(1,17)}
nums=sorted(pos); N=len(nums); nbit={n:i for i,n in enumerate(nums)}; FULL=(1<<N)-1
views=[(dr,dc) for dr in range(MAX_DR+1) for dc in range(MAX_DC+1)]
cover={}
for dr,dc in views:
    m=0
    for n in nums:
        if any(dr<=r<=dr+3 and dc<=c<=dc+5 for r,c in pos[n]): m|=1<<nbit[n]
    cover[(dr,dc)]=m
START=(0,0)
def md(a,b): return abs(a[0]-b[0])+abs(a[1]-b[1])
def tsp_path(points):
    """从START出发访问points全部的最短路径(终点任意), 返回(步数,顺序)"""
    best=(10**9,None)
    for perm in itertools.permutations(points):
        d=md(START,perm[0]); prev=perm[0]
        for nxt in perm[1:]:
            d+=md(prev,nxt); prev=nxt
        if d<best[0]: best=(d,perm)
    return best

best=(10**9,None)
for k in range(1,6):
    for S in itertools.combinations([v for v in views if v!=START],k):
        cov=cover[START]
        for v in S: cov|=cover[v]
        if cov!=FULL: continue
        d,order=tsp_path(S)
        if d<best[0]: best=(d,(S,order))
    # 找到可行就记录; 继续更大k看是否更短(通常k大反而步数不一定小)

steps,(S,order)=best
print('=== 第1关「填满再滚」集合覆盖方案 ===')
print(f'当前TSP代表格法: 17 步')
print(f'集合覆盖最优  : {steps} 步   停靠视口 {list(order)}')
print()
allstops=[START]+list(order)
v=START; filled=set(); total=0
for stop in allstops:
    d=md(v,stop); total+=d; v=stop
    here=sorted(n for n in nums if n not in filled and any(stop[0]<=r<=stop[0]+3 and stop[1]<=c<=stop[1]+5 for r,c in pos[n]))
    print(f'  停{stop}(滚{d}步): 本窗口填 {here}')
    filled.update(here)
print(f'  合计滚动 {total} 步, 填 {len(filled)}/{N} 数字')
