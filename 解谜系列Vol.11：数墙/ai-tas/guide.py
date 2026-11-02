#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""照抄攻略：从《答案.md》（官方答案盘面）解析每关黑格坐标，去除求解器。

答案.md 由 validation/puzzles.json 生成，盘面字符约定：
  █ (U+2588) = 墙（要涂黑的格子）
  □ (U+25A1) / 全角空格 　 / 带圈数字  = 白格（不涂）
每关一个矩阵，行列与题目尺寸一致，r 自上而下、c 自左而右（0-based）。

本模块只做「答案查表」，不识别谜面、不调用任何求解算法。
启动时用 puzzles.json 对每关黑格集合做一致性断言，双重保险。
"""
import os
import re
import json

HERE = os.path.dirname(os.path.abspath(__file__))
GUIDE = os.path.join(HERE, "..", "答案.md")
PUZZLES = os.path.join(HERE, "..", "validation", "puzzles.json")
BLACK = "█"  # U+2588

_REC_TITLE = re.compile(
    r"###\s*第(\d+)問\s*rec(\d+)\s*（(\d+)×(\d+)）\s*\n"
    r"((?:[^\n]*\n)+?)(?=###|\Z)"
)


def _parse_guide_md():
    """返回 {diff: {rec: set((r,c))}} 黑格坐标集合。"""
    text = open(GUIDE, encoding="utf-8").read()
    parts = re.split(r"^##\s+(.+)$", text, flags=re.M)
    result = {}
    for i in range(1, len(parts), 2):
        diff = parts[i].strip()
        body = parts[i + 1]
        recs = {}
        for m in _REC_TITLE.finditer(body):
            rec = int(m.group(2))
            h = int(m.group(4))
            mat = m.group(5).rstrip("\n").split("\n")
            blacks = set()
            for r, line in enumerate(mat):
                for c, ch in enumerate(line):
                    if ch == BLACK:
                        blacks.add((r, c))
            recs[rec] = blacks
        result[diff] = recs
    return result


def load_answers(diff="入門"):
    """返回 {rec: sorted[(r,c)...]} 黑格坐标，并断言与 puzzles.json 完全一致。"""
    guide = _parse_guide_md()
    puz = json.load(open(PUZZLES, encoding="utf-8"))[diff]
    out = {}
    for p in puz:
        rec = p["rec"]
        w, h = p["w"], p["h"]
        blacks_puz = set(
            (r, c) for r in range(h) for c in range(w)
            if p["wall"][r * w + c] == 1
        )
        blacks_guide = guide[diff].get(rec, set())
        if blacks_puz != blacks_guide:
            diff_cells = blacks_puz ^ blacks_guide
            raise AssertionError(
                f"答案.md 与 puzzles.json 在 rec{rec} 不一致: {diff_cells}"
            )
        out[rec] = sorted(blacks_puz)
    return out


if __name__ == "__main__":
    for d in ("入門", "やさしい", "ふつう", "むずかしい"):
        ans = load_answers(d)
        print(f"{d}: {len(ans)} 关, 黑格数示例 rec1={len(ans[1])}")
    print("✅ 答案.md 与 puzzles.json 全部一致")
