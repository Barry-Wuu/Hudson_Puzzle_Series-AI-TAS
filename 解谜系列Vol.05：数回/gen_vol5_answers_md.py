#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成《解谜系列Vol.5：数回》全关卡答案（答案格字符矩阵版）。

参照《解谜系列Vol.11：数墙》答案.md 的版式：每关一个紧凑字符矩阵，
放在代码块里用等宽字体渲染，行列对齐。

分章口径（2026-11-10 实机标定，非臆测）：
  - 难度选择页 4 档：入門 / やさしい / ふつう / むずかしい；
    选关页下屏「クリア数」分母依次为 020 / 100 / 100 / 050 = 270 关。
  - ROM pack 题库 idx1403..1672 恰好 270 条连续记录，按 idx 升序即关卡顺序，
    连续切分为 20 / 100 / 100 / 50；4 个难度首关预览尺寸实测
    6x6 / 10x10 / 18x10 / 24x14，与切分点逐项吻合。
  - 一级按难度分章，章内按尺寸分节（对齐数墙「难度 · 尺寸」格式），
    另附「按尺寸速查」表；余下 36 道不在选关页内的记录单列附录 A。

字符约定（每格恰好 1 个字符，**只表示答案格，不单独表示边**）：
    ○            回路外格、无线索
    ●            回路内格、无线索
    ⓪ ① ② ③     回路【外】的线索数字 0/1/2/3（白底带圈）
    ⓿ ❶ ❷ ❸     回路【内】的线索数字 0/1/2/3（黑底反白带圈 = 黑色版）

`●` 与 `○` 的分界线即官方环路。数据来自 validation/puzzles.json：
  clue_grid    -> 题面线索（'.'=空格，0-3=数字）
  answer_mask  -> 每格环内=1 / 环外=0

共 306 道正式题有答案盘面；idx1400 / idx1401 是空白占位记录，
ROM 答案层全 0（idx1401 是教程练习盘），附录 B 单列，不渲染误导性的全 ○ 矩阵。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'validation', 'puzzles.json')
DST = os.path.join(HERE, '答案.md')

# 回路外 / 回路内的带圈数字（索引 0..3 对应线索数字 0..3）
OUTER = ['⓪', '①', '②', '③']   # U+24EA / U+2460..2462
INNER = ['⓿', '❶', '❷', '❸']   # U+24FF / U+2776..2778（黑底反白 = 黑色版）
BLANK_OUT = '○'                 # U+25CB WHITE CIRCLE（回路外空格）
BLANK_IN = '●'                  # U+25CF BLACK CIRCLE（回路内空格）
# 两者 EAW=A，中文等宽字体下满宽 1ch，与 ①/❶ 的圆圈同大小；
# 方块 □(U+25A1)/█(U+2588) 混在圆里视觉突兀，已弃用。

SIZE_ORDER = [(6, 6), (10, 10), (18, 10), (24, 14), (36, 20)]
VALID = set(OUTER + INNER + [BLANK_OUT, BLANK_IN])

# (难度名, 关数, 起始 pack idx, 实机选关页分母)
DIFFS = [
    ('入門',       20, 1403, '020'),
    ('やさしい',  100, 1423, '100'),
    ('ふつう',    100, 1523, '100'),
    ('むずかしい', 50, 1623, '050'),
]
CN_NUM = ['一', '二', '三', '四']
MAIN_START, MAIN_END = 1403, 1672


def cell_text(clue_ch, mask):
    """单格字符：有线索用带圈数字（按内外分黑白版），无线索用 ○/●。"""
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


def classify(data):
    """把 308 条记录分成 4 个难度关卡 / 附录 A 额外题 / 附录 B 空白占位。"""
    diff_items, extra, blanks = {}, [], []
    for p in data:
        if p.get('blank'):
            blanks.append(p)
            continue
        idx = p['idx']
        hit = None
        for i, (name, count, start, _den) in enumerate(DIFFS):
            if start <= idx < start + count:
                hit = (i, idx - start + 1)   # (难度序号, 该难度内第 N 問)
                break
        if MAIN_START <= idx <= MAIN_END and hit is not None:
            diff_items.setdefault(hit[0], []).append((hit[1], p))
        else:
            extra.append(p)
    for i in diff_items:
        diff_items[i].sort(key=lambda t: t[0])
    extra.sort(key=lambda p: p['idx'])
    blanks.sort(key=lambda p: p['idx'])
    return diff_items, extra, blanks


def self_check(data, text, diff_items, extra, blanks):
    """生成结果回读自检：覆盖数、行列数、字符集、反解一致、难度分章口径。"""
    official = [p for p in data if not p.get('blank')]
    assert len(official) == 306 and len(blanks) == 2, (len(official), len(blanks))
    assert set((p['w'], p['h']) for p in data) == set(SIZE_ORDER)

    # 难度分章口径硬校验（防止改动后悄悄跑偏）
    assert sum(c for _n, c, _s, _d in DIFFS) == 270
    assert MAIN_END - MAIN_START + 1 == 270
    for i, (name, count, start, den) in enumerate(DIFFS):
        items = diff_items[i]
        assert len(items) == count, (name, len(items), count)
        assert items[0][0] == 1 and items[-1][0] == count, name
        assert items[0][1]['idx'] == start, (name, items[0][1]['idx'], start)
        assert [n for n, _p in items] == list(range(1, count + 1)), name
    assert len(extra) == 36, len(extra)
    assert sum(len(diff_items[i]) for i in diff_items) + len(extra) == 306

    # 文档里出现的每一关矩阵都能反解回原始 clue + mask
    for p in official:
        w, h = p['w'], p['h']
        clue = p['clue_grid'] if isinstance(p['clue_grid'], list) else p['clue_grid'].splitlines()
        mask = p['answer_mask']
        for r in range(h):
            row = ''.join(cell_text(clue[r][c], mask[r * w + c]) for c in range(w))
            assert len(row) == w
            assert set(row) <= VALID
            # 反解：黑底圈/● -> mask=1；白底圈/○ -> mask=0
            for c, ch in enumerate(row):
                m = 1 if (ch == BLANK_IN or ch in INNER) else 0
                assert m == mask[r * w + c], (p['idx'], r, c, ch)
                if ch in OUTER or ch in INNER:
                    n = (OUTER + INNER).index(ch) % 4
                    assert clue[r][c] == str(n), (p['idx'], r, c, ch)

    n_mat = text.count('```') // 2
    assert n_mat == 306, n_mat
    assert 'idx1400' in text and 'idx1401' in text
    for i, (name, count, start, den) in enumerate(DIFFS):
        assert f'## {CN_NUM[i]}、{name}（{count} 关）' in text
    print('自检通过：306 题全部渲染、逐格可反解回 clue/mask；'
          '4 难度 20/100/100/50 分章口径正确；附录 A 36 题、附录 B 2 条占位')
    return len(official), len(blanks)


def main():
    data = json.load(open(SRC, encoding='utf-8'))
    diff_items, extra, blanks = classify(data)

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
    out.append('> | `○` | 回路**外**格（无线索） |')
    out.append('> | `●` | 回路**内**格（无线索） |')
    out.append('> | `⓪` `①` `②` `③` | 回路**外**的线索数字 0/1/2/3（白底带圈） |')
    out.append('> | `⓿` `❶` `❷` `❸` | 回路**内**的线索数字 0/1/2/3（黑底反白＝黑色版） |')
    out.append('>')
    out.append('> `○`(U+25CB) / `●`(U+25CF) 与带圈数字同为 **EAW=A**，中文等宽字体下正好')
    out.append('> **满宽 1ch**，圆圈大小与 `①` / `❶` 一致，整盘统一为圆形语汇；')
    out.append('> 方块 `□`(U+25A1) / `█`(U+2588) 混在圆里视觉突兀，已弃用。')
    out.append('>')
    out.append('> **`●` 与 `○` 的分界线就是官方环路**：掩码里环内=1、环外=0，')
    out.append('> 水平边 `H[r][c] ⟺ mask[r-1][c]≠mask[r][c]`、垂直边 `V[r][c] ⟺ mask[r][c-1]≠mask[r][c]`。')
    out.append('> 答案盘面直接取自 ROM 记录的 `[2+w·h : 2+2·w·h]` 段，逐题已通过')
    out.append('> 「线索逐格满足 + 格点度数 ∈{0,2} + 恰好一个连通环」三重校验（**306/306**）。')
    out.append('>')
    out.append('> **分章口径（2026-11-10 实机标定，非臆测）**')
    out.append('>')
    out.append('> - 游戏难度选择页 4 档：**入門 / やさしい / ふつう / むずかしい**；')
    out.append('>   选关页下屏 `クリア数` 分母依次为 `020 / 100 / 100 / 050`，合计 **270 关**。')
    out.append('> - ROM pack 题库 `idx1403..1672` 恰好 **270 条**连续记录；按 `idx` 升序即关卡顺序，')
    out.append('>   连续切分为 20 / 100 / 100 / 50。四个难度**首关预览尺寸**实测')
    out.append('>   `6x6 / 10x10 / 18x10 / 24x14`，与切分点逐项吻合；')
    out.append('>   入門第 1 問 `idx1403`、第 2 問 `idx1404` 已与实机屏幕逐格对上')
    out.append('>   （`validation/reverse_from_clues.py` 反解闭环）。')
    out.append('> - **一级按难度分章、章内按尺寸分节**（对齐 Vol.11 数墙「难度 · 尺寸」格式），')
    out.append('>   并附「按尺寸速查」表；关号 `第N問` 为该难度内序号，与实机 `LEVEL 第N問` 一致。')
    out.append('> - 余下 **36 道**正式题（5 条各尺寸样本 + `idx1402` 教程盘 + 末尾 30 条）')
    out.append('>   **不在选关页 270 关内**，难度归属未解码，单列附录 A，不臆测。')
    out.append('')
    out.append('## 分章速查')
    out.append('')
    out.append('**按难度**（一级章）：')
    out.append('')
    out.append('| 难度 | 关数 | pack idx 范围 | 尺寸分布 | 实机 `クリア数` 分母 |')
    out.append('|---|---|---|---|---|')
    for i, (name, count, start, den) in enumerate(DIFFS):
        sizes = {}
        for _n, p in diff_items[i]:
            k = f'{p["w"]}×{p["h"]}'
            sizes[k] = sizes.get(k, 0) + 1
        dist = ' / '.join(f'{k} ×{v}' for k, v in sizes.items())
        out.append(f'| **{name}** | {count} | `{start}–{start + count - 1}` | {dist} | `{den}` |')
    out.append('| 附录 A（归属未解码） | 36 | `1395–1402`, `1673–1702` | 6×6 ×2 / 10×10 ×9 / 18×10 ×9 / 24×14 ×8 / 36×20 ×8 | 不在选关页 |')
    out.append('| 附录 B（空白占位） | 2 | `1400`, `1401` | 6×6 ×2 | 无答案盘面 |')
    out.append('')
    out.append('**按尺寸**（二级节速查；`–` 表示该难度无此尺寸）：')
    out.append('')
    out.append('| 尺寸 | 总关数 | 入門 | やさしい | ふつう | むずかしい | 附录 A |')
    out.append('|---|---|---|---|---|---|---|')
    for size in SIZE_ORDER:
        row = []
        for i in range(4):
            row.append(sum(1 for _n, p in diff_items[i]
                           if (p['w'], p['h']) == size))
        ex = sum(1 for p in extra if (p['w'], p['h']) == size)
        total = sum(row) + ex
        cells = [str(v) if v else '–' for v in row]
        out.append(f'| **{size[0]}×{size[1]}** | {total} | '
                   + ' | '.join(cells) + f' | {ex} |')
    out.append('')
    out.append('> 全库 308 条记录 = 270 关（4 难度）+ 36 道附录 A + 2 条附录 B。')
    out.append('')

    # 一级：按难度分章；二级：按尺寸分节
    for i, (name, count, start, den) in enumerate(DIFFS):
        items = diff_items[i]
        out.append(f'## {CN_NUM[i]}、{name}（{count} 关）')
        out.append('')
        out.append(f'> 实机选关页 `クリア数 000/{den}`；pack idx `{start}–{start + count - 1}`。')
        out.append('')
        segs = []
        for n, p in items:
            k = (p['w'], p['h'])
            if segs and segs[-1][0] == k:
                segs[-1][1].append((n, p))
            else:
                segs.append((k, [(n, p)]))
        for k, seg in segs:
            out.append(f'### {name} · {k[0]}×{k[1]}（{len(seg)} 关）')
            out.append('')
            for n, p in seg:
                out.append(f'**第{n:02d}問 · pack idx{p["idx"]}（{p["w"]}×{p["h"]}）**')
                out.append(render(p))
                out.append('')

    # 附录 A：不在选关页内的 36 道记录，按尺寸分节
    out.append('## 附录 A：不在选关页内的 36 道记录（难度归属未解码）')
    out.append('')
    out.append('> 这 36 道有完整题面与答案，但不在 4 个难度选关页的 270 关内，')
    out.append('> 归属（教程样本 / 追加问题 / 其它模式）**未解码，不臆测**，仅按尺寸登记。')
    out.append('> 组成：前 5 条各尺寸样本 `idx1395–1399`、`idx1402` 教程盘、')
    out.append('> 末尾 30 条 `idx1673–1702`（10×10 ×8 / 18×10 ×8 / 24×14 ×7 / 36×20 ×7）。')
    out.append('> 其中仅 `idx1399` 与主体 `idx1649` 题面完全相同，其余均为独立盘面。')
    out.append('')
    by_size = {}
    for p in extra:
        by_size.setdefault((p['w'], p['h']), []).append(p)
    for size in SIZE_ORDER:
        if size not in by_size:
            continue
        items = sorted(by_size[size], key=lambda p: p['idx'])
        out.append(f'### 附录 A · {size[0]}×{size[1]}（{len(items)} 关）')
        out.append('')
        for p in items:
            out.append(f'**pack idx{p["idx"]}（{p["w"]}×{p["h"]}）**')
            out.append(render(p))
            out.append('')

    # 附录 B：2 条空白占位
    out.append('## 附录 B：2 条空白占位记录（ROM 无答案盘面，不渲染矩阵）')
    out.append('')
    out.append('> 这两条不是正式关卡，答案层全 0，若渲染成全 `○` 会误导成「整盘都在环外」，')
    out.append('> 因此只登记不画盘面。')
    out.append('')
    out.append('| pack idx | 尺寸 | 情况 |')
    out.append('|---|---|---|')
    out.append('| `idx1400` | 6×6 | 线索盘全空、答案掩码全 0，纯占位 |')
    out.append('| `idx1401` | 6×6 | 教程练习盘：有线索，但 ROM 答案层全 0（环是教程里现画的，不在题库记录里） |')
    out.append('')
    out.append('> 题面层仍可读（308/308），实机第 1 問 `idx1403` / 第 2 問 `idx1404` 已与屏幕逐格对上。')
    out.append('')

    text = '\n'.join(out).rstrip() + '\n'
    self_check(data, text, diff_items, extra, blanks)
    with open(DST, 'w', encoding='utf-8') as f:
        f.write(text)
    print('已写出', DST, len(text.encode('utf-8')), 'bytes',
          '%.1f KB' % (len(text.encode('utf-8')) / 1024))


if __name__ == '__main__':
    main()
