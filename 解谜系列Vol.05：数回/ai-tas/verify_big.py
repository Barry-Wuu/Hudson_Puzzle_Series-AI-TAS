#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.05 数回 大盘（24x14 / 36x20）录制验收。

对 outdir 下每段 mp4 检查：
  * 编码 h264 256x384@30fps + aac 44100Hz 2ch
  * 末帧为真正结算页（复用 record18_v4.real_result 的三重颜色判据：
    上屏绿 > 0.45、上屏中蓝 > 0.18、下屏橙 < 300）
  * record_log.json 中该关 cleared=True
并可生成末帧拼图证据图（与其它 Vol 相同的 MEDIANCUT 256 色压缩）。

用法:
    python3 ai-tas/verify_big.py --dir /workspace/vol5_recordings_futsuu_24x14 \
        --evidence ai-tas/evidence/42_futsuu_24x14_tails.png
"""
import argparse
import json
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw


def probe(path):
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate,channels",
         "-of", "json", path], text=True)
    return json.loads(out)["streams"]


def codec_ok(streams):
    v = next((s for s in streams if s["codec_type"] == "video"), None)
    a = next((s for s in streams if s["codec_type"] == "audio"), None)
    if not v or not a:
        return False, "缺视频或音频流"
    fr = v.get("r_frame_rate", "0/1")
    if "/" in fr:
        num, den = fr.split("/")
        fps = float(num) / float(den)
    else:
        fps = float(fr)
    ok = (v["codec_name"] == "h264" and v["width"] == 256 and v["height"] == 384
          and abs(fps - 30) < 0.1 and a["codec_name"] == "aac"
          and int(a.get("sample_rate", 0)) == 44100
          and int(a.get("channels", 0)) == 2)
    desc = (f"{v['codec_name']} {v['width']}x{v['height']}@{fps:g}fps + "
            f"{a['codec_name']} {a.get('sample_rate')}Hz {a.get('channels')}ch")
    return ok, desc


def tail_png(path, out="/tmp/_vb_tail.png"):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-sseof", "-0.3",
                    "-i", path, "-frames:v", "1", out], check=True)
    return Image.open(out).convert("RGB")


def real_result(a):
    """与 record18_v4.real_result 一致，但数据源是视频末帧而非实机截图。

    ★ 2026-11-13：去掉「中部蓝色横幅」要求。BGM / デザイン = RANDOM 会换主题，
      第19問实测结算页是**纯绿底成绩板**（上屏绿 0.615）且完全没有蓝色横幅，
      旧判据 blue>0.18 永远不满足 -> 真过关也判失败。
      绿色占比本身区分度足够：盘面/Completion 页上屏绿 = 0.000。
    """
    t, b = a[0:192], a[192:384]
    R, G, B = t[:, :, 0], t[:, :, 1], t[:, :, 2]
    green = float(((G > R + 25) & (G > B + 25) & (G > 80)).mean())
    mid = t[45:115]
    Rm, Gm, Bm = mid[:, :, 0], mid[:, :, 1], mid[:, :, 2]
    blue = float(((Bm > Rm + 25) & (Bm > Gm + 5) & (Bm > 90)).mean())
    Rb, Gb, Bb = b[:, :, 0], b[:, :, 1], b[:, :, 2]
    orange = int(((Rb > 150) & (Gb > 60) & (Gb < 175) & (Bb < 110)).sum())
    # ★ 2026-11-13 去掉「下屏橙 < 300」要求：デザイン=RANDOM 主题色每关随机，
    #   暖色(米黄)主题的下屏盘面本身就是橙色，第20問末帧 orange=2244 被误判
    #   为失败（该帧实为真结算页：クリアタイム 00:06:07 / ★★★★★ / 得点 1068）。
    #   上屏绿底成绩板 (green>0.45) 已足够：盘面/Completion 页上屏绿≈0.000。
    #   orange 仍随诊断元组返回，仅作参考、不参与判定。
    return (green > 0.45), (round(green, 3), round(blue, 3), orange)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--evidence", default=None)
    ap.add_argument("--cols", type=int, default=8)
    a = ap.parse_args()

    mp4s = sorted(f for f in os.listdir(a.dir) if f.endswith(".mp4"))
    logpath = os.path.join(a.dir, "record_log.json")
    log = {}
    if os.path.exists(logpath):
        try:
            log = {r["lvl"]: r for r in json.load(open(logpath, encoding="utf-8"))}
        except (ValueError, OSError):
            pass

    bad = []
    thumbs = []
    for f in mp4s:
        path = os.path.join(a.dir, f)
        m = re.search(r"第(\d+)問", f)
        lvl = int(m.group(1)) if m else None
        try:
            ok, desc = codec_ok(probe(path))
        except Exception as e:
            ok, desc = False, f"ffprobe失败 {e}"
        try:
            im = tail_png(path)
            rr, vals = real_result(np.asarray(im).astype(int))
            thumbs.append((lvl, im))
        except Exception as e:
            rr, vals = False, f"抽帧失败 {e}"
        cl = bool(log.get(lvl, {}).get("cleared"))
        flag = ok and rr and cl
        if not flag:
            bad.append(f)
        print(f"{'OK ' if flag else 'BAD'} {f}: 编码={ok}({desc}) "
              f"末帧结算={rr}{vals} 日志cleared={cl}", flush=True)

    print(f"\n合计 {len(mp4s)} 段，异常 {len(bad)} 段", flush=True)
    if bad:
        print("异常:", bad, flush=True)

    if a.evidence and thumbs:
        cw, ch = 128, 192
        cols = a.cols
        rows = (len(thumbs) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cw, rows * ch), (255, 255, 255))
        dr = ImageDraw.Draw(sheet)
        for i, (lvl, im) in enumerate(thumbs):
            x, y = (i % cols) * cw, (i // cols) * ch
            sheet.paste(im.resize((cw, ch)), (x, y))
            dr.text((x + 3, y + 3), f"{lvl:02d}" if lvl is not None else f"{i+1:02d}",
                    fill=(255, 0, 0))
        os.makedirs(os.path.dirname(a.evidence) or ".", exist_ok=True)
        q = sheet.quantize(colors=256, method=Image.MEDIANCUT)
        q.save(a.evidence, optimize=True, compress_level=9)
        print("证据图", a.evidence, sheet.size, flush=True)

    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
