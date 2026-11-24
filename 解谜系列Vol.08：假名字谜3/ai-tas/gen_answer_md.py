#!/usr/bin/env python3.11
"""从 answers_full.json 生成仿 vol13《答案.md》格式的填字答案。

- 假名直接落到数字格位置,片假名,无映射表
- █ = 墙/黑格(含 grid 值127, 以及 mapping 标记为 █ 的索引72格)
- 索引72 实机词条验证为墙(非促音): 当ッ满屏乱码, 当墙横竖成词
"""
import json

BASE = "/workspace/hudson_tas/解谜系列Vol.08：假名字谜3/"
d = json.load(open(BASE + "answers_full.json", encoding="utf-8"))
H = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんがぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽー"
K = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポー"
KATA = dict(zip(H, K))


def cell(v, mapping):
    if v == 127:
        return "█"
    ch = mapping.get(str(v & 0x7f), "?")
    return "█" if ch == "█" else KATA.get(ch, ch)


diff_name = {0: "ヤサシイ（易）", 1: "フツウ（中）", 2: "ムズカシイ（难）",
             3: "認定 ブロンズ", 4: "認定 シルバー", 5: "認定 ゴールド", 6: "認定 プラチナ"}

out = []
out.append("# 《解谜系列Vol.08：假名字谜3》全关卡答案（填字答案）\n")
out.append("> 📌 **阅读提示**：每关盘面都放在**代码块**里，网页与手机端预览都会按等宽字体渲染，行列对齐、无需切换「源码模式」。\n")
out.append("> 说明：以下每关答案均为**已填好假名**的盘面，采用**紧凑矩阵**排版——行内假名之间没有空格，行与行之间也没有空行。盘面上的片假名即该格应填的字（游戏里按五十音键盘输入对应假名即可）。\n")
out.append("> 盘面中的 **█**（全角实心方块）表示墙/黑格，即原盘不可填写的格子；其余位置均为答案假名。\n")
out.append("> 全文假名一律采用**片假名**（与游戏键盘一致）；答案由 ROM 题库数字密码解出后**直接落到数字位置**，不附任何映射表。\n")
out.append("> 关卡顺序依题库记录号（rec）：通常問題 易→中→难，随后認定問題四级；每关标题标注「第N关 / rec / 尺寸」。\n")
out.append("> ⚠️ 题库索引 72 经实机词条验证为**墙**（非促音）：当假名「ッ」时满屏乱码，当墙时横竖词条全部成词（セクハラ/ネクタイ/コオロギ 等）；涉及 10 关，已按 █ 落位。\n")
out.append("\n---\n")
cur = None
for i, p in enumerate(d):
    fld = p["difficulty_field"]
    if fld != cur:
        cur = fld
        out.append("\n## %s\n" % diff_name.get(fld, "难度字段%d" % fld))
    w, h, m = p["w"], p["h"], p["mapping"]
    out.append("\n**第%03d关 rec%d（%d×%d）**\n" % (i + 1, p["rec"], w, h))
    out.append("```")
    for y in range(h):
        out.append("".join(cell(p["grid"][y * w + x], m) for x in range(w)))
    out.append("```")
open(BASE + "答案.md", "w", encoding="utf-8").write("\n".join(out) + "\n")
print("生成 答案.md, 行数:", len(out))
