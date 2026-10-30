#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plans.json 最终瘦身转换器（从 git HEAD 原始 m/k 格式生成最终 M<x>/K 格式）。

原始格式（git HEAD: validation/plans.json）：
  - map   : m<row><col><badge2>   定长5  (badge 为 2 位十进制徽章号)
  - kanji : k<row><col>           定长3
  - 其余  : ^ v < > L R X P Q     单字符
  - 7 条模式2 beam 记录为 list，原样保留

最终格式（本脚本产出）：
  - map   : M<x>    定长2  x = 小写16进制( row*4 + col )，row,col ∈ 0..3 → 0..f
                      例 (3,3) → 3*4+3=15=0xf → "Mf"
  - kanji : K<row><col>  定长3  (仅大小写变化，便于与 M 区分)
  - 其余  : ^ v < > L R X P Q   单字符（不变）
  - beam list：原样保留

徽章号不落盘（执行侧按 rec 的 badge_cells 现场反查）；map 行列压成 1 位 hex。

用法：python3 convert_plans_mk.py
读取源：git show HEAD:validation/plans.json（保证从权威原始格式出发，可复现）
写出：validation/plans.json（UTF-8，紧凑，ensure_ascii=False）
"""
import json
import subprocess
import sys

OUT = "validation/plans.json"


def load_original():
    raw = subprocess.run(
        ["git", "show", "HEAD:validation/plans.json"],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(raw)


def convert_item(x):
    if not isinstance(x, str):
        return x  # None 或 beam list 原样
    out = []
    i = 0
    n = len(x)
    while i < n:
        c = x[i]
        if c == "m":
            row = int(x[i + 1])
            col = int(x[i + 2])
            # badge 两位 x[i+3:i+5] 丢弃
            if not (0 <= row <= 3 and 0 <= col <= 3):
                raise ValueError("map row/col 超范围 0..3: (%d,%d) @ '%s'" % (row, col, x))
            xv = row * 4 + col
            out.append("M%x" % xv)  # 小写 hex (0-f)
            i += 5
        elif c == "k":
            out.append("K" + x[i + 1:i + 3])
            i += 3
        elif c in "^v<>LRXPQ":
            out.append(c)
            i += 1
        else:
            raise ValueError("未知字符 '%s' @ '%s'" % (c, x))
    return "".join(out)


def decode_final(s):
    """把最终串解码成 (kind,row,col,badge) 列表，badge 标记 '<推算>'。"""
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "M":
            xv = int(s[i + 1], 16)
            row, col = xv // 4, xv % 4
            out.append(("map", row, col, "<推算>"))
            i += 2
        elif c == "K":
            out.append(("kanji", int(s[i + 1]), int(s[i + 2]), ""))
            i += 3
        elif c in "^v<>LRXPQ":
            out.append(c)
            i += 1
        else:
            raise ValueError("解码未知字符 '%s'" % c)
    return out


def decode_original(s):
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "m":
            out.append(("map", int(s[i + 1]), int(s[i + 2]), str(int(s[i + 3:i + 5]))))
            i += 5
        elif c == "k":
            out.append(("kanji", int(s[i + 1]), int(s[i + 2]), ""))
            i += 3
        elif c in "^v<>LRXPQ":
            out.append(c)
            i += 1
        else:
            raise ValueError("解码未知字符 '%s'" % c)
    return out


def main():
    orig = load_original()
    new = []
    mismatch = 0
    n_m = 0
    n_k = 0
    n_list = 0
    len_before = 0
    len_after = 0
    for idx, x in enumerate(orig):
        if isinstance(x, list):
            new.append(x)
            n_list += 1
            continue
        if x is None:
            new.append(None)
            continue
        len_before += len(x)
        conv = convert_item(x)
        len_after += len(conv)
        # 语义校验：map 行列一致（徽章忽略），其余逐字节一致
        do = decode_original(x)
        dn = decode_final(conv)
        if len(do) != len(dn):
            mismatch += 1
            print("len mismatch rec", idx)
            continue
        for a, b in zip(do, dn):
            if a == b:
                continue
            if a[0] == "map" and b[0] == "map" and a[1:3] == b[1:3]:
                continue
            mismatch += 1
            print("step mismatch rec", idx, a, b)
            break
        if conv and conv[0] == "M":
            n_m += conv.count("M")
        n_k += conv.count("K")
        new.append(conv)

    if mismatch:
        print("!!! 语义校验失败 %d 条，中止写出" % mismatch)
        sys.exit(1)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(new, f, ensure_ascii=False, separators=(",", ":"))

    import os
    size = os.path.getsize(OUT)
    print("OK 写出 %s" % OUT)
    print("  非空项(字符串):", sum(1 for x in new if isinstance(x, str)))
    print("  beam list:", n_list)
    print("  M(map) 操作数:", n_m, " K(kanji) 操作数:", n_k)
    print("  原始总长:", len_before, " → 最终总长:", len_after)
    print("  文件体积:", size, "B")


if __name__ == "__main__":
    main()
