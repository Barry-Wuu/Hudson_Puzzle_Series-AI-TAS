#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""带音高补偿的验证：rec_BGM00（网页版录音）↔ SEQ_BGM00 渲染。

背景（已实测）：
- rec_BGM00（原名 rec_puzzle）是网页版模拟器录音，已裁掉开头 1.315s 的菜单音效/静默，
  从音乐本体第一拍起算，避免开头 SFX 干扰 onset 统计与对齐
- 主音高 113.6Hz vs 本地渲染 BGM00 主音高 132.8Hz
  → 网页版音频时钟使整体音高降低约 2.5-2.7 半音（≈ -272 音分）
- 因此直接 chroma 对比会因移调而失配，需要「音高补偿」后再测旋律/速度相关性。

方法：
1. 对录音做音高补偿（重采样，使音高与渲染对齐）后计算：
   - chroma 零旋转相似度（应显著提升）
   - 最佳旋转 bin（应接近 0）
   - onset 速度比例（重采样不改变速度，只改音高）
2. 输出验证数据集结论。
"""
import subprocess, os, sys, tempfile, json
import numpy as np

FFMPEG = r'D:\B++\WorkBuddy\tools\ffmpeg\bin\ffmpeg.exe'
SR = 22050
HOP = 512
WIN = 2048

def decode_to_pcm(path, max_sec=180):
    tmp = tempfile.mktemp(suffix='.f32')
    try:
        r = subprocess.run(
            [FFMPEG, '-y', '-v', 'quiet', '-i', path,
             '-ac', '1', '-ar', str(SR), '-f', 'f32le', '-t', str(max_sec), tmp],
            capture_output=True)
        if r.returncode != 0:
            return None
        return np.fromfile(tmp, dtype=np.float32)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

def pitch_shift(pcm, semitones):
    """用重采样实现音高偏移（保持时长不变）。
    semitones>0 升高音高。升高 s 半音 = 重采样率乘以 2^(s/12)，
    再重采样回原长度（保持时长）。
    实现：用 FFT 插值/抽取，简化用 scipy.signal.resample_poly。
    """
    from scipy import signal
    factor = 2 ** (semitones / 12.0)
    # 目标：时长不变、音高升高 factor 倍
    # 先把 pcm 以 factor 倍速率重采样（缩短/变长样本数），再用插值拉回原长度
    # resample_poly(x, up, down) 改变采样率 factor = up/down
    # 要音高升高 factor：读取速率加快 factor → 等价于 up/down = factor
    from fractions import Fraction
    f = Fraction(factor).limit_denominator(1000)
    up, down = f.numerator, f.denominator
    y = signal.resample_poly(pcm, up, down)
    # 拉回原长度（保持时长）
    x_old = np.linspace(0, 1, len(y))
    x_new = np.linspace(0, 1, len(pcm))
    return np.interp(x_new, x_old, y).astype(np.float32)

def chroma_features(pcm):
    n = len(pcm)
    if n < WIN:
        return np.zeros((1, 12), dtype=np.float32)
    n_frames = (n - WIN) // HOP + 1
    chroma = np.zeros((n_frames, 12), dtype=np.float32)
    freqs = np.fft.rfftfreq(WIN, 1.0 / SR)
    midi = 69 + 12 * np.log2(np.maximum(freqs, 1e-6) / 440.0)
    valid = (midi >= 24) & (midi <= 96)
    pc = np.mod(np.round(midi[valid]).astype(int), 12)
    for i in range(n_frames):
        seg = pcm[i * HOP: i * HOP + WIN]
        if len(seg) < WIN:
            break
        seg = seg * np.hanning(WIN)
        spec = np.abs(np.fft.rfft(seg))
        s = spec[valid]
        acc = np.bincount(pc, weights=s, minlength=12).astype(np.float32)
        m = np.max(acc)
        if m > 1e-6:
            acc = acc / m
        chroma[i] = acc
    return chroma

def normalize_rows(c):
    norms = np.linalg.norm(c, axis=1, keepdims=True)
    norms[norms < 1e-6] = 1
    return c / norms

def spectral_flux(pcm):
    n = len(pcm)
    n_frames = (n - WIN) // HOP + 1
    flux = np.zeros(n_frames)
    prev = np.zeros(WIN // 2 + 1)
    for i in range(n_frames):
        seg = pcm[i * HOP: i * HOP + WIN]
        if len(seg) < WIN:
            break
        seg = seg * np.hanning(WIN)
        spec = np.abs(np.fft.rfft(seg))
        flux[i] = np.sum(np.maximum(0, spec - prev))
        prev = spec
    return flux

def main():
    rec_dir = r'D:\B++\WorkBuddy\2026-10-10-20-10-45\解谜系列Vol.13 汉字解谜\music_extract\recordings'
    rend_dir = r'D:\B++\WorkBuddy\2026-10-10-20-10-45\解谜系列Vol.13 汉字解谜\music_extract\rendered'
    rec_name = sys.argv[1] if len(sys.argv) > 1 else 'rec_BGM00'
    target = sys.argv[2] if len(sys.argv) > 2 else 'SEQ_BGM00'

    rec_pcm = decode_to_pcm(os.path.join(rec_dir, rec_name + '.mp3'))
    rend_pcm = decode_to_pcm(os.path.join(rend_dir, target + '.wav'))
    if rec_pcm is None or rend_pcm is None:
        print('解码失败')
        sys.exit(1)

    rend_ch = normalize_rows(chroma_features(rend_pcm))
    rend_fl = spectral_flux(rend_pcm)

    print(f'=== 音高补偿验证: {rec_name} ↔ {target} ===\n')
    print(f'录音 {len(rec_pcm)/SR:.2f}s, 渲染 {len(rend_pcm)/SR:.2f}s')

    # 搜索最佳音高补偿量（-6 到 +6 半音，步长 0.25）
    print('\n[1] 音高补偿扫描（每 0.25 半音）')
    best = None
    for s in np.arange(-6, 6.01, 0.25):
        shifted = pitch_shift(rec_pcm, s)
        rc = normalize_rows(chroma_features(shifted))
        L = min(len(rc), len(rend_ch))
        sim = float(np.median(np.sum(rc[:L] * rend_ch[:L], axis=1)))
        if best is None or sim > best[1]:
            best = (s, sim)
    print(f'  最佳补偿: {best[0]:+.2f} 半音 → 相似度 {best[1]:.4f}')

    # 用最佳补偿做完整分析
    comp = best[0]
    shifted = pitch_shift(rec_pcm, comp)
    rc = normalize_rows(chroma_features(shifted))
    rfl = spectral_flux(shifted)
    L = min(len(rc), len(rend_ch))
    sim_comp = float(np.median(np.sum(rc[:L] * rend_ch[:L], axis=1)))
    print(f'\n[2] 补偿后旋律相关性: 零旋转中位相似度 = {sim_comp:.4f}')

    # 最佳旋转（应接近0）
    best_rot = -1
    best_rot_sim = -1
    for r in range(12):
        rr = np.roll(rc, r, axis=1)
        s = float(np.median(np.sum(rr[:L] * rend_ch[:L], axis=1)))
        if s > best_rot_sim:
            best_rot, best_rot_sim = r, s
    print(f'  最佳旋转: {best_rot} bin (相似度 {best_rot_sim:.4f})')
    print(f'  → 最佳旋转 {best_rot} bin = {"同调" if best_rot==0 else f"{best_rot} 半音偏移"}')

    # 速度相关性（onset 对齐）
    print('\n[3] 速度相关性（onset 包络）')
    rfn = rend_fl / (np.max(rend_fl) + 1e-9)
    qfn = rfl / (np.max(rfl) + 1e-9)
    best_scale = None
    best_corr = -1
    for sc in np.linspace(0.8, 1.2, 81):
        nq = len(qfn)
        nr = int(nq * sc)
        if nr < 30 or nr > len(rfn):
            continue
        x_old = np.linspace(0, 1, nq)
        x_new = np.linspace(0, 1, nr)
        qr = np.interp(x_new, x_old, qfn)
        n = len(rfn) + len(qr) - 1
        R = np.fft.rfft(rfn, n)
        Q = np.fft.rfft(qr, n)
        corr = np.fft.irfft(R * np.conj(Q), n)
        peak = float(np.max(corr)) / len(qr)
        if peak > best_corr:
            best_corr = peak
            best_scale = sc
    print(f'  最佳 scale={best_scale:.3f} (peak_corr={best_corr:.3f})')
    print(f'  → 录音速度 = 渲染速度 × {best_scale:.3f}')
    speed_ratio = best_scale if best_scale else 1.0

    print('\n=== 验证数据集结论 ===')
    print(f'旋律相关性: {sim_comp:.3f} (补偿 {comp:+.2f} 半音后, 旋转 {best_rot} bin)')
    print(f'速度相关性: scale={speed_ratio:.3f} (Pearson/峰值相关 {best_corr:.3f})')
    ok_m = sim_comp > 0.6
    ok_t = abs(speed_ratio - 1.0) < 0.08
    print(f'{"✅" if ok_m else "❌"} 旋律显著相关 (>{0.6})')
    print(f'{"✅" if ok_t else "❌"} 速度一致 (±8%)')

    # 保存 JSON
    report = {
        'recording': rec_name,
        'seq': target,
        'rec_sec': round(len(rec_pcm)/SR, 2),
        'rend_sec': round(len(rend_pcm)/SR, 2),
        'pitch_compensation_semitones': round(float(comp), 2),
        'melody_similarity_compensated': round(float(sim_comp), 4),
        'best_rotation_bins': int(best_rot),
        'best_rotation_sim': round(float(best_rot_sim), 4),
        'speed_scale': round(float(speed_ratio), 4),
        'onset_peak_corr': round(float(best_corr), 4),
        'conclusion': {
            'melody_correlated': bool(ok_m),
            'tempo_consistent': bool(ok_t),
        }
    }
    out = os.path.join(rend_dir, f'verify_{rec_name}_{target}.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'\n报告已保存: {out}')

if __name__ == '__main__':
    main()