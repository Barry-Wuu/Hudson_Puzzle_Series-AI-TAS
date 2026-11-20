#!/usr/bin/env python3.11
"""
Vol.08 假名字谜3 (NANKURO / AXNJ18) 题库答案提取器.

ROM: /workspace/roms/解谜系列Vol.08：假名字谜3.nds
数据源: NitroFS file id=4 (file_04.bin), CPQ. 块 @ 0x4fcb8
结构:
  CPQ. magic(4) + n_records(u32, =301) + offset_table(n*u32)
  每条记录: header(0x1c) + grid(w*h bytes @0x1c) + tail(16 bytes)
    - grid: 0x7f=黑格; 1..16=数字密码; 0x80标志位=预留答案提示格
    - tail: 16字节 = 数字1..16 各自对应的假名在 71 音表中的索引
玩法本质: 数字→假名的【全局替换密码】填字, 词条组成有意义的日语词。
最快打法: 无需推理, 直接从 tail 解出映射, 每个数字输一次假名即可。
"""
import struct, json, os

ROM = "/workspace/roms/解谜系列Vol.08：假名字谜3.nds"
CPQ_OFF = 0x4fcb8

# 71 音表 (清音50 + 浊音25 + 半浊音5, 与实际键盘布局一致)
GOJ = ["あいうえお","かきくけこ","さしすせそ","たちつてと","なにぬねの",
       "はひふへほ","まみむめも","やゆよ","らりるれろ","わをん",
       "がぎぐげご","ざじずぜぞ","だぢづでど","ばびぶべぼ","ぱぴぷぺぽ"]
KANA = [c for row in GOJ for c in row] + ["っ"]  # 索引71=促音「っ」(由词条上下文推定; 第1关不涉及)

# 键盘坐标 (下屏相对, 已实测 つ=(63,151) 确认): 每格16px, 行y, 清音x=15+16i
KANA_ROWS = {
    119: "アカサタナハマヤラワガザダバパパ",
    135: "イキシチニヒミユリギジヂビピ",
    151: "ウクスツヌフムヨルーグズヅブプ",
    167: "エケセテネヘメレゲゼデベペ",
    183: "オコソトノホモロゴゾドボポ",
}
def kana_pos(kana_katakana):
    for y, row in KANA_ROWS.items():
        if kana_katakana in row:
            return [15 + row.index(kana_katakana)*16, y]
    return None

def to_katakana(hira):
    # 平假名→片假名 (仅本题库用到的字)
    d = {}
    for h, k in zip("あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんがぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽ",
                    "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポ"):
        d[h]=k
    return ''.join(d.get(c,c) for c in hira)

def extract():
    with open(ROM,'rb') as f: rom=f.read()
    # FAT: file id=4
    fat_off=struct.unpack_from('<I',rom,0x48)[0]
    s,e=struct.unpack_from('<II',rom,fat_off+4*8)
    d=rom[s:e]
    p=CPQ_OFF
    assert d[p:p+4]==b'CPQ.', "CPQ magic not found"
    n=struct.unpack_from('<I',d,p+4)[0]
    offs=[struct.unpack_from('<I',d,p+8+4*i)[0] for i in range(n)]
    puzzles=[]
    for i in range(n):
        r=d[p+offs[i]:p+(offs[i+1] if i+1<n else len(d))]
        if len(r)<0x2c: continue
        w,h=r[0x18],r[0x19]
        if not (4<=w<=30 and 4<=h<=30): continue  # 排除 tail 哨兵
        grid=r[0x1c:0x1c+w*h]
        tail=list(r[0x1c+w*h:0x1c+w*h+16])
        if len(tail)<16: continue
        mapping={num+1: (KANA[tail[num]] if tail[num] < len(KANA) else f'?{tail[num]}') for num in range(16)}
        difficulty=struct.unpack_from('<I',r,4)[0]
        puzzles.append({
            "rec": i, "difficulty_field": difficulty, "w": w, "h": h,
            "grid": list(grid), "mapping": mapping,
            "hint_cells": [[y,x,grid[y*w+x]&0x7f] for y in range(h) for x in range(w) if grid[y*w+x]&0x80],
        })
    return puzzles

if __name__=="__main__":
    puzzles=extract()
    out="/workspace/hudson_tas/解谜系列Vol.08：假名字谜3/answers.json"
    json.dump(puzzles,open(out,'w',encoding='utf-8'),ensure_ascii=False)
    from collections import Counter
    print("提取记录数:",len(puzzles))
    print("难度字段分布:",dict(sorted(Counter(p['difficulty_field'] for p in puzzles).items())))
    # 第一关映射与键盘坐标
    p0=puzzles[0]
    print("\n第1关映射 (数字→假名→键盘坐标):")
    for num,kana in sorted(p0['mapping'].items()):
        kk=to_katakana(kana)
        print(f"  {num:2d} -> {kana}({kk}) @ {kana_pos(kk)}")
    print("\nanswers.json 已写出:",out)
