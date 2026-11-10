#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.05 数回：从「实机题面」反解题面文件与答案文件（已知明文检索）。

这一步回答的问题是：*如果只给你实机屏幕上看到的一道题（线索数字盘），
怎么把 ROM 里对应的题面记录和答案记录挖出来？*

思路（已知明文攻击，不依赖求解器、不逆运行时内存）：

  1. 实机题面 = w×h 的线索盘，逐格 0/1/2/3 或空白。把空白记作 4，
     得到 w·h 个字节，这就是一段**已知明文**。
  2. ROM 的 `indata/add01dat.bin` 是通用 pack：开头 u32 偏移表（1704 项），
     题库区是偏移表 idx 1395..1702 的 308 条定长记录。
  3. 逐条比对记录 `[2 : 2+w·h]` 与这段已知明文；命中即定位到题目记录。
  4. 由记录长度恒等式 `2 + 2·w·h + 26 == len(record)` 拆出后半段
     `[2+w·h : 2+2·w·h]`，即**答案掩码**（每格环内=1 / 环外=0）。
  5. 掩码的内外分界线还原环路，再用「线索全满足 + 格点度数∈{0,2}
     + 恰好一个连通环」自洽校验。

也就是说：**答案是题面记录在文件里的后半段**，不需要实机通关、不需要求
解，题面本身就是定位答案的钥匙。

用法：
  # 自检：用 puzzles.json 全部 308 题的题面去反解，验证答案逐题一致
  python3 validation/reverse_from_clues.py --self-test

  # 演示：挑 6x6 / 10x10 / 36x20 各一题，打印反解全过程
  python3 validation/reverse_from_clues.py --demo

  # 从 puzzles.json 取第 N 题的题面当作「实机题面」输入
  python3 validation/reverse_from_clues.py --from-json 0

  # 直接喂实机屏幕抄录的线索盘（每行等长，. = 空格，0-3 = 线索）
  python3 validation/reverse_from_clues.py --clue-grid \\
      '......' '.2112.' '.1..1.' '.2112.' '......' '......'

  # pack 原始字节不入库；默认先读 validation/vol5_pack.bin，
  # 没有就从 ROM 重新提取，也可用 --pack / --rom 指定
  python3 validation/reverse_from_clues.py --demo --pack /path/to/vol5_pack.bin
"""
import argparse
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PARENT = os.path.dirname(HERE)
sys.path.insert(0, PARENT)
import extract_vol5_answers as E          # 复用 extract_pack / loop_edges / verify / draw_loop

PACK_DEFAULT = os.path.join(HERE, "vol5_pack.bin")
JSON_PATH = os.path.join(HERE, "puzzles.json")


def load_pack(pack=None, rom=None):
    """pack 原始字节不入库；优先本地文件，其次从 ROM 的 NitroFS 现解。"""
    path = pack or PACK_DEFAULT
    if os.path.exists(path):
        return open(path, "rb").read(), path
    d = E.extract_pack(rom or E.DEFAULT_ROM)
    return d, "<从 ROM 现场提取>"


def records(d):
    """只按偏移表切记录，不做答案自洽校验——反解阶段不能先假定答案正确。"""
    first = struct.unpack_from("<I", d, 0)[0]
    n = first // 4
    offs = list(struct.unpack_from("<%dI" % n, d, 0)) + [len(d)]
    out = []
    for i in range(E.IDX_START, min(E.IDX_END, n)):
        out.append((i, d[offs[i]:offs[i + 1]]))
    return out


def grid_to_clues(lines):
    """把 '.2112.' 这样的字符盘转成 w,h,clues 字节序列（空白=4）。"""
    lines = [l.strip() for l in lines if l.strip()]
    if not lines:
        raise ValueError("题面为空")
    w = len(lines[0])
    if any(len(l) != w for l in lines):
        raise ValueError("题面每行长度必须一致")
    clues = []
    for line in lines:
        for ch in line:
            if ch == ".":
                clues.append(4)
            elif ch in "0123":
                clues.append(int(ch))
            else:
                raise ValueError("非法字符 %r：只允许 0-3 和 ." % ch)
    return w, len(lines), clues


def clues_to_grid(w, h, clues):
    return ["".join("." if clues[r * w + c] == 4 else str(clues[r * w + c])
                    for c in range(w)) for r in range(h)]


def search(d, w, h, clues):
    """已知明文检索：返回所有题面完全匹配的 (idx, record)。"""
    cells = w * h
    expected = 2 + 2 * cells + E.TAIL_LEN
    hits = []
    for idx, raw in records(d):
        if len(raw) != expected or raw[0] != w or raw[1] != h:
            continue
        if list(raw[2:2 + cells]) == clues:
            hits.append((idx, raw))
    return hits


def reverse_one(d, w, h, clues, label=""):
    """反解一题：打印题面层 -> 答案层 -> 环路 -> 自洽校验。"""
    cells = w * h
    hits = search(d, w, h, clues)
    print("=" * 68)
    print("输入题面 %s  %dx%d  共 %d 格" % (label, w, h, cells))
    for line in clues_to_grid(w, h, clues):
        print("  " + line)
    if not hits:
        print("结果：无匹配记录（题面抄录有误，或尺寸不属于 5 档白名单）")
        return []
    print("命中 %d 条题库记录：" % len(hits))
    results = []
    for idx, raw in hits:
        mask = list(raw[2 + cells:2 + 2 * cells])
        tail = raw[2 + 2 * cells:]
        he, ve = E.loop_edges(w, h, mask)
        bad, degbad, comps = E.verify(w, h, clues, he, ve)
        assert len(raw) == 2 + 2 * cells + E.TAIL_LEN
        print("-" * 68)
        print("  pack 偏移表 idx = %d   记录长度 = %d B" % (idx, len(raw)))
        print("  长度恒等式  2 + 2·%d·%d + 26 = %d  ✓" % (w, h, len(raw)))
        print("  题面层 [2:%d]        = 输入题面（逐格一致）" % (2 + cells))
        print("  答案层 [%d:%d]  = 每格环内/环外掩码：" % (2 + cells, 2 + 2 * cells))
        for line in ["".join(str(mask[r * w + c]) for c in range(w)) for r in range(h)]:
            print("    " + line)
        print("  图形元数据尾   = %s...（%d B）" % (tail[:8].hex(), len(tail)))
        print("  还原环路：水平边 %d 条 / 垂直边 %d 条，共 %d 条"
              % (len(he), len(ve), len(he) + len(ve)))
        for line in E.draw_loop(w, h, he, ve):
            print("    " + line)
        print("  自洽校验：线索违例 %d / 度数违例 %d / 连通分量 %d  -> %s"
              % (bad, degbad, comps, "通过" if (bad == 0 and degbad == 0 and comps == 1) else "不通过"))
        results.append({"idx": idx, "answer_mask": mask,
                        "edges_h": he, "edges_v": ve,
                        "bad": bad, "degbad": degbad, "comps": comps})
    return results


def self_test(d):
    """全量验证：每道题的题面都能反解出与 puzzles.json 完全一致的答案。"""
    puzzles = json.load(open(JSON_PATH, encoding="utf-8"))
    hit = uniq = consistent = passed = 0
    missing, mismatch = [], []
    for p in puzzles:
        hits = search(d, p["w"], p["h"], p["clues"])
        if not hits:
            missing.append(p["idx"])
            continue
        hit += 1
        if len(hits) == 1:
            uniq += 1
        cells = p["cells"]
        masks = [list(raw[2 + cells:2 + 2 * cells]) for _, raw in hits]
        if p["answer_mask"] in masks:
            consistent += 1
        else:
            mismatch.append(p["idx"])
        for idx, raw in hits:
            mask = list(raw[2 + cells:2 + 2 * cells])
            he, ve = E.loop_edges(p["w"], p["h"], mask)
            bad, degbad, comps = E.verify(p["w"], p["h"], p["clues"], he, ve)
            if bad == 0 and degbad == 0 and comps == 1:
                passed += 1
                break
    print("=" * 68)
    print("全量自检：题面 -> 反解答案（共 %d 题）" % len(puzzles))
    print("  题面命中记录            : %d / %d" % (hit, len(puzzles)))
    print("  其中唯一命中            : %d" % uniq)
    print("  反解答案与题库逐格一致  : %d / %d" % (consistent, len(puzzles)))
    print("  反解环路自洽(线索/度数/单环): %d / %d" % (passed, len(puzzles)))
    if missing:
        print("  未命中 idx :", missing)
    if mismatch:
        print("  答案不一致 idx :", mismatch)
    ok = hit == len(puzzles) and consistent == len(puzzles)
    print("  结论：", "链路 100% 通 —— 题面即答案的钥匙" if ok else "存在不一致，需复查")
    return ok


def main():
    ap = argparse.ArgumentParser(description="从实机题面反解 Vol.05 数回的题面/答案文件")
    ap.add_argument("--pack", help="pack 原始字节路径（默认 validation/vol5_pack.bin）")
    ap.add_argument("--rom", help="ROM 路径（pack 不存在时从其 NitroFS 现解）")
    ap.add_argument("--self-test", action="store_true", help="全量自检 308 题")
    ap.add_argument("--demo", action="store_true", help="演示 6x6 / 10x10 / 36x20 各一题")
    ap.add_argument("--from-json", type=int, metavar="N", help="取 puzzles.json 第 N 题的题面作输入")
    ap.add_argument("--clue-grid", nargs="+", metavar="ROW", help="实机屏幕抄录的线索盘，每行等长，. 表空格")
    args = ap.parse_args()

    d, src = load_pack(args.pack, args.rom)
    print("pack 来源：%s   大小 %d B" % (src, len(d)))

    if args.self_test:
        sys.exit(0 if self_test(d) else 1)

    if args.demo:
        puzzles = json.load(open(JSON_PATH, encoding="utf-8"))
        by_dim = {}
        for p in puzzles:
            by_dim.setdefault((p["w"], p["h"]), p)
        for dim in [(6, 6), (10, 10), (36, 20)]:
            p = by_dim.get(dim)
            if not p:
                print("缺少尺寸", dim)
                continue
            r = reverse_one(d, p["w"], p["h"], p["clues"], "(demo idx%d)" % p["idx"])
            if r:
                print("  与题库答案一致：", any(x["answer_mask"] == p["answer_mask"] for x in r))
        return

    if args.from_json is not None:
        p = json.load(open(JSON_PATH, encoding="utf-8"))[args.from_json]
        reverse_one(d, p["w"], p["h"], p["clues"], "(puzzles.json[%d] idx%d)" % (args.from_json, p["idx"]))
        return

    if args.clue_grid:
        w, h, clues = grid_to_clues(args.clue_grid)
        reverse_one(d, w, h, clues, "(实机屏幕抄录)")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
