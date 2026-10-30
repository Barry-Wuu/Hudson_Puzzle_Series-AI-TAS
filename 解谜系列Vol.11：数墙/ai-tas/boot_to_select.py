#!/usr/bin/env python3
"""冷启动导航：DeSmuME 重启 -> 本編を -> 存档1 -> やさしい选关页。

路径（2026-10-24 冷启动实测修正）：
  boot -> logo/title -> tap(128,40) 本編を始める -> slot存档页
  -> tap(128,60) 存档1行 -> x -> diff -> やさしい -> x -> select
  （旧 68 落在按钮下方空隙、冷启动必卡；114/160 是体験版 HITORI/AKARI，勿碰）
防吞：关键按键/点击后轮询状态确认，失败重试。
"""
import sys
import time

sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import ds
import mode2_fast as M


def wait_state(want, timeout=8.0, iv=0.25):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = M.state()
        if st in want:
            return st
        time.sleep(iv)
    return M.state()


def boot_to_select():
    # 1. 到 title（logo 页）：可能需要点本編を
    for att in range(6):
        st = M.state()
        print(f"  boot{att} state={st}", flush=True)
        if st == "select":
            return True
        if st == "title":
            ds.tap(128, 40, after=1.0)          # 本編を始める（2026-10-24 冷启动实测；68 落空隙、135 落体験版AKARI）
            st2 = wait_state(("slot", "menu", "diff"), 6)
            print(f"    -> {st2}", flush=True)
            if st2 == "slot":
                break                              # 存档页
        elif st == "slot":
            break
        elif st == "diff":
            break
        elif st == "menu":
            ds.tap(170, 83, after=1.2)
        else:
            ds.press("z", wait=0.8)
        time.sleep(0.3)

    # 2. 存档页 -> 存档1 -> diff
    for att in range(6):
        st = M.state()
        print(f"  slot{att} state={st}", flush=True)
        if st == "diff":
            break
        if st == "select":
            return True
        ds.tap(128, 60, after=0.6)                 # 存档1行（★60，原 95 会落存档2）
        ds.press("x", wait=1.5)
        st2 = wait_state(("diff", "select"), 6)
        print(f"    -> {st2}", flush=True)
        if st2 == "diff":
            break

    # 3. diff -> やさしい -> select
    for att in range(8):
        st = M.state()
        print(f"  diff{att} state={st}", flush=True)
        if st == "select":
            return True
        if st != "diff":
            print("  unexpected state", st, flush=True)
            return False
        # ★ 2026-10-23 修：原 Down×2「防吞补按」会进 ふつう。
        # 改为 select_diff()：Up 环绕到入門 → 按 DIFF Down N 次 → x，与光标原位置无关。
        M.select_diff()
        st2 = wait_state(("select", "diff"), 6)
        print(f"    -> {st2}", flush=True)
        if st2 == "select":
            return True
        # 又回 diff（x 被吞或选错难度）：继续循环重试
    return False


if __name__ == "__main__":
    ok = boot_to_select()
    print("RESULT:", "OK" if ok else "FAIL", flush=True)
    sys.exit(0 if ok else 1)
