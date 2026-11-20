#!/usr/bin/env python3
"""验证合并成品：时长、分辨率、帧率、解码错误数、最大GOP、首尾帧截图。"""
import subprocess, sys, os

FFMPEG='/usr/bin/ffmpeg'
FFPROBE='/usr/bin/ffprobe'

def probe(path):
    out=subprocess.check_output([FFPROBE,'-v','error','-select_streams','v:0',
        '-show_entries','stream=width,height,r_frame_rate,codec_name',
        '-show_entries','format=duration,size','-of','default=noprint_wrappers=1',path],text=True)
    return dict(l.strip().split('=',1) for l in out.strip().splitlines() if '=' in l)

def decode_errors(path):
    r=subprocess.run([FFMPEG,'-v','error','-i',path,'-f','null','-'],
                     capture_output=True,text=True)
    lines=[l for l in r.stderr.splitlines() if l.strip()]
    return len(lines), lines[:5]

def max_gop(path):
    out=subprocess.check_output([FFPROBE,'-v','error','-skip_frame','nokey',
        '-select_streams','v:0','-show_entries','frame=best_effort_timestamp_time',
        '-of','csv=p=0',path],text=True)
    ts=[float(x.strip().rstrip(',')) for x in out.splitlines() if x.strip() and x.strip()[0].isdigit()]
    if len(ts)<2: return None
    gaps=[ts[i+1]-ts[i] for i in range(len(ts)-1)]
    return max(gaps), len(ts)

def frame_at(path, t, outpng):
    subprocess.run([FFMPEG,'-v','error','-ss',str(t),'-i',path,'-frames:v','1',
                    '-y',outpng],check=True)

if __name__=='__main__':
    for path in sys.argv[1:]:
        print('='*60)
        print('文件:',os.path.basename(path))
        p=probe(path)
        dur=float(p.get('duration',0))
        size=int(p.get('size',0))/1024/1024
        print(f"  时长 {dur/60:.1f} 分 ({dur:.0f}s)  大小 {size:.0f} MB  "
              f"{p.get('width')}x{p.get('height')} {p.get('r_frame_rate')} {p.get('codec_name')}")
        ne, sample=decode_errors(path)
        print(f"  解码错误: {ne}", ("样例: "+str(sample) if ne else ""))
        g=max_gop(path)
        if g: print(f"  最大GOP: {g[0]:.2f}s (关键帧 {g[1]} 个)")
        base=os.path.splitext(path)[0]
        frame_at(path, 3, base+'_head.png')
        frame_at(path, max(0,dur-3), base+'_tail.png')
        print(f"  首尾截图: {base}_head.png / {base}_tail.png")
