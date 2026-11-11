# -*- coding: utf-8 -*-
"""
大肥鱼 · 纯云端版（抖音热榜）
不依赖任何本地设备：GitHub Actions 定时跑，结果推到 Pages，手机电脑全关也能看。

环境变量（可选）:
  GLM_API_KEY   智谱 key，有则让鱼自己写点评，没有就用规则兜底
  GLM_MODEL     默认 glm-4-flash
  PICK          每天入选条数，默认 10
  OUT_ROOT      输出根目录，默认脚本所在目录（Actions 里即仓库根）
"""
import json, os, re, ssl, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
TZ = timezone(timedelta(hours=8))
NOW = datetime.now(TZ)
TODAY = NOW.strftime("%Y-%m-%d")
STAMP = NOW.strftime("%Y-%m-%d %H:%M")

PICK = int(os.environ.get("PICK", "10"))
GLM_API_KEY = (os.environ.get("GLM_API_KEY") or "").strip()
GLM_MODEL = (os.environ.get("GLM_MODEL") or "glm-4-flash").strip()
OUT_ROOT = os.environ.get("OUT_ROOT") or os.path.dirname(os.path.abspath(__file__))

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

WEB_API = ("https://www.douyin.com/aweme/v1/web/hot/search/list/"
           "?device_platform=webapp&aid=6383&channel=channel_pc_web&detail_list=1")
IES_API = "https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/"


def fetch(url, referer, timeout=25):
    h = {"User-Agent": UA, "Referer": referer,
         "Accept": "application/json, text/html, */*",
         "Accept-Language": "zh-CN,zh;q=0.9"}
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.status, r.read()


def norm(item):
    """统一 web / ies 两种返回结构"""
    cover = ""
    wc = item.get("word_cover") or {}
    urls = wc.get("url_list") or []
    if urls:
        cover = urls[0]
    sid = str(item.get("sentence_id") or "")
    return {
        "word": (item.get("word") or item.get("word_name") or "").strip(),
        "hot": int(item.get("hot_value") or item.get("hot_value_for") or 0),
        "cover": cover,
        "sid": sid,
        "videos": int(item.get("video_count") or 0),
        "discuss": int(item.get("discuss_video_count") or 0),
        "label": int(item.get("label") or 0),
        "pos": int(item.get("position") or 0),
        "url": ("https://www.douyin.com/hot/%s" % sid) if sid else "https://www.douyin.com/hot",
    }


def get_hotlist():
    for name, url, ref in (("web", WEB_API, "https://www.douyin.com/"),
                           ("ies", IES_API, "https://www.iesdouyin.com/")):
        try:
            st, body = fetch(url, ref)
            j = json.loads(body.decode("utf-8", "ignore"))
            data = j.get("data") or j
            wl = data.get("word_list") or data.get("hot_search") or []
            rows = [norm(x) for x in wl if norm(x)["word"]]
            print("[%s] status=%s 拿到 %d 条" % (name, st, len(rows)))
            if rows:
                return rows
        except Exception as e:
            print("[%s] 失败 %s %s" % (name, type(e).__name__, e))
    return []


def pick(rows, n):
    seen, out = set(), []
    for r in sorted(rows, key=lambda x: -x["hot"]):
        if r["word"] in seen:
            continue
        # 广告位 label=5 跳掉；纯无封面无视频的也跳
        if r["label"] == 5:
            continue
        seen.add(r["word"])
        out.append(r)
        if len(out) >= n:
            break
    return out


# ---------- 点评 ----------
FALLBACK = ["这个我刷到了。", "有点意思。", "不太懂，但看完了。", "热度挺高。", "没什么感觉。"]


def rule_say(i, item):
    v = item["videos"]
    if v >= 20:
        return "讨论的人很多。我看了几条。"
    if v >= 5:
        return "视频不少。我随手翻完了。"
    return FALLBACK[i % len(FALLBACK)]


def glm_say(items):
    if not GLM_API_KEY:
        print("[glm] 没配 key，用规则兜底")
        return None
    lines = "\n".join("%d. %s（热度%d，相关视频%d条）" % (i + 1, x["word"], x["hot"], x["videos"])
                      for i, x in enumerate(items))
    prompt = (
        "你是大肥鱼，一只蓝色的鱼，正在刷抖音热榜。对下面每条内容写一句点评。\n"
        "规则：自称我，称对方老板；短句，多用句号，少用感叹号；不用表情符号、不用网络烂梗、"
        "不说“作为一个AI”；每条点评不超过 20 个字；态度只能从 喜欢/还行/不喜欢 里选一个。\n"
        "只输出 JSON 数组，不要解释，格式：[{\"i\":1,\"say\":\"...\",\"attitude\":\"喜欢\"}]\n\n"
        "内容：\n" + lines
    )
    body = json.dumps({"model": GLM_MODEL, "temperature": 0.8,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(
        "https://open.bigmodel.cn/api/paas/v4/chat/completions", data=body,
        headers={"Authorization": "Bearer " + GLM_API_KEY,
                 "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            j = json.loads(r.read().decode("utf-8", "ignore"))
        txt = j["choices"][0]["message"]["content"]
        m = re.search(r"\[.*\]", txt, re.S)
        arr = json.loads(m.group(0) if m else txt)
        print("[glm] 点评 %d 条" % len(arr))
        return {int(a["i"]): (str(a.get("say", "")).strip()[:40],
                              str(a.get("attitude", "还行")).strip()) for a in arr}
    except Exception as e:
        print("[glm] 失败 %s %s → 规则兜底" % (type(e).__name__, e))
        return None


# ---------- 页面 ----------
TPL = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>大肥鱼日报 · 抖音热榜</title>
<style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;padding:0 0 40px;background:#0f1420;color:#e8eef7;
font:16px/1.55 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
header{padding:22px 18px 14px;border-bottom:1px solid #1e2838}
h1{margin:0 0 6px;font-size:20px;font-weight:600;letter-spacing:.5px}
.meta{font-size:13px;color:#7d8ba3}
.fish{display:inline-block;width:9px;height:9px;border-radius:50%;background:#3fa9f5;margin-right:7px;
vertical-align:middle;box-shadow:0 0 10px #3fa9f5}
.list{padding:10px 14px}
.card{display:flex;gap:12px;padding:13px 12px;margin-bottom:10px;border-radius:14px;
background:#161d2c;border:1px solid #1f2a3d}
.rank{flex:0 0 26px;font-size:15px;font-weight:700;color:#4c5a72;padding-top:2px}
.rank.top{color:#ff8a3d}
.thumb{flex:0 0 64px;height:64px;border-radius:10px;background:#0b1018 center/cover no-repeat;overflow:hidden}
.body{flex:1;min-width:0}
.t{font-size:15px;font-weight:600;margin:0 0 5px;color:#eaf2ff;text-decoration:none;display:block}
.t:active{opacity:.6}
.say{font-size:13.5px;color:#8fa3bf;margin:0 0 6px}
.say b{color:#3fa9f5;font-weight:600}
.tag{display:inline-block;font-size:11.5px;color:#6c7d96;border:1px solid #24314a;
border-radius:6px;padding:1px 6px;margin-right:6px}
.tag.hot{color:#ff8a3d;border-color:#3d2a1c}
footer{padding:18px;text-align:center;font-size:12px;color:#4d5a70;line-height:1.8}
</style></head><body>
<header><h1><span class="fish"></span>大肥鱼日报 · 抖音热榜</h1>
<div class="meta">__STAMP__ 捞到的 · 共 __COUNT__ 条 · 我只看不评论不点赞</div></header>
<div class="list">
__ITEMS__
</div>
<footer>云端自动生成，电脑和手机都不用开。<br>点标题进抖音话题页看视频。</footer>
</body></html>"""

CARD = """<div class="card">
<div class="rank__RANKCLS__">__RANK__</div>
<div class="thumb" style="background-image:url('__COVER__')"></div>
<div class="body">
<a class="t" href="__URL__" target="_blank" rel="noopener">__WORD__</a>
<p class="say"><b>大肥鱼：</b>__SAY__ <span style="color:#5b6b85">（__ATT__）</span></p>
<div><span class="tag hot">热度 __HOT__</span><span class="tag">视频 __VID__</span></div>
</div></div>"""


def human(n):
    if n >= 100000000:
        return "%.1f亿" % (n / 100000000.0)
    if n >= 10000:
        return "%.1f万" % (n / 10000.0)
    return str(n)


def render(items, says):
    cards = []
    for i, it in enumerate(items):
        say, att = says.get(i + 1, (rule_say(i, it), "还行"))
        cards.append(CARD
                     .replace("__RANKCLS__", " top" if i < 3 else "")
                     .replace("__RANK__", str(i + 1))
                     .replace("__COVER__", it["cover"].replace("'", "%27"))
                     .replace("__URL__", it["url"])
                     .replace("__WORD__", it["word"].replace("<", "&lt;"))
                     .replace("__SAY__", say.replace("<", "&lt;"))
                     .replace("__ATT__", att)
                     .replace("__HOT__", human(it["hot"]))
                     .replace("__VID__", str(it["videos"])))
    return (TPL.replace("__STAMP__", STAMP)
            .replace("__COUNT__", str(len(items)))
            .replace("__ITEMS__", "\n".join(cards)))


def main():
    rows = get_hotlist()
    if not rows:
        print("[err] 热榜一条都没拿到，本轮跳过，不覆盖已有页面")
        sys.exit(0)

    items = pick(rows, PICK)
    says = glm_say(items) or {}

    for i, it in enumerate(items):
        say, att = says.get(i + 1, (rule_say(i, it), "还行"))
        print("%2d. %s | %s → %s（%s）" % (i + 1, it["word"], human(it["hot"]), say, att))

    base = os.path.join(OUT_ROOT, "douyin")
    os.makedirs(os.path.join(base, "archive"), exist_ok=True)
    os.makedirs(os.path.join(OUT_ROOT, "data"), exist_ok=True)

    html = render(items, says)
    with open(os.path.join(base, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)

    payload = {"date": TODAY, "stamp": STAMP, "source": "douyin_hotsearch",
               "count": len(items),
               "items": [dict(it, say=says.get(i + 1, (rule_say(i, it), "还行"))[0],
                              attitude=says.get(i + 1, (rule_say(i, it), "还行"))[1])
                         for i, it in enumerate(items)]}
    for p in (os.path.join(OUT_ROOT, "data", "douyin_latest.json"),
              os.path.join(base, "archive", TODAY + ".json")):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    print("[ok] 页面已生成 douyin/index.html，共 %d 条" % len(items))


if __name__ == "__main__":
    main()
