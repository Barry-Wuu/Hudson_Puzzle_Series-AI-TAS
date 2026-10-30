#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seg2b platinum 認定証补录（tag=seg2bp，2026-10-17）。

**为什么补**：seg2b 录 platinum 时证书轮询窗口只有 60s，而模式1 末级通关演出极长
（正解 →「全問正解!」→ 記録滚动 ~66s → 認定証 ~+85s → おめでとう → 淡出 → 标题页），
原片在第 136s 被截断在滚动中段，platinum 認定証始终未上屏。

**做法**：恢复 15:43:06 存档（bronze/silver/gold 已认定、platinum 未认定），
从「ゴールド选中」的认定菜单（= seg2b 80.2s 帧）续录到尾：
  冷启动(带声) → ファイル1 → ゲーム選択 → 漢字ナンクロ → 認定問題 → 级别菜单
  → 点ゴールド（对齐拼接帧）→ [起录] → 两击プラチナ（首击移高亮/二击激活，§S50.4）
  → 进盘 → 设 BGM2（§S60.4：设置不落盘，同会话内必须重设）
  → リスト + rec50-54 全库匹配 → 快通填字 → 正解 → 全問正解! → 記録滚动 → 認定証 → 标题页

  轮询 400 轮 ≈ 220s（覆盖 ~85s 演出 + 余量）；仅在庆典弹窗期(前 12 轮/is_popup)点击推进，
  记录滚动期间绝不乱点（乱点会把認定証点掉，§S62 platinum 同款教训）。

用法：python3 record_seg2b_plat.py
产物：/workspace/recordings/seg2bp.mp4 + validation/mode1_4_certification/platinum_certificate.png
"""
import os
import sys
import time
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

os.environ.setdefault('AI_TAS_DISPLAY', ':0')
os.environ.setdefault('DISPLAY', ':0')
os.environ.setdefault('XDG_RUNTIME_DIR', '/tmp/xdg-pulse')
os.environ.setdefault('SDL_AUDIODRIVER', 'pulse')
os.environ.setdefault('LD_LIBRARY_PATH', '/usr/games:/usr/lib/x86_64-linux-gnu')
# 模式1 = fast 档（与 seg2b 相同；段名不在 _SLOW_SEGS）
for _k, _v in dict(AI_TAS_TAP_HOLD='0.02', AI_TAS_MOVE_GAP='0.02', AI_TAS_TAP_AFTER='0.02',
                   AI_TAS_ARROW_AFTER='0.02', AI_TAS_KANJI_AFTER='0.02', AI_TAS_FILL_WAIT='0.02',
                   AI_TAS_HOP_AFTER='0.03', AI_TAS_BREATHE_EVERY='0', AI_TAS_PANEL_WAIT='0.6',
                   AI_TAS_SEIKAI_WAIT='0.1', AI_TAS_NAV_AFTER='1.5',
                   AI_TAS_NAV_ENTER_WAIT='5.0').items():
    os.environ.setdefault(_k, _v)

import kanji_common as KC          # noqa: E402
import fill_fast_any as FF         # noqa: E402
import run as R                    # noqa: E402
import record_series as RS         # noqa: E402

TAG = 'seg2bp'
EVDIR = os.path.join(RS.ROOT, 'validation', 'mode1_4_certification')
POLL_ITERS = 400                   # ≈220s：模式1 末级演出 ~85s + 余量
LOG = RS.LOG


def full_library_match(path, topn=8):
    """盘面全库匹配（§S61.9 待办落地）：与 300 条 datasheet 记录逐一比对可见格掩码。

    ⚠️ 绝对差有大盘边缘漂移噪声（§S60.5.1：正确盘也报差 19-37，失配集中在最底 1-2 行），
    判据看**排名与领先幅度**：头名与次名差 ≥15 才采信。
    返回 [(diff, rec), ...] 升序前 topn。
    """
    import identify_kentei_board as IK
    import solve2
    m, _geo = IK.shot_map(path)
    vis = set(m)
    best = []
    for rec in range(300):
        try:
            r = solve2.solve(rec)
        except Exception:
            continue
        if not r:
            continue
        grid = set(r['grid'])
        w = max(c for c, _ in grid) + 1
        h = max(y for _, y in grid) + 1
        mm = 0
        for (c, rr) in vis:
            if c >= w or rr >= h:
                mm += 1
                continue
            if (m[(c, rr)] != '.') != ((c, rr) in grid):
                mm += 1
        best.append((mm, rec))
    best.sort()
    return best[:topn]


def main():
    R._set_shot_dir('/tmp/rec_%s' % TAG)
    os.makedirs(EVDIR, exist_ok=True)
    RS.cold_start_with_sound()
    RS.to_gamesel()
    RS.enter_mode(1)
    if not RS.cert_tap_entry(1):
        raise SystemExit('❌ 未到认定级别菜单')
    # --- 对齐 seg2b 拼接帧（80.2s：ゴールド选中，上屏 ゴールド認定問題 認定済み ロの数106） ---
    KC.tap(128, 116, after=1.6)
    time.sleep(0.6)
    join = R._shot('join_menu_gold.png')
    LOG('拼接帧菜单截图 → %s（人工核对后再起录）' % join)
    aud, vid = RS.start_ffmpeg(TAG)
    t0 = time.time()
    got = False
    try:
        time.sleep(0.5)
        # --- 两击进プラチナ盘 ---
        if not R._enter_kentei_board(1, 'platinum'):
            raise SystemExit('❌ 未进 platinum 盘')
        KC.wait_banner_gone(timeout=8.0)
        time.sleep(0.8)
        # --- BGM2（设置不落盘，§S60.4：跨会话必须重设） ---
        b = R.set_bgm('2', mode=1)
        LOG('BGM set → %s' % b)
        KC.wait_banner_gone(timeout=8.0)
        # --- リスト + 盘面识别（先全库匹配定 rec，再与本级题库核对，§S61.9） ---
        if not KC.list_panel_open():
            KC.tap(57, 136, after=0.5)
            time.sleep(1.0)
        board_png = R._shot('cert_plat_board.png')
        want = KC.kentei_recs('platinum', 1)
        lib = full_library_match(board_png)
        LOG('全库匹配 top：%s' % lib)
        rec_lib = lib[0][1]
        margin = lib[1][0] - lib[0][0] if len(lib) > 1 else 999
        if rec_lib not in want or margin < 15:
            raise SystemExit('❌ 全库匹配不在 platinum 池或无显著优势（%s）' % lib)
        scores = R._identify(1, board_png, want)
        if not scores or scores[0][1] != rec_lib:
            raise SystemExit('❌ 池内识别与全库结果不一致（%s vs %s）'
                             % (scores[:1], rec_lib))
        rec = rec_lib
        LOG('识别 rec%d（全库差 %d、领先 %d）' % (rec, lib[0][0], margin))
        FF.do_fill(None, rec=rec)
        src = os.path.join(KC.SHOT_DIR, 'rec%d_fill_complete.png' % rec)
        if os.path.exists(src):
            shutil.move(src, os.path.join(EVDIR, 'platinum_clear_r%d.png' % rec))
            LOG('正解证据 → %s' % os.path.join(EVDIR, 'platinum_clear_r%d.png' % rec))
        # --- 长轮询等認定証（模式1 末级演出：全問正解!→記録滚动~66s→認定証~+85s） ---
        for i in range(POLL_ITERS):
            p = R._shot('cert_plat_poll_%03d.png' % i)
            if not got and RS.is_certificate(p):
                shutil.copy(p, os.path.join(EVDIR, 'platinum_certificate.png'))
                LOG('🏅 platinum 認定証到手（第 %d 轮，+%.1fs）' % (i, time.time() - t0))
                got = True
                time.sleep(1.0)
                KC.tap(*KC.CLEAR_DISMISS, after=1.5)
                break
            if R._cert_menu(1, p):
                LOG('ℹ️ 轮询中回到认定菜单（未见証）')
                break
            if KC.on_title(p):
                LOG('🏁 轮询中已回标题页（%s）' % ('証已到手' if got else '未见証'))
                break
            if i < 12 or KC.is_popup(p):
                KC.tap(*KC.CLEAR_DISMISS, after=0.4)
            time.sleep(0.5)
        # --- 証后的「おめでとう」/淡出/回标题 ---
        for i in range(12):
            p = R._shot('cert_plat_after_%02d.png' % i)
            if KC.on_title(p):
                LOG('🏁 通关演出结束，已回标题页')
                break
            if i % 2 == 1:
                KC.tap(*KC.CLEAR_DISMISS, after=1.2)
            time.sleep(0.8)
    finally:
        RS.stop_ffmpeg(vid)
        RS.stop_ffmpeg(aud)
        LOG('停止采集，合成中…')
        RS.mux(TAG)
    LOG('=== %s 完成：%.1fs，認定証 %s ===' % (TAG, time.time() - t0, '✅ 到手' if got else '❌ 缺失'))
    return 0 if got else 1


if __name__ == '__main__':
    sys.exit(main())
