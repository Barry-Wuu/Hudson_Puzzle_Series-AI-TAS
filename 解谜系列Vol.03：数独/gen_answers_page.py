#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 Vol.3 答案页 answers.html（数字 emoji 盘面，行内单空格 / 行间换行）。"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'validation', 'puzzles.json')
# 站点目录：默认 /workspace/vol3_site，可用环境变量 SITE 覆盖
OUT = os.path.join(os.environ.get('SITE', '/workspace/vol3_site'), 'answers.html')

EMOJI = {i: '%d\ufe0f\u20e3' % i for i in range(1, 10)}


def grid_html(sol, w, h):
    rows = []
    for i in range(h):
        row = sol[i * w:(i + 1) * w]
        groups = [row[j:j + 3] for j in range(0, w, 3)]
        rows.append(' '.join(''.join(EMOJI[v] for v in g) for g in groups))
        # 每 3 行（一个大行）之间空一行
        if (i + 1) % 3 == 0 and i != h - 1:
            rows.append('')
    return '\n'.join(rows)


def main():
    data = json.load(open(SRC, encoding='utf-8'))
    diffs = []
    for r in data:
        if r['diff'] not in diffs:
            diffs.append(r['diff'])

    counts = {d: sum(1 for r in data if r['diff'] == d) for d in diffs}

    tabs = ''.join(
        '<button class="tab%s" data-d="%s">%s<span>%d 問</span></button>'
        % (' on' if i == 0 else '', d, d, counts[d])
        for i, d in enumerate(diffs)
    )

    secs = []
    for d in diffs:
        recs = [r for r in data if r['diff'] == d]
        cards = []
        for r in recs:
            cards.append(
                '<article class="pz" data-idx="%d" data-d="%s">'
                '<h2>第%03d問</h2><pre>%s</pre></article>'
                % (r['idx'], d, r['idx'], grid_html(r['solution'], r['w'], r['h']))
            )
        secs.append(
            '<section class="grp" data-d="%s"><h3 class="gh">%s · %d 問</h3>'
            '<div class="grid">%s</div></section>' % (d, d, len(recs), ''.join(cards))
        )

    html = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vol.3 数独 · 全 300 关答案（数字 emoji）</title>
<style>
*{box-sizing:border-box}
body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;margin:0;background:#0f1216;color:#d9dee6;-webkit-font-smoothing:antialiased}
main{max-width:1080px;margin:0 auto;padding:30px 18px 80px}
h1{font-size:21px;margin:0 0 8px;color:#e8eef7}
.lead{color:#7f8b9c;font-size:12.5px;line-height:1.9;margin:0 0 16px}
.lead b{color:#b9c7d8}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:#161b22;border:1px solid #232b36;border-radius:12px;padding:12px 14px;margin-bottom:18px;position:sticky;top:0;z-index:5}
.tab{background:#11161e;border:1px solid #232b36;color:#9fb0c4;font:inherit;font-size:12.5px;padding:7px 13px;border-radius:8px;cursor:pointer;display:flex;gap:7px;align-items:center}
.tab span{font-size:10.5px;color:#6f7d90;font-variant-numeric:tabular-nums}
.tab.on{background:#1a7f37;border-color:#1a7f37;color:#fff;font-weight:700}
.tab.on span{color:#cdebd7}
.jump{margin-left:auto;display:flex;gap:6px;align-items:center;font-size:12px;color:#7f8b9c}
.jump input{width:78px;background:#0b0f14;border:1px solid #2b3646;color:#d9dee6;border-radius:7px;padding:6px 8px;font:inherit;font-size:12px;text-align:center;font-variant-numeric:tabular-nums}
.jump input:focus{outline:none;border-color:#3f6fa8}
.jump button{background:#22303f;border:1px solid #2b394b;color:#b8c6d8;border-radius:7px;padding:6px 11px;font:inherit;font-size:12px;cursor:pointer}
.gh{font-size:13px;color:#8ab4f8;margin:22px 0 10px;font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(225px,1fr));gap:11px}
.pz{background:#161b22;border:1px solid #232b36;border-radius:11px;padding:11px 12px}
.pz.hit{border-color:#f0b429;box-shadow:0 0 0 2px rgba(240,180,41,.18)}
.pz h2{font-size:12px;color:#8ab4f8;margin:0 0 7px;font-weight:600;font-variant-numeric:tabular-nums}
.pz pre{margin:0;font-family:"Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji",system-ui,sans-serif;font-size:14px;line-height:1.9;white-space:pre;overflow-x:auto;color:#e8eef7}
.foot{font-size:12px;color:#68758a;line-height:1.95;margin-top:30px;border-top:1px solid #232b36;padding-top:15px}
.foot a{color:#8ab4f8;text-decoration:none}
.foot a:hover{text-decoration:underline}
@media(max-width:640px){
  main{padding:20px 12px 60px}
  .grid{grid-template-columns:1fr;gap:10px}
  .pz{padding:10px 12px}
  .pz pre{font-size:14px;line-height:1.95}
  .jump{margin-left:0;width:100%}
  .jump input{flex:1;width:auto}
}
@media(max-width:400px){
  .pz pre{font-size:13px;line-height:1.9}
}
</style></head><body><main>
<h1>Vol.3 数独 · 全 300 关答案</h1>
<p class="lead">每格用<b>数字 emoji</b>（1️⃣~9️⃣）表示：<b>同一个 3×3 宫内三格连写、宫内不留空格；宫与宫之间一个空格；每 3 行之间空一行（大行分隔）</b>，9 行读完即完整解。答案来自 ROM 内现成数据表，开录前一次性静态提取，非现场求解。<br>点击难度切换，或用右侧输入框跳到指定关号（1–300）。</p>
<div class="bar">__TABS__
<div class="jump"><input id="q" type="number" min="1" max="300" placeholder="关号"><button id="go">跳转</button></div>
</div>
<div id="wrap">__SECS__</div>
<div class="foot">
盘面顺序与录播一致：やさしい 001–070 → ふつう 071–210 → むずかしい 211–300。<br>
原文下载：<a href="files/答案.md?dl=1" download>答案.md</a>（同一份 emoji 盘面）｜存档：<a href="files/vol3.dsv?dl=1" download>vol3.dsv</a>（全 300 关通关）· <a href="files/vol3_all_ranks.dsv?dl=1" download>vol3_all_ranks.dsv</a>（+ 四段位全认定）<br>
<a href="index.html">← 返回录播总览</a>
</div>
</main>
<script>
const tabs=[...document.querySelectorAll('.tab')];
const grps=[...document.querySelectorAll('.grp')];
function show(d){grps.forEach(g=>g.style.display=(g.dataset.d===d?'':'none'));
  tabs.forEach(t=>t.classList.toggle('on',t.dataset.d===d));}
tabs.forEach(t=>t.addEventListener('click',()=>show(t.dataset.d)));
document.getElementById('go').addEventListener('click',()=>{
  const n=parseInt(document.getElementById('q').value,10);
  if(!(n>=1&&n<=300))return;
  const card=document.querySelector('.pz[data-idx="'+n+'"]');
  if(!card)return;
  show(card.dataset.d);
  document.querySelectorAll('.pz.hit').forEach(e=>e.classList.remove('hit'));
  card.classList.add('hit');
  card.scrollIntoView({block:'center',behavior:'smooth'});
  setTimeout(()=>card.classList.remove('hit'),2600);
});
</script>
</body></html>
"""
    html = html.replace('__TABS__', tabs).replace('__SECS__', ''.join(secs))
    open(OUT, 'w', encoding='utf-8').write(html)
    print('写出', OUT, os.path.getsize(OUT), 'bytes | 关卡', len(data), '| 难度', counts)


if __name__ == '__main__':
    main()
