#!/usr/bin/env bash
# seg4 录制完成后的自动后处理：等 4 段 mp4 齐全 -> 逐段裁剪(选关0.5s+save剪净) -> 合并 -> 写 /tmp/seg4_DONE
# 由 supervisord 托管(seg4post)，与录制同树，会话回收后自动续跑。
set -u
AIDIR="/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
OUTBASE="/workspace/数墙_seg4"
TRIMDIR="/workspace/_seg4_trim"
DONE="/tmp/seg4_DONE"
LOG="/tmp/seg4_post.log"
FF="$(command -v ffmpeg)"
FP="$(command -v ffprobe)"
mkdir -p "$TRIMDIR"
SEGS="1 2 3 4"

echo "$(date) seg4_post start (ff=$FF fp=$FP)" >> "$LOG"

# 幂等：已完成则直接退出，避免 supervisord 重启后重跑
if [ -f "$DONE" ]; then echo "$(date) DONE already exists, exit" >> "$LOG"; exit 0; fi

state_of(){
  python3.11 - <<'PY'
import socket,re
SOCK='/.PlnPyKFp4CRfFtgC1_run/cs-supervisor.sock'
def rpc(method,params=None):
    params=params or []
    def p(v):
        if isinstance(v,bool): return '<param><value><boolean>%d</boolean></value></param>'%(1 if v else 0)
        return '<param><value><string>%s</string></value></param>'%v
    body=('<?xml version="1.0"?><methodCall><methodName>%s</methodName><params>%s</params></methodCall>'%(method,''.join(p(x) for x in params))).encode()
    req=('POST /RPC2 HTTP/1.1\r\nHost: localhost\r\nContent-Type: text/xml\r\nContent-Length: %d\r\nConnection: close\r\n\r\n'%len(body)).encode()+body
    s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); s.connect(SOCK); s.sendall(req)
    buf=b''
    while True:
        d=s.recv(65536)
        if not d: break
        buf+=d
        if b'</methodResponse>' in buf: break
    s.close(); return buf.decode(errors='replace')
xml=rpc('supervisor.getProcessInfo',['seg4rec'])
m=re.search(r'<name>state</name><value><int>([^<]*)', xml)
print(m.group(1) if m else '0')
PY
}

# ---- 等录制全部完成：4 段 mp4 都在 + mtime 稳定 60s ----
while true; do
  ready=1
  for N in $SEGS; do
    f="$OUTBASE"_p$N.mp4
    [ -s "$f" ] || ready=0
  done
  if [ "$ready" = "1" ]; then
    ok=1
    for N in $SEGS; do
      f="$OUTBASE"_p$N.mp4
      a=$(stat -c %Y "$f"); sleep 5; b=$(stat -c %Y "$f")
      [ "$a" = "$b" ] || ok=0
    done
    if [ "$ok" = "1" ]; then echo "$(date) all 4 segments present & stable, begin post" >> "$LOG"; break; fi
  fi
  echo "$(date) wait ready=$ready" >> "$LOG"
  sleep 60
done

# ---- 逐段裁剪 ----
for N in $SEGS; do
  in="$OUTBASE"_p$N.mp4
  out="$TRIMDIR/seg4_p${N}_trim.mp4"
  echo "$(date) trim p$N" >> "$LOG"
  python3.11 "$AIDIR/trim_select_save.py" "$in" "$out" >> "$LOG" 2>&1
  echo "$(date) trim p$N rc=$?" >> "$LOG"
done

# ---- 合并(重编码确保无缝) ----
INS=""
for N in $SEGS; do INS="$INS -i $TRIMDIR/seg4_p${N}_trim.mp4"; done
FLT="[0:v][0:a][1:v][1:a][2:v][2:a][3:v][3:a]concat=n=4:v=1:a=1[v][a]"
echo "$(date) merge" >> "$LOG"
"$FF" -y -hide_banner -loglevel warning $INS -filter_complex "$FLT" -map "[v]" -map "[a]" \
  -c:v libopenh264 -b:v 3000k -pix_fmt yuv420p -c:a aac -b:a 160k -movflags +faststart \
  /workspace/数墙_seg4_final.mp4 >> "$LOG" 2>&1
echo "$(date) merge rc=$?" >> "$LOG"

# ---- 校验时长 ----
DUR=$("$FP" -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 /workspace/数墙_seg4_final.mp4 2>/dev/null)
echo "$(date) final duration(s)=$DUR" >> "$LOG"

date > "$DONE"
echo "$(date) ALL DONE -> $DONE" >> "$LOG"
