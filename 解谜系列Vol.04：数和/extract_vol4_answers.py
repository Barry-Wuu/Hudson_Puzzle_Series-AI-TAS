#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.4（数和 / Kakuro）答案数据提取器 —— 从 ROM 的 CPQ. 数据块挖出现成题库。

方法论（用户定调）：答案是 ROM 里现成的二进制数据表，"玩的时候"从 bin 挖出，
不是求解器现场推算，也不必逆运行时内存编码。本脚本走静态提取，与 Vol.13
`datasheet.bin` 同家族做法。

ROM 结构（实测，日版 AQ6J / 8MiB）：
  r.files[4]（Nitro 资源包）内偏移 0x27acc0 处是 `CPQ.` 数据块：
    [0:4]   magic = b'CPQ.'
    [4:8]   u32 count = 310          关卡总数
    [8:8+4*310] 310 个 u32 偏移表   第 k 项 = 第 k 关记录在块内的偏移
                （首项 1248 = 8 + 4*310，即偏移表刚好结束，自洽）
    [1248:159584] 310 条关卡记录     每条 = [offs[k] : offs[k+1]]
  每条记录头部第一个 u32 = 关卡号（实测 0..309 全部成立，零反例）。
  记录体是 Kakuro 盘面：段和提示（10..45）+ 答案数字盘（1..9，0 = 黑格/斜线格）。
  答案盘满足 "同一 run 内数字不重复"（全库自检 99.5%，见 validate）。

用法：
  python3.11 extract_vol4_answers.py [ROM路径]
默认 ROM: /workspace/roms/解谜系列Vol.04：数和.nds
产出（写到脚本同目录 validation/ 下）：
  vol4_cpq.bin     CPQ. 块原始字节（答案 bin 保真存档）
  vol4_all.json    310 关结构化数据 + 自检
"""
import sys, os, json, struct
from collections import Counter
import ndspy.rom

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, 'validation')
DEFAULT_ROM = '/workspace/roms/解谜系列Vol.04：数和.nds'


def find_cpq(block_bytes):
    """返回 (magic 在块内的位置, count, 偏移表)。用 magic 搜索，不写死偏移。"""
    pos = block_bytes.find(b'CPQ.')
    if pos < 0:
        raise RuntimeError('未找到 CPQ. 数据块')
    count = struct.unpack_from('<I', block_bytes, pos + 4)[0]
    offs = [struct.unpack_from('<I', block_bytes, pos + 8 + 4 * k)[0]
            for k in range(count)]
    return pos, count, offs


def dup_check(grid_bytes):
    """把 0 视为黑格分隔符，检查每个连续非零 run 内数字是否不重复。
    返回 (满足段数, 违反段数)。仅适用于「答案数字盘」(值 0..9)。"""
    ok = bad = 0
    cur = []
    for v in grid_bytes:
        if v == 0:
            if len(cur) >= 2:
                if len(set(cur)) == len(cur):
                    ok += 1
                else:
                    bad += 1
            cur = []
        else:
            cur.append(int(v))
    if len(cur) >= 2:
        if len(set(cur)) == len(cur):
            ok += 1
        else:
            bad += 1
    return ok, bad


def answer_disk(rec):
    """取记录内「最后一个连续 >=16B、值全 0..9」的块作为答案数字盘。
    段和提示(10..45)等 >9 字节会打断连续性，因此不会混进来污染 run 判定。"""
    best = None
    i = 0
    n = len(rec)
    while i < n:
        if 0 <= rec[i] <= 9:
            j = i
            while j < n and 0 <= rec[j] <= 9:
                j += 1
            if j - i >= 16:
                best = (i, j)      # 记最后一个这样的块
            i = j
        else:
            i += 1
    return best


def main():
    rom_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROM
    rom = ndspy.rom.NintendoDSRom.fromFile(rom_path)

    # 遍历所有 ROM 文件，找含 'CPQ.' 的那个（实测落在 r.files[4]，但不写死索引）
    target = None
    for idx, fdata in enumerate(rom.files):
        b = bytes(fdata)
        if b.find(b'CPQ.') >= 0:
            target = (idx, b)
            break
    if target is None:
        raise RuntimeError('ROM 内没有任何文件包含 CPQ. 数据块')
    file_idx, blob = target
    pos, count, offs = find_cpq(blob)

    # CPQ. 块尾 = 该资源块内下一个 magic 或文件尾；用偏移表末项 + 末记录长度兜底
    # 实测块长 159584；这里取 offs[-1] 之后到下一个 'CPQ.'/文件尾之间，稳妥用文件尾
    blk_end = len(blob)
    cpq = blob[pos:blk_end]                 # 从 CPQ. 到该文件尾（含块内偏移表+记录）
    # 记录绝对位置在 blob 内 = pos + offs[k]；块内相对 = offs[k]
    rec_end = 159584 if len(cpq) >= 159584 else len(cpq)   # 实测块长，保真

    print('ROM 文件:', rom_path)
    print('CPQ. 所在 ROM 文件索引: r.files[%d]' % file_idx)
    print('CPQ. 块内偏移: 0x%x  记录数: %d  偏移表首项: %d (=8+4*%d=%d)'
          % (pos, count, offs[0], count, 8 + 4 * count))
    print('偏移严格递增:', all(offs[i] < offs[i + 1] for i in range(count - 1)))

    os.makedirs(OUTDIR, exist_ok=True)
    # 答案 bin 保真存档（只存 CPQ. 块本体：magic + 表 + 记录）
    cpq_body = blob[pos:pos + rec_end]
    with open(os.path.join(OUTDIR, 'vol4_cpq.bin'), 'wb') as fp:
        fp.write(cpq_body)

    levels = []
    bad_level = []
    headers = []
    tot_ok = tot_bad = 0
    clue_cnt = 0
    for k in range(count):
        a = pos + offs[k]
        b = pos + (offs[k + 1] if k + 1 < count else rec_end)
        rec = blob[a:b]
        level = struct.unpack_from('<I', rec, 0)[0] if len(rec) >= 4 else -1
        if level != k:
            bad_level.append((k, level))
        head = [struct.unpack_from('<I', rec, i)[0]
                for i in range(0, min(len(rec), 20), 4)]
        headers.append(tuple(head))
        # 记录体（去头部 20 字节）里的 Kakuro 线索
        body = rec[20:]
        clue_cnt += sum(1 for x in body if 10 <= x <= 45)
        disk = answer_disk(rec)
        if disk:
            ok, bad = dup_check(rec[disk[0]:disk[1]])
            tot_ok += ok
            tot_bad += bad
            disk_span = [disk[0], disk[1]]
        else:
            disk_span = []
        levels.append({
            'level': k,                       # 0-based 关卡号
            'rec_len': len(rec),
            'offset_in_cpq': offs[k],
            'header_u32': head,              # 头部 5 个 u32（首=关卡号；其余为逐关变化的盘面参数，语义待逐字段验证，不臆断）
            'body_len': len(body),
            'clue_bytes': sum(1 for x in body if 10 <= x <= 45),  # 段和提示字节数（10..45）
            'answer_disk_span': disk_span,   # 答案数字盘在整条记录内的 [起,止) 偏移
            'body_hex': body.hex(),          # 记录体保真（段和 + 答案数字盘，0=黑格）
        })

    # 头部常量字段统计（如实记录哪些逐关变化）
    for j in range(1, 5):
        vals = [h[j] for h in headers if len(h) > j]
        top = Counter(vals).most_common(3)
        print('  头部 u32[%d] 取值分布(top3): %s' % (j, top))

    rate = 100.0 * tot_ok / max(1, tot_ok + tot_bad)
    report = {
        'rom': os.path.basename(rom_path),
        'gamecode': 'AQ6J',
        'region': 'Japan',
        'method': 'ROM 内 CPQ. 数据块静态提取（现成答案表，非求解器推算）',
        'cpq_file_index': file_idx,
        'cpq_offset_in_file': pos,
        'cpq_block_len': rec_end,
        'level_count': count,
        'offset_table_first': offs[0],
        'selfcheck': {
            'offset_strictly_increasing': all(offs[i] < offs[i + 1] for i in range(count - 1)),
            'level_number_all_match': len(bad_level) == 0,
            'level_mismatch': bad_level[:10],
            'dup_free_runs_ok': tot_ok,
            'dup_free_runs_bad': tot_bad,
            'dup_free_rate_pct': round(rate, 2),
            'dup_check_scope': '仅答案数字盘(连续0..9块)，段和提示>9不参与',
            'clue_bytes_total': clue_cnt,
        },
        'levels': levels,
    }
    with open(os.path.join(OUTDIR, 'vol4_all.json'), 'w', encoding='utf-8') as fp:
        json.dump(report, fp, ensure_ascii=False, indent=1)

    print('\n=== 自检 ===')
    print('关卡号 0..%d 全部匹配: %s (反例 %d)' % (count - 1, len(bad_level) == 0, len(bad_level)))
    print('答案盘 段内不重复率: %.2f%% (%d 满足 / %d 违反)' % (rate, tot_ok, tot_bad))
    print('段和提示字节总计:', clue_cnt)
    print('\n产出:')
    print('  %s (%d B)' % (os.path.join(OUTDIR, 'vol4_cpq.bin'), os.path.getsize(os.path.join(OUTDIR, 'vol4_cpq.bin'))))
    print('  %s (%d B, %d 关)' % (os.path.join(OUTDIR, 'vol4_all.json'),
          os.path.getsize(os.path.join(OUTDIR, 'vol4_all.json')), len(levels)))


if __name__ == '__main__':
    main()
