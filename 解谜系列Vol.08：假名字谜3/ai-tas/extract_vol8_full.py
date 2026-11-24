#!/usr/bin/env python3.11
"""Vol.08 假名字谜3 —— 全关卡盘面+答案离线提取(完整版)。

修复原 extract_vol8_answers.py 的缺陷:
  1) 映射写死 16 项 -> 改为动态长度(= 盘面最大密码值),覆盖 252 个 >16 的关卡;
  2) 索引 72 = 墙(黑格),不是假名——实机词条验证: 当「ッ」时满屏乱码,
     当墙时横竖词条全部成词(セクハラ/ネクタイ/コオロギ...)。mapping 中记为 "█"。

每关字段:
  rec / difficulty_field / w / h
  grid      : 长度 w*h 的字节矩阵。127=黑格; 1..N=密码数字; 0x80 位=提示格
  mapping   : {密码数字: 假名}, 动态长度
  kana_idx  : 原始 tail 假名索引, 便于后续核对/标定
  hint_cells: [[y,x,密码数字]...]
"""
import struct, json

ROM = "/workspace/roms/解谜系列Vol.08：假名字谜3.nds"
CPQ_OFF = 0x4fcb8
OUT = "/workspace/hudson_tas/解谜系列Vol.08：假名字谜3/answers_full.json"

GOJ = ["あいうえお", "かきくけこ", "さしすせそ", "たちつてと", "なにぬねの",
       "はひふへほ", "まみむめも", "やゆよ", "らりるれろ", "わをん",
       "がぎぐげござじずぜぞ", "だぢづでど", "ばびぶべぼ", "ぱぴぷぺぽ"]
KANA = [c for row in GOJ for c in row] + ["ー", "█"]  # 71=长音ー, 72=墙█(非假名; 词条验证坐实)


def extract():
    rom = open(ROM, "rb").read()
    fat = struct.unpack_from("<I", rom, 0x48)[0]
    s, e = struct.unpack_from("<II", rom, fat + 4 * 8)
    d = rom[s:e]
    p = CPQ_OFF
    n = struct.unpack_from("<I", d, p + 4)[0]
    offs = [struct.unpack_from("<I", d, p + 8 + 4 * i)[0] for i in range(n)]
    puzzles = []
    for i in range(n):
        r = d[p + offs[i]:p + (offs[i + 1] if i + 1 < n else len(d))]
        if len(r) < 0x2c:
            continue
        w, h = r[0x18], r[0x19]
        if not (4 <= w <= 30 and 4 <= h <= 30):
            continue
        grid = list(r[0x1c:0x1c + w * h])
        digits = [v & 0x7f for v in grid if v != 127 and (v & 0x7f) < 127]
        mx = max(digits) if digits else 0
        tail = list(r[0x1c + w * h:0x1c + w * h + mx])
        mapping = {str(num + 1): (KANA[tail[num]] if tail[num] < len(KANA) else f"?{tail[num]}")
                   for num in range(mx)}
        puzzles.append({
            "rec": i,
            "difficulty_field": struct.unpack_from("<I", r, 4)[0],
            "w": w, "h": h,
            "grid": grid,
            "mapping": mapping,
            "kana_idx": tail,
            "hint_cells": [[y, x, grid[y * w + x] & 0x7f]
                           for y in range(h) for x in range(w) if grid[y * w + x] & 0x80],
        })
    return puzzles


if __name__ == "__main__":
    pz = extract()
    json.dump(pz, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    from collections import Counter
    print("导出:", OUT)
    print("关卡数:", len(pz))
    print("映射长度分布:", dict(sorted(Counter(len(p["mapping"]) for p in pz).items())))
    print("含索引72(墙█)的关:", sum(1 for p in pz if 72 in p["kana_idx"]))
