#!/usr/bin/env python3.11
"""Vol.08 假名字谜3 自动填字/通关。

核心机制（2026-11-20 第三轮最终确认，见标定报告第七节）：
  - 点数字格选中该数字 → 点对应假名键 2 次填入。
  - 连续点不同假名会互相覆盖，必须逐数字"选格+填"。
  - 盘面格坐标 (24+26c, 19+26r)，下屏仅显 6×4 放大镜（视口滚动待解决）。
  - 旧版"直接点假名键全局替换"过于简化，已纠正。
  - 促音「っ」不存在（ROM 索引71=长音「ー」）。

键盘：15 列 x 5 行五十音图，公式 x=15+16*col, y=119+16*row。
  第9列 = ン(row1)/ー(row2)，第10列起浊音，第14列半浊音。
"""
import sys, json, time
import ds

ANS = "/workspace/hudson_tas/解谜系列Vol.08：假名字谜3/answers.json"

# 键盘网格 (片假名) → (col,row)
GRID = [
    ["ア","カ","サ","タ","ナ","ハ","マ","ヤ","ラ","ワ","ガ","ザ","ダ","バ","パ"],
    ["イ","キ","シ","チ","ニ","ヒ","ミ","ユ","リ","ン","ギ","ジ","ヂ","ビ","ピ"],
    ["ウ","ク","ス","ツ","ヌ","フ","ム","ヨ","ル","ー","グ","ズ","ヅ","ブ","プ"],
    ["エ","ケ","セ","テ","ネ","ヘ","メ",None,"レ",None,"ゲ","ゼ","デ","ベ","ペ"],
    ["オ","コ","ソ","ト","ノ","ホ","モ",None,"ロ",None,"ゴ","ゾ","ド","ボ","ポ"],
]
KANA_POS = {}
for r, row in enumerate(GRID):
    for c, k in enumerate(row):
        if k: KANA_POS[k] = (15 + 16*c, 119 + 16*r)

HIRA2KATA = {}
_h = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんがぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽー"
_k = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポー"
for a, b in zip(_h, _k): HIRA2KATA[a] = b


def tap_kana(kana, twice=True, hold=0.08, after=0.35, gap=0.04):
    kk = HIRA2KATA.get(kana, kana)
    pos = KANA_POS.get(kk)
    if not pos:
        return False, kk, None
    x, y = pos
    ds.tap(x, y, hold=hold, after=after, gap=gap)
    if twice:
        ds.tap(x, y, hold=hold, after=after, gap=gap)
    return True, kk, pos


def solve(question, check_btn=None, twice=True):
    """填第 question 关 (1-based)。返回 (ok, 未定位假名列表)。"""
    data = json.load(open(ANS, encoding='utf-8'))
    p = data[question - 1]
    mapping = p['mapping']  # {'1':'は',...}
    # 只填盘面实际出现的数字
    used = sorted(set(v & 0x7f for v in p['grid'] if (v & 0x7f) in range(1, 17)))
    missing = []
    print(f"第{question:03d}問 {p['w']}x{p['h']} 填{len(used)}个数字", flush=True)
    for num in used:
        kana = mapping[str(num)]
        ok, kk, pos = tap_kana(kana, twice=twice)
        if not ok:
            missing.append((num, kana, kk))
            print(f"  !! 数字{num}={kana}({kk}) 无键位", flush=True)
        else:
            print(f"  {num:2d}={kana}({kk})@{pos}", flush=True)
    ds.grab(f'solve_{question:03d}_filled')
    if check_btn:
        ds.tap(*check_btn, hold=0.1, after=1.5)
        ds.grab(f'solve_{question:03d}_checked')
    return missing


if __name__ == '__main__':
    ds.start()
    q = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    twice = not ('--once' in sys.argv)
    miss = solve(q, twice=twice)
    print('missing:', miss, flush=True)
