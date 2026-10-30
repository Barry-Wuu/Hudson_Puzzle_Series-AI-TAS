#!/usr/bin/env python3
"""SSEQ+SWAR 合成器：从游戏源数据渲染原声大碟（WAV）。

管线：SDAT → SSEQ 事件解释器（轨道/Call/Return/Jump/Tempo）→
      SBNK 乐器查表 → SWAR 波形（ADPCM 解码）→ 音高重采样 +
      ADSR 包络 + 音量/声像 → 混音 → WAV。
"""
import ndspy.soundArchive as sa
import numpy as np, wave, struct, sys, os

SDAT = '/home/z/my-project/kanji_repo/sound_data.sdat'
OUT = '/home/z/my-project/kanji_repo/music_extract/rendered'
SR = 44100
TPQN = 24
wsrc_rates = {}
wloop_info = {}

# ---------- NDS IMA-ADPCM 解码 ----------
IMA_STEP = [7,8,9,10,11,12,13,14,16,17,19,21,23,25,28,31,34,37,41,45,50,55,60,
66,73,80,88,97,107,118,130,143,157,173,190,209,230,253,279,307,337,371,408,449,
494,544,598,658,724,796,876,963,1060,1166,1282,1411,1552,1707,1878,2066,2272,
2499,2749,3024,3327,3660,4026,4428,4871,5358,5894,6484,7132,7845,8630,9493,
10442,11487,12635,13899,15289,16818,18500,20350,22385,24623,27086,29794,32767]

def adpcm_decode(data):
    init = struct.unpack_from('<h', data, 0)[0]
    tidx = data[2]
    sample = init; table = tidx
    out = np.empty((len(data)-4)*2, dtype=np.float32)
    pos = 0
    for byte in data[4:]:
        for nib in (byte >> 4, byte & 0xF):  # NDS ADPCM: 高半字节在前
            step = IMA_STEP[table]
            diff = step >> 3
            if nib & 4: diff += step
            if nib & 2: diff += step >> 1
            if nib & 1: diff += step >> 2
            if nib & 8: diff = -diff
            sample = max(-32768, min(32767, sample + diff))
            table = max(0, min(88, table + [-1,-1,-1,-1,2,4,6,8][nib & 7]))
            out[pos] = sample / 32768.0
            pos += 1
    return out[:pos]

# ---------- 包络速率→时间 ----------
def rate_time(r, scale=0.5):
    if r >= 126: return 0.001
    return (127 - r) / 127.0 * scale

def load_all():
    arc = sa.SDAT(open(SDAT,'rb').read())
    # bank 15 = BANK_BGM, waveArchive 15 = WAVE_BGM
    sbnk = arc.banks[15][1]
    warc = arc.waveArchives[15][1]
    waves = {}
    for i, w in enumerate(warc.waves):
        assert int(w.waveType) == 2 or str(w.waveType) == '2', f'wave {i} not ADPCM'
        waves[i] = adpcm_decode(bytes(w.data))
    global wsrc_rates
    wsrc_rates = {i: int(w.sampleRate) for i, w in enumerate(warc.waves)}
    global wloop_info
    wloop_info = {i: (bool(w.isLooped), int(w.loopOffset), int(w.totalLength))
                  for i, w in enumerate(warc.waves)}
    return arc, sbnk, waves

def render(seq_name_seq, arc, sbnk, waves, max_seconds=180, fade_tail=1.0):
    name, seq = seq_name_seq
    seq.parse()
    evs = seq.events
    idx = {id(e): i for i, e in enumerate(evs)}
    starts = sorted([0] + [idx.get(id(e.firstEvent)) for e in evs
                           if type(e).__name__ == 'BeginTrackSequenceEvent' and idx.get(id(e.firstEvent))])
    bounds = starts + [len(evs)]
    n = int(max_seconds * SR)
    mixL = np.zeros(n + SR, dtype=np.float64)
    mixR = np.zeros(n + SR, dtype=np.float64)
    tempo = [120]
    active = []  # (end_sample, array, gainL, gainR, sustain_end, rel_rate, attack_t, decay_t, sustain_lvl)

    for ti in range(len(bounds)-1):
        seg, end = bounds[ti], bounds[ti+1]
        ch = ti % 16
        pc, stack, loops, steps = seg, [], 0, 0
        track_vol, expr, pan = 1.0, 1.0, 64
        prog = 0
        t_sec = 0.0
        mono = False  # SSEQ默认POLY：音符不推进时间线
        notes = []  # (start_tick, dur_ticks, midi, vel, prog_at, vol, expr, pan)
        while seg <= pc < end and steps < 20000:
            steps += 1
            e = evs[pc]; tn = type(e).__name__
            if tn == 'NoteSequenceEvent':
                notes.append((t_sec, e.duration / TPQN * 60.0 / tempo[0],
                              e.type & 0x7F, e.velocity,
                              prog, track_vol, expr, pan))
                if mono: t_sec += e.duration / TPQN * 60.0 / tempo[0]
            elif tn == 'RestSequenceEvent':
                t_sec += e.duration / TPQN * 60.0 / tempo[0]
            elif tn == 'TempoSequenceEvent': tempo[0] = e.value
            elif tn == 'MonoPolySequenceEvent': mono = (int(e.value) == 1)
            elif tn == 'InstrumentSwitchSequenceEvent': prog = e.instrumentID
            elif tn == 'TrackVolumeSequenceEvent': track_vol = e.value / 127.0
            elif tn == 'ExpressionSequenceEvent': expr = e.value / 127.0
            elif tn == 'PanSequenceEvent': pan = e.value
            elif tn == 'CallSequenceEvent':
                dst = idx.get(id(e.destination))
                if dst is not None: stack.append(pc+1); pc = dst; continue
            elif tn == 'ReturnSequenceEvent':
                if stack: pc = stack.pop(); continue
            elif tn == 'JumpSequenceEvent':
                dst = idx.get(id(e.destination))
                if dst is not None:
                    loops += 1
                    if loops > 8: break
                    pc = dst; continue
            pc += 1
        # 渲染音符
        for (t0, dur, midi, vel, pr, tv, ex, pa) in notes:
            if pr >= len(sbnk.instruments) or sbnk.instruments[pr] is None: continue
            inst = sbnk.instruments[pr]
            d = inst.noteDefinition if hasattr(inst, 'noteDefinition') else None
            if d is None or getattr(d, 'type', None) is None or int(d.type) != 1: continue
            w = waves.get(d.waveID)
            if w is None or len(w) < 8: continue
            base = d.pitch
            wsamp = wsrc_rates[d.waveID]  # 波形自身采样率
            factor = 2 ** ((midi - base) / 12.0) * (wsamp / SR)
            total_len = int(dur * SR / factor) + 1
            rel_t = max(0.01, rate_time(d.release, 0.4))
            rel_n = int(rel_t * SR)
            need = min(total_len + rel_n, n + SR)
            # 波形（循环支持）
            src = w
            looped, ls, le = wloop_info.get(d.waveID, (False, 0, len(src)))
            body = np.empty(need + 8, dtype=np.float32)
            if looped:
                idx_all = np.arange(need + 8)
                kk = np.where(idx_all >= le, ls + (idx_all - ls) % (le - ls), idx_all)
                kk = np.clip(kk, 0, len(src) - 1)
                body[:] = src[kk]
            else:
                # 非循环：整段播放一次，其后静音（由release包络收尾）
                body[:len(src)] = src[:need + 8]
                body[len(src):] = 0.0
            # 重采样读取（factor<1 时音高上移采样更密）
            out = np.empty(need, dtype=np.float64)
            read = np.arange(need) * factor
            i0 = read.astype(np.int64); frac = read - i0
            valid = i0 + 1 < len(body)
            out[valid] = body[i0[valid]] * (1-frac[valid]) + body[i0[valid]+1] * frac[valid]
            out[~valid] = 0.0
            # ADSR
            env = np.ones(need, dtype=np.float64)
            atk = max(1, int(rate_time(d.attack, 0.1) * SR))
            dec = max(1, int(rate_time(d.decay, 0.5) * SR))
            sus = d.sustain / 127.0
            rel = max(1, rel_n)
            gate = min(need, int(dur * SR / factor))
            for i in range(min(atk, need)):
                env[i] = i / atk
            j = min(atk, gate)
            for i in range(j, min(j+dec, gate)):
                env[i] = 1.0 - (1.0 - sus) * (i - j) / dec
            if j+dec < gate: env[j+dec:gate] = sus
            if gate < need:
                r = min(need - gate, rel)
                env[gate:gate+r] = env[gate-1] * (1 - np.arange(r)/r)
                if gate+r < need: env[gate+r:] = 0.0
            gain = (vel/127.0) * tv * ex * (d.sustain/127.0)**0  # velocity only
            p = (pa - 64) / 64.0
            gl = gain * (1 - max(0, p) * 0.7) * sus if False else gain * (1 - max(0,p)*0.7)
            gr = gain * (1 - max(0,-p) * 0.7)
            s0 = int(t0 * SR)
            segl = out * env * gl
            segr = out * env * gr
            e0 = s0 + need
            if s0 >= n: continue
            e0 = min(e0, n + SR)
            segl = segl[:e0-s0]; segr = segr[:e0-s0]
            if e0 - s0 <= 0: continue
            mixL[s0:e0] += segl
            mixR[s0:e0] += segr
    # 归一化 + 淡出
    m = max(1e-9, np.abs(mixL).max(), np.abs(mixR).max())
    mixL /= m; mixR /= m
    fo = int(fade_tail * SR)
    mixL[-fo:] *= np.linspace(1, 0, fo); mixR[-fo:] *= np.linspace(1, 0, fo)
    os.makedirs(OUT, exist_ok=True)
    path = f'{OUT}/{name}.wav'
    data = np.empty(n*2, dtype=np.int16)
    data[0::2] = (mixL[:n] * 32767).astype(np.int16)
    data[1::2] = (mixR[:n] * 32767).astype(np.int16)
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
        wf.writeframes(data.tobytes())
    print('rendered', name, '->', path)
    return path

if __name__ == '__main__':
    arc, sbnk, waves = load_all()
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for s in arc.sequences:
        if only and only not in s[0]: continue
        try:
            render(s, arc, sbnk, waves, max_seconds=90)
        except Exception as ex:
            import traceback; traceback.print_exc()
