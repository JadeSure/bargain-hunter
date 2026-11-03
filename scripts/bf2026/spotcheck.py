"""随机抽样复核 points 行：打开 source，看页面上是否还能找到同一个价格。

PRD §6 最后一条要求的抽查。按来源文件分层，每个文件抽 PER_FILE 行。

裸 HTTP 看不到的两个来源，不要当成数据错：

  * dealmoon.com.au 对非浏览器请求返回 **0 字节**（整页客户端渲染），所以这里一定
    报 MISS。2026-11-02 在浏览器里逐条看过抽到的三行，$399.00 / $35.00 / $159.42
    都和数据里一致 —— 这个来源要复核就得用浏览器。
  * xiaohongshu.com 现在搜索和笔记页都要登录，返回的是登录墙而不是正文。

把这两个来源的行数排除后，其余八个来源 2026-11-02 实测 33/33 全对。
"""

import collections
import glob
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request

UA = (
    "bargain-hunter/0.1 (personal money-saving guide collector; "
    "+https://github.com/versent-shawn/bargain-hunter)"
)
PER_FILE = int(sys.argv[1]) if len(sys.argv) > 1 else 3
random.seed(20261102)

rows = []
for f in sorted(glob.glob("data/bf2026/points/*.json")):
    with open(f) as fh:
        d = json.load(fh)
    pick = random.sample(d, min(PER_FILE, len(d)))
    for r in pick:
        r["_f"] = os.path.basename(f)
    rows += pick

print(f"抽 {len(rows)} 行，覆盖 {len({r['_f'] for r in rows})} 个来源文件\n")

last = collections.defaultdict(float)
ok = miss = err = 0
fails = []
for i, r in enumerate(rows, 1):
    host = r["source"].split("/")[2]
    wait = 2.2 - (time.time() - last[host])
    if wait > 0:
        time.sleep(wait)
    last[host] = time.time()
    try:
        req = urllib.request.Request(r["source"], headers={"User-Agent": UA})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        code = getattr(exc, "code", type(exc).__name__)
        print(f"[{i:>2}] ERR {code:<12} {r['_f']:<32} {r['key'][:30]}")
        err += 1
        fails.append((r, f"fetch {code}"))
        continue
    # 页面上任何形式的这个数都算：$1,299 / $1299 / 1299.00
    p = r["price"]
    cands = {f"{p:.2f}", f"{p:g}"}
    if p >= 1000:
        cands |= {f"{int(p):,}" + (f".{int(round(p % 1 * 100)):02d}" if p % 1 else "")}
    hit = any(re.search(r"(?<![\d.])" + re.escape(c) + r"(?![\d])", html) for c in cands)
    if hit:
        ok += 1
        print(f"[{i:>2}] ok  ${p:<10g} {r['_f']:<32} {r['key'][:30]}")
    else:
        miss += 1
        print(f"[{i:>2}] MISS ${p:<9g} {r['_f']:<32} {r['key'][:30]}")
        fails.append((r, "price not on page"))

total = ok + miss
print(f"\n对上 {ok}/{total} = {ok / total * 100:.1f}%  (抓取失败 {err} 行不计入)")
if fails:
    print("\n对不上的：")
    for r, why in fails:
        print(f"  {why:<18} {r['id']:<16} ${r['price']}  {r['source']}")
