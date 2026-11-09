#!/usr/bin/env python3
"""Slitherlink 求解器：给定 w×h 线索盘(0-3, 4=空)，求单一闭合环路的边集。
边：H[(h+1)×w] 水平边 + V[h×(w+1)] 垂直边，1=画线。
约束：每格点度数 ∈{0,2}；每个数字格四周边数 == 该数字；全局恰好一个环。
用 DFS + 约束传播（顶点度数剪枝），求解唯一环路。"""
import sys

def solve(w, h, clues):
    Hn=(h+1)*w; Vn=h*(w+1); E=Hn+Vn
    def HI(r,c): return r*w+c
    def VI(r,c): return Hn+r*(w+1)+c
    # 每格4条边
    cell_edges=[[HI(r,c),HI(r+1,c),VI(r,c),VI(r,c+1)] for r in range(h) for c in range(w)]
    # 每个格点相邻边
    vert_edges=[]
    for r in range(h+1):
        for c in range(w+1):
            es=[]
            if c<w: es.append(HI(r,c))
            if c>0: es.append(HI(r,c-1))
            if r<h: es.append(VI(r,c))
            if r>0: es.append(VI(r-1,c))
            vert_edges.append(es)
    # 边 -> 关联格点(2个)
    edge_verts=[]
    for r in range(h+1):
        for c in range(w):
            edge_verts.append((HI(r,c),(r*(w+1)+c, r*(w+1)+c+1)))
    for r in range(h):
        for c in range(w+1):
            edge_verts.append((VI(r,c),(r*(w+1)+c, (r+1)*(w+1)+c)))
    # 保证 edge_verts 按 e 索引
    ev=[None]*E
    for e,(a,b) in [(HI(r,c),(r*(w+1)+c,r*(w+1)+c+1)) for r in range(h+1) for c in range(w)]:
        ev[e]=(a,b)
    for r in range(h):
        for c in range(w+1):
            e=VI(r,c); ev[e]=(r*(w+1)+c,(r+1)*(w+1)+c)
    # 顶点当前度数 & 未定边数
    deg=[0]*( (h+1)*(w+1) )
    und=[0]*( (h+1)*(w+1) )
    for es in vert_edges: pass
    for v in range((h+1)*(w+1)):
        und[v]=len(vert_edges[v])
    val=[0]*E  # 0=未定, 1=线, 2=无线
    clue_cells=[(r,c,clues[r*w+c]) for r in range(h) for c in range(w) if 0<=clues[r*w+c]<=3]
    # 顶点度数约束检查
    def vert_ok(v):
        s=sum(1 for e in vert_edges[v] if val[e]==1)
        u=sum(1 for e in vert_edges[v] if val[e]==0)
        if s>2: return False
        if u==0 and s not in (0,2): return False
        return True
    touched=set()
    def set_edge(e,v):
        touched.add(e); val[e]=v
    def unset(e):
        val[e]=0
    def all_vert_ok():
        for v in range((h+1)*(w+1)):
            s=sum(1 for e in vert_edges[v] if val[e]==1)
            u=sum(1 for e in vert_edges[v] if val[e]==0)
            if s>2 or (u==0 and s not in (0,2)): return False
        return True
    sol=[None]
    def dfs(ci):
        if sol[0] is not None: return
        if ci==len(clue_cells):
            # 剩余未定边全设 2(无线)，检查顶点 + 单环
            rem=[e for e in range(E) if val[e]==0]
            for e in rem: val[e]=2
            if not all_vert_ok():
                for e in rem: val[e]=0
                return
            edges=[e for e in range(E) if val[e]==1]
            if not edges:
                for e in rem: val[e]=0
                return
            # 连通性：并查集/BFS，且每个端点度为2
            from collections import defaultdict
            adj=defaultdict(list)
            for e in edges:
                a,b=ev[e]; adj[a].append(b); adj[b].append(a)
            if any(len(x)!=2 for x in adj.values()):
                for e in rem: val[e]=0
                return
            start=next(iter(adj)); seen={start}; st=[start]
            while st:
                x=st.pop()
                for y in adj[x]:
                    if y not in seen: seen.add(y); st.append(y)
            if len(seen)!=len(adj):
                for e in rem: val[e]=0
                return
            sol[0]=[1 if val[e]==1 else 0 for e in range(E)]
            return
        r,c,num=clue_cells[ci]
        es=cell_edges[r*w+c]
        # 枚举该格4边的所有 0/1 组合，满足 sum==num 且与现值不冲突
        import itertools
        for combo in itertools.product([1,2],repeat=4):
            if sum(1 for x in combo if x==1)!=num: continue
            ok=True; changed=[]
            for e,v in zip(es,combo):
                if val[e]!=0 and val[e]!=v: ok=False; break
                if val[e]==0: set_edge(e,v); changed.append(e)
            if not ok:
                continue
            if all_vert_ok():
                dfs(ci+1)
            for e in changed: unset(e)
            if sol[0] is not None: return
    dfs(0)
    return sol[0], Hn, Vn

if __name__=='__main__':
    import json
    d=json.load(open('/workspace/hudson_tas/解谜系列Vol.05：数回/validation/puzzles.json'))
    p=next(x for x in d if x['idx']==1396)
    s,Hn,Vn=solve(p['w'],p['h'],p['clues'])
    print('idx1396 解:', '无解' if s is None else f'找到，边1数={sum(s)}')
