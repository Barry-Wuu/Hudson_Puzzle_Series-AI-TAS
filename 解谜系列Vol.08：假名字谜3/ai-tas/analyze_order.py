import json, solve_vol8 as s
p=json.load(open(s.ANS,encoding='utf-8'))[0]
g,wd,ht=p['grid'],p['w'],p['h']
MAX_DR,MAX_DC=6,4
pos={n:[(r,c) for r in range(ht) for c in range(wd) if g[r*wd+c]!=0x7f and (g[r*wd+c]&0x7f)==n] for n in range(1,17)}

# 复用当前 pick_cell 逻辑: 为每个数字选一个代表格 -> 视口目标(dr,dc)
def pick(cells):
    best=None
    for r,c in cells:
        dc=min(max(c-2,0),MAX_DC); dr=min(max(r-1,0),MAX_DR)
        if not (0<=c-dc<6 and 0<=r-dr<4):
            dc=min(c,MAX_DC); dr=min(r,MAX_DR)
        cost=dr+dc
        if best is None or cost<best[0]: best=(cost,r,c,dr,dc)
    return best  # cost,r,c,dr,dc

T={n:pick(pos[n]) for n in range(1,17)}   # n -> (cost,r,c,dr,dc)

def scroll(seq,start=(0,0)):
    v=start; tot=0; detail=[]
    for n in seq:
        dr,dc=T[n][3],T[n][4]
        step=abs(dr-v[0])+abs(dc-v[1])
        tot+=step; detail.append((n,dr,dc,step)); v=(dr,dc)
    return tot,detail

# 1) 数字顺序
seq_num=list(range(1,17))
tot_num,det_num=scroll(seq_num)

# 2) 最近邻贪心
def nearest(start=(0,0)):
    v=start; rem=set(range(1,17)); seq=[]
    while rem:
        n=min(rem,key=lambda n:abs(T[n][3]-v[0])+abs(T[n][4]-v[1]))
        seq.append(n); rem.remove(n); v=(T[n][3],T[n][4])
    return seq
seq_nn=nearest(); tot_nn,_=scroll(seq_nn)

# 3) TSP 精确 (Held-Karp), 16点从(0,0)出发
pts=[(0,0)]+[(T[n][3],T[n][4]) for n in range(1,17)]  # idx0=start, idx n = 数字n
def d(i,j): return abs(pts[i][0]-pts[j][0])+abs(pts[i][1]-pts[j][1])
INF=10**9; FULL=1<<16
dp=[[INF]*17 for _ in range(FULL)]
par=[[-1]*17 for _ in range(FULL)]
for j in range(1,17): dp[1<<(j-1)][j]=d(0,j)
for mask in range(FULL):
    for j in range(1,17):
        if not (mask>>(j-1))&1: continue
        cur=dp[mask][j]
        if cur>=INF: continue
        for k in range(1,17):
            if (mask>>(k-1))&1: continue
            nm=mask|(1<<(k-1)); nv=cur+d(j,k)
            if nv<dp[nm][k]: dp[nm][k]=nv; par[nm][k]=j
full=FULL-1
end=min(range(1,17),key=lambda j:dp[full][j])
tot_tsp=dp[full][end]
seq_tsp=[]; m=full; j=end
while j!=-1:
    seq_tsp.append(j); pj=par[m][j]; m^=(1<<(j-1)); j=pj
seq_tsp=seq_tsp[::-1]

print('=== 每个数字的代表格与视口目标 (数字顺序) ===')
for n,dr,dc,step in det_num:
    print(f'  数字{n:2d} 格({T[n][1]:2d},{T[n][2]:2d}) 视口(dr{dr},dc{dc}) 本步滚动{step}')
print()
print(f'数字顺序(现状) : 滚动总步数 {tot_num:2d}  顺序 {seq_num}')
print(f'最近邻贪心      : 滚动总步数 {tot_nn:2d}  顺序 {seq_nn}')
print(f'TSP最优         : 滚动总步数 {tot_tsp:2d}  顺序 {seq_tsp}')
print()
print(f'优化收益: 数字顺序 {tot_num} -> TSP {tot_tsp}, 省 {tot_num-tot_tsp} 步 ({(tot_num-tot_tsp)/tot_num*100:.0f}%)')
print(f'每步滚动 = 1次箭头点击 after={0.4}s -> 省约 {(tot_num-tot_tsp)*0.4:.1f}s')
