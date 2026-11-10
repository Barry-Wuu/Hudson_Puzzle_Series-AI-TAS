#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《解谜系列Vol.5：数回》全关卡答案（答案格字符矩阵版）。

参照《解谜系列Vol.11：数墙》答案.md 的版式：每关一个紧凑字符矩阵，
放在代码块里用等宽字体渲染，行列对齐。

字符约定（每格恰好 1 个字符，**只表示答案格，不单独表示边**）：
    □            回路外格、无线索
    █            回路内格、无线索
    ⓪ ① ② ③     回路【外】的线索数字 0/1/2/3（白底带圈）
    ⓿ ❶ ❷ ❸     回路【内】的线索数字 0/1/2/3（黑底反白带圈 = 黑色版）

`█` 与 `□` 的分界线即官方环路。数据来自 validation/puzzles.json：
  clue_grid    -> 题面线索（'.'=空格，0-3=数字）
  answer_mask  -> 每格环内=1 / 环外=0

共 306 道正式题有答案盘面；idx1400 / idx1401 是空白占位记录，
ROM 答案层全 0（idx1401 是教程练习盘），文末附录单列，不渲染误导性的全 □ 矩阵。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'validation', 'puzzles.json')
DST = os.path.join(HERE, '答案.md')

# 回路外 / 回路内的带圈数字（索引 0..3 对应线索数字 0..3）
OUTER = ['⓪', '①', '②', '③']   # U+24EA / U+2460..2462
INNER = ['⓿', '❶', '❷', '❸']   # U+24FF / U+2776..2778（黑底反白 = 黑色版）
BLANK_OUT = '□'                 # U+25A1 回路外空格
BLANK_IN = '█'                  # U+2588 回路内空格

SIZE_ORDER = [(6, 6), (10, 10), (18, 10), (24, 14), (36, 20)]
VALID = set(OUTER + INNER + [BLANK_OUT, BLANK_IN])


def cell_text(clue_ch, mask):
    """单格字符：有线索用带圈数字（按内外分黑白版），无线索用 □/█。"""
    if clue_ch in '0123':
        return (INNER if mask == 1 else OUTER)[int(clue_ch)]
    return BLANK_IN if mask == 1 else BLANK_OUT


def render(p):
    """渲染一关为 h 行 × w 列的字符矩阵（代码块围栏）。"""
    w, h = p['w'], p['h']
    clue = p['clue_grid']
    mask = p['answer_mask']
    if isinstance(clue, str):
        clue = clue.splitlines()
    assert len(clue) == h and all(len(r) == w for r in clue), p['idx']
    assert len(mask) == w * h, p['idx']
    lines = ['```']
    for r in range(h):
        lines.append(''.join(cell_text(clue[r][c], mask[r * w + c])
                             for c in range(w)))
    lines.append('```')
    return '\n'.join(lines)


def self_check(data, text):
    """生成结果回读自检：覆盖数、行列数、字符集、以及反向还原 clay/mask 一致。"""
    official = [p for p in data if not p.get('blank')]
    blanks = [p for p in data if p.get('blank')]
    assert len(official) == 306 and len(blanks) == 2, (len(official), len(blanks))
    assert set((p['w'], p['h']) for p in data) == set(SIZE_ORDER)

    # 文档里出现的每一关矩阵都能反解回原始 clue + mask
    for p in official:
        w, h = p['w'], p['h']
        clue = p['clue_grid'] if isinstance(p['clue_grid'], list) else p['clue_grid'].splitlines()
        mask = p['answer_mask']
        for r in range(h):
            row = ''.join(cell_text(clue[r][c], mask[r * w + c]) for c in range(w))
            assert len(row) == w
            assert set(row) <= VALID
            # 反解：黑底圈/█ -> mask=1；白底圈/□ -> mask=0
            for c, ch in enumerate(row):
                m = 1 if (ch == BLANK_IN or ch in INNER) else 0
                assert m == mask[r * w + c], (p['idx'], r, c, ch)
                if ch in OUTER or ch in INNER:
                    n = (OUTER + INNER).index(ch) % 4
                    assert clue[r][c] == str(n), (p['idx'], r, c, ch)

    n_mat = text.count('```') // 2
    assert n_mat == 306, n_mat
    assert 'idx1400' in text and 'idx1401' in text
    print('自检通过：306 题全部渲染、逐格可反解回 clue/mask；附录含 2 条空白占位')
    return len(official), len(blanks)


def main():
    data = json.load(open(SRC, encoding='utf-8'))
    by_size = {}
    for p in data:
        by_size.setdefault((p['w'], p['h']), []).append(p)
    for k in by_size:
        by_size[k].sort(key=lambda p: p['idx'])

    official = [p for p in data if not p.get('blank')]
    blanks = sorted((p for p in data if p.get('blank')), key=lambda p: p['idx'])

    out = []
    out.append('# 《解谜系列Vol.5：数回》全关卡答案（官方答案盘面）')
    out.append('')
    out.append('> 📌 **阅读提示**：每关盘面都放在**代码块**里，网页与手机端预览都会按等宽字体渲染，')
    out.append('> 行列对齐、无需切换「源码模式」。')
    out.append('>')
    out.append('> **图例（每格 1 个字符；只表示答案格，不单独表示边）**')
    out.append('>')
    out.append('> | 字符 | 含义 |')
    out.append('> |---|---|')
    out.append('> | `□` | 回路**外**格（无线索） |')
    out.append('> | `█` | 回路**内**格（无线索） |')
    out.append('> | `⓪` `①` `②` `③` | 回路**外**的线索数字 0/1/2/3（白底带圈） |')
    out.append('> | `⓿` `❶` `❷` `❸` | 回路**内**的线索数字 0/1/2/3（黑底反白＝黑色版） |')
    out.append('>')
    out.append('> **`█` 与 `□` 的分界线就是官方环路**：掩码里环内=1、环外=0，')
    out.append('> 水平边 `H[r][c] ⟺ mask[r-1][c]≠mask[r][c]`、垂直边 `V[r][c] ⟺ mask[r][c-1]≠mask[r][c]`。')
    out.append('> 答案盘面直接取自 ROM 记录的 `[2+w·h : 2+2·w·h]` 段，逐题已通过')
    out.append('> 「线索逐格满足 + 格点度数 ∈{0,2} + 恰好一个连通环」三重校验（**306/306**）。')
    out.append('>')
    out.append('> 题目按 **pack 偏移表索引（idx）升序**分章；`idx` 是 ROM 记录号，')
    out.append('> **不是**游戏内难度／关号（本库未解码难度归属，不臆测）。标题里的 `#N` 只是本文档内的顺序号。')
    out.append('> 共 **306 题**有官方答案盘面；另有 2 条空白占位记录无答案，见文末附录。')
    out.append('')

    for size in SIZE_ORDER:
        items = [p for p in by_size[size] if not p.get('blank')]
        out.append(f'## {size[0]}×{size[1]}（{len(items)} 关）')
        out.append('')
        for n, p in enumerate(items, 1):
            out.append(f'**#{n:02d} · pack idx {p["idx"]}（{p["w"]}×{p["h"]}）**')
            out.append(render(p))
            out.append('')

    out.append('## 附录：2 条空白占位记录（ROM 无答案盘面，不渲染矩阵）')
    out.append('')
    out.append('> 这两条不是正式关卡，答案层全 0，若渲染成全 `□` 会误导成「整盘都在环外」，')
    out.append('> 因此只登记不画盘面。')
    out.append('')
    out.append('| pack idx | 尺寸 | 情况 |')
    out.append('|---|---|---|')
    out.append('| `idx1400` | 6×6 | 线索盘全空、答案掩码全 0，纯占位 |')
    out.append('| `idx1401` | 6×6 | 教程练习盘：有线索，但 ROM 答案层全 0（环是教程里现画的，不在题库记录里） |')
    out.append('')
    out.append('> 全库 308 条记录 = 306 道正式题 + 这 2 条占位。')
    out.append('> 题面层仍可读（308/308），实机第 1 問 `idx1403` / 第 2 問 `idx1404` 已与屏幕逐格对上。')
    out.append('')

    text = '\n'.join(out).rstrip() + '\n'
    self_check(data, text)
    with open(DST, 'w', encoding='utf-8') as f:
        f.write(text)
    print('已写出', DST, len(text.encode('utf-8')), 'bytes',
          '%.1f KB' % (len(text.encode('utf-8')) / 1024))


if __name__ == '__main__':
    main()
