import ndspy.rom, struct, json
r=ndspy.rom.NintendoDSRom.fromFile('/tmp/v10.nds')
a=bytes(r.arm9); b=r.arm9RamAddress
zones=[(0,0xa1cf0,20),(1,0xa21a0,100),(2,0xa2650,100),(3,0xa1de0,80)]
def check(G,M):
    n=len(G)
    for i in range(n):
        for j in range(n):
            if M[i][j]:
                if j+1<n and M[i][j+1]: return 'adj'
                if i+1<n and M[i+1][j]: return 'adj'
    for i in range(n):
        s=[G[i][j] for j in range(n) if not M[i][j]]
        if len(s)!=len(set(s)): return 'rowdup'
        s=[G[j][i] for j in range(n) if not M[j][i]]
        if len(s)!=len(set(s)): return 'coldup'
    cells=[(i,j) for i in range(n) for j in range(n) if not M[i][j]]
    st=[cells[0]]; seen={cells[0]}
    while st:
        i,j=st.pop()
        for di,dj in ((1,0),(-1,0),(0,1),(0,-1)):
            p,q=i+di,j+dj
            if 0<=p<n and 0<=q<n and not M[p][q] and (p,q) not in seen:
                seen.add((p,q)); st.append((p,q))
    if len(seen)!=len(cells): return 'disconn'
    return 'ok'
out=[]; bad=[]
for diff,off,cnt in zones:
    for k in range(cnt):
        p=off+k*12
        w,h=a[p],a[p+1]
        q1,q2=struct.unpack_from('<II',a,p+4)
        o1,o2=q1-b,q2-b
        seg=a[o1:o1+w*h]; msk=a[o2:o2+w*h]
        G=[list(seg[i*w:(i+1)*w]) for i in range(h)]
        M=[list(msk[i*w:(i+1)*w]) for i in range(h)]
        v=check(G,M)
        if v!='ok' or any(x not in (0,1) for x in msk) or not all(1<=x<=max(w,h) for x in seg):
            bad.append((diff,k+1,w,h,v))
        out.append(dict(diff=diff,idx=k+1,w=w,h=h,G=G,M=M))
json.dump(out,open('/tmp/vol10_all.json','w'))
print('total',len(out),'bad',bad[:10],len(bad))
from collections import Counter
print(Counter(o['w'] for o in out))
