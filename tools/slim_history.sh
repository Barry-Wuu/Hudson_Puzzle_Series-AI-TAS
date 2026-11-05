#!/usr/bin/env bash
# 仓库历史瘦身工具（手动档）。
#
# 两档能力：
#   1) 安全档  gc     —— 重新打包对象、删除冗余/不可达对象。绝不改提交内容，本地操作，无需强推。
#   2) 重写档  filter  —— 用 git-filter-repo 从历史里剔除指定文件（如视频/大二进制）。会改写
#                        提交哈希，必须强推远程，且协作方需重新 clone。属破坏性操作，默认只 dry-run。
#
# 用法：
#   ./tools/slim_history.sh gc                # 安全收紧（推荐日常维护）
#   ./tools/slim_history.sh analyze           # 列出历史里最大的 blob（看清是什么在占空间）
#   ./tools/slim_history.sh filter --dry-run  # 预览会被剔除的文件（不改动）
#   ./tools/slim_history.sh filter --apply    # 真正改写历史（需后续强推，谨慎！）
#
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

cmd="${1:-gc}"; shift || true
DRY=1; APPLY=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1; APPLY=0;;
    --apply)   DRY=0; APPLY=1;;
  esac
done

case "$cmd" in
  gc)
    echo "==> git gc --prune=now （重新打包，删除不可达/冗余对象）"
    git -c gc.reflogExpire=now -c gc.reflogExpireUnreachable=now gc --prune=now
    echo "==> 现状："
    du -sh .git
    git count-objects -vH | grep -E '^(count|size|packs|size-pack):'
    ;;

  analyze)
    echo "==> 历史中最大的 blob（解压体积 / 路径）："
    python3 - <<'PY'
import subprocess
out = subprocess.run(['git','rev-list','--objects','--all'],capture_output=True,text=True).stdout
sha2path={}
for ln in out.splitlines():
    p=ln.split(' ',1)
    if len(p)==2 and p[1].strip(): sha2path[p[0]]=p[1].strip()
if not sha2path:
    print("  (无路径信息，可能浅克隆)"); raise SystemExit
shas=list(sha2path)
batch=subprocess.run(['git','cat-file','--batch-check=%(objectname) %(objecttype) %(objectsize)'],
    input='\n'.join(shas)+'\n',capture_output=True,text=True).stdout
rows=[]
for ln in batch.splitlines():
    f=ln.split()
    if len(f)==3 and f[1]=='blob':
        try: rows.append((int(f[2]),sha2path.get(f[0],'?'),f[0]))
        except: pass
rows.sort(reverse=True)
for sz,path,sha in rows[:25]:
    print(f"  {sz/1048576:7.2f} MB  {path}")
print(f"  共 {len(rows)} 个 blob（带路径）")
PY
    ;;

  filter)
    # 要剔除的模式：视频 + 大音频二进制。可在此增删。
    PATTERNS=(
      '--path-glob' '*.mp4'  '--path-glob' '*.mkv'  '--path-glob' '*.avi'
      '--path-glob' '*.mov'  '--path-glob' '*.webm' '--path-glob' '*.flv'
      '--path-glob' '*.wmv'  '--path-glob' '*.mpg'  '--path-glob' '*.mpeg'
    )
    if [ "$APPLY" -eq 0 ]; then
      echo "==> [dry-run] 预览将剔除的视频类文件（不改动历史）："
      # dry-run：用 analyze 思路列出匹配路径
      python3 - "${PATTERNS[@]}" <<'PY'
import subprocess, sys
pats=set(sys.argv[1:])
exts={p[1:].lower() for p in pats if p.startswith('*.')}
out=subprocess.run(['git','rev-list','--objects','--all'],capture_output=True,text=True).stdout
hit=set()
for ln in out.splitlines():
    p=ln.split(' ',1)
    if len(p)==2 and p[1].strip():
        path=p[1].strip()
        e=path.rsplit('.',1)[-1].lower() if '.' in path else ''
        if e in exts: hit.add(path)
if not hit:
    print("  历史中没有匹配的视频文件 —— 无需剔除。")
else:
    for h in sorted(hit): print("  -",h)
PY
      echo "==> 确认无误后加 --apply 执行（会改写历史，需强推）。"
    else
      echo "⚠️  即将用 git-filter-repo 改写历史并剔除视频类文件。"
      read -r -p "确认执行？(输入 YES 继续): " ans
      [ "$ans" = "YES" ] || { echo "已取消。"; exit 1; }
      echo "==> 备份当前分支 ref 到 refs/pre-filter-backup/*"
      git for-each-ref --format='%(refname)' refs/heads | while read r; do
        b="${r#refs/heads/}"; git update-ref "refs/pre-filter-backup/$b" "$r"
      done
      echo "==> 执行 git filter-repo"
      git filter-repo "${PATTERNS[@]}" --force
      echo "==> 完成。下一步：git push --force --all  （并通知协作者重新 clone）"
      echo "    如需回滚：git for-each-ref --format='%(refname)' refs/pre-filter-backup | ..."
    fi
    ;;

  *)
    echo "用法: $0 {gc|analyze|filter [--dry-run|--apply]}"
    exit 1
    ;;
esac
