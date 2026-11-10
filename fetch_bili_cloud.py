# -*- coding: utf-8 -*-
"""
大肥鱼 · 云版（GitHub Actions 用）
抓 B 站热门 + 评论区热评，生成手机可看的网页，零账号、零费用。

环境变量（可选）:
  GLM_API_KEY   智谱免费额度 key，有则让鱼自己写点评，无则用规则兜底
  GLM_MODEL     默认 glm-4-flash
  BILI_KEYWORD  关键词搜索，留空则抓全站热门
"""
import json, urllib.request, urllib.parse, http.cookiejar, time, hashlib, random, os, sys, re
from datetime import datetime, timezone, timedelta

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
H = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
     "Accept-Language": "zh-CN,zh;q=0.9"}
CJ = http.cookiejar.CookieJar()
OP = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CJ))
TZ = timezone(timedelta(hours=8))

MIX = [46,47,18,2,53,8,23,32,15,50,10,31,58,3,45,35,27,43,5,49,33,9,42,19,29,28,14,39,12,38,41,13,
       37,48,7,16,24,55,40,61,26,17,0,1,60,51,30,4,22,25,54,21,56,59,6,63,57,62,11,36,20,34,44,52]


def _open(url, referer="https://www.bilibili.com", timeout=20):
    h = dict(H); h["Referer"] = referer
    with OP.open(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def jget(url, referer="https://www.bilibili.com", timeout=20):
    try:
        return json.loads(_open(url, referer, timeout))
    except Exception as e:
        print("[warn] %s %s" % (type(e).__name__, e))
        return {"code": -1}


def warmup():
    try:
        _open("https://www.bilibili.com/", timeout=15)
    except Exception:
        pass


def wbi_sign(params, ik, sk):
    mixin = "".join((ik + sk)[i] for i in MIX)
    p = dict(params); p["wts"] = int(time.time())
    p = {k: "".join(c for c in str(v) if c not in "!'()*") for k, v in sorted(p.items())}
    q = urllib.parse.urlencode(p)
    p["w_rid"] = hashlib.md5((q + mixin).encode()).hexdigest()
    return urllib.parse.urlencode(sorted(p.items()))


def get_videos(limit=8, kw=""):
    if kw:
        nav = jget("https://api.bilibili.com/x/web-interface/nav")
        w = (nav.get("data") or {}).get("wbi_img")
        if w:
            ik = w["img_url"].rsplit("/", 1)[-1].split(".")[0]
            sk = w["sub_url"].rsplit("/", 1)[-1].split(".")[0]
            q = wbi_sign({"search_type": "video", "keyword": kw, "page": 1}, ik, sk)
            d = jget("https://api.bilibili.com/x/web-interface/search/type?" + q,
                     "https://search.bilibili.com/all?keyword=" + urllib.parse.quote(kw))
            res = (d.get("data") or {}).get("result") or []
            if res:
                out = []
                for r in res[:limit]:
                    out.append({
                        "bvid": r.get("bvid"), "aid": r.get("aid"),
                        "title": re.sub(r"<[^>]+>", "", r.get("title") or ""),
                        "owner": r.get("author"), "tname": r.get("typename"),
                        "desc": (r.get("description") or "")[:200],
                        "view": r.get("play"), "like": r.get("like"),
                        "reply": r.get("video_review"), "duration": 0,
                        "keyword": kw
                    })
                return out
        print("[warn] 搜索失败，退回热门流")
    d = jget("https://api.bilibili.com/x/web-interface/popular?ps=%d&pn=1" % max(limit, 8))
    lst = (d.get("data") or {}).get("list") or []
    return [{
        "bvid": v.get("bvid"), "aid": v.get("aid"), "title": v.get("title"),
        "owner": (v.get("owner") or {}).get("name"), "tname": v.get("tname"),
        "desc": (v.get("desc") or "")[:200],
        "view": (v.get("stat") or {}).get("view"), "like": (v.get("stat") or {}).get("like"),
        "reply": (v.get("stat") or {}).get("reply"),
        "duration": v.get("duration") or 0, "keyword": ""
    } for v in lst[:limit]]


def get_comments(aid, bvid):
    for _ in range(2):
        d = jget("https://api.bilibili.com/x/v2/reply?type=1&oid=%s&sort=2&ps=20&pn=1" % aid,
                 "https://www.bilibili.com/video/" + str(bvid))
        reps = ((d.get("data") or {}).get("replies")) or []
        if reps:
            cs = [{"like": r.get("like", 0),
                   "text": (((r.get("content") or {}).get("message")) or "").replace("\n", " ").strip(),
                   "rcount": r.get("rcount", 0)} for r in reps]
            cs.sort(key=lambda x: x["like"], reverse=True)
            return cs
        time.sleep(1.5 + random.random())
    return []


# ---------- 点评：有 key 用模型，无 key 用规则 ----------
PERSONA = """你是老板电脑里养的一条蓝色大肥鱼，整天泡水里刷视频，说话全是大白话。叫用户"老板"，自称"我"。
你只拿到标题、UP主、分区、时长、播放量、热评，没真看过片子，所以不编画面剧情，也不猜题材。标题里的字照原样说。
不许低俗、脏话、擦边。一句话说完，25字以内。
只留一个态度，别用"但、不过、然而、却"这类转折词。
下面是语气的样子，照这个味道说，话得自己写：
- "这我连看两遍，眼睛跟着转。"
- "三分钟就给我看困了，游走了。"
- "评论区比正片好笑。"
- "没太看懂，鱼脑子转不动。"
- "标题起得比片子好听。"
- "挺爽，尾巴拍了一下。"
八条各说各的，别用一个模子，别拿标题当点评。
每条给一个态度：喜欢 / 还行 / 不喜欢，三种都用上。
硬伤：超过25分钟的视频容易走神。
只输出 JSON 数组，每项 {"i":序号,"say":"你的点评(40字内)","verdict":"like|ok|dislike"}，不要任何其他文字。"""


def llm_comment(pack):
    key = os.environ.get("GLM_API_KEY", "").strip()
    if not key:
        return None
    model = os.environ.get("GLM_MODEL", "glm-4.5-flash").strip() or "glm-4.5-flash"
    lines = []
    for i, v in enumerate(pack["videos"], 1):
        c = "；".join("%s(%s赞)" % (x["text"][:50], x["like"]) for x in v["comments"][:3])
        lines.append("%d. 《%s》 UP:%s 分区:%s 时长:%s秒 播放%s | 简介: %s | 热评: %s"
                     % (i, v["title"], v["owner"], v["tname"], v["duration"], v["view"],
                        (v.get("desc") or "无")[:60].replace("\n", " "), c or "无"))
    body = {"model": model, "temperature": 0.95,
            "messages": [{"role": "system", "content": PERSONA},
                         {"role": "user", "content": "今天捞到的鱼食（八条各说各的，别重复句式，别复述标题）：\n" + "\n".join(lines)}]}
    try:
        req = urllib.request.Request(
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
        with urllib.request.urlopen(req, timeout=90) as r:
            txt = json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"]
        m = re.search(r"\[.*\]", txt, re.S)
        arr = json.loads(m.group(0) if m else txt)
        got = {}
        for x in arr:
            got[int(x["i"])] = (str(x.get("say", ""))[:80], x.get("verdict", "ok"))
        for i, v in enumerate(pack["videos"], 1):
            if i in got:
                v["say"], v["verdict"] = got[i]
        print("[llm] 模型点评成功 %d 条" % len(got))
        return True
    except Exception as e:
        print("[llm] 失败，转规则兜底: %s %s" % (type(e).__name__, e))
        return None


def rule_comment(pack):
    for v in pack["videos"]:
        dur = int(v.get("duration") or 0)
        top = v["comments"][0] if v["comments"] else None
        if dur and dur > 1500:
            v["say"] = "太长了，%d分钟。我没看完，说实话。" % (dur // 60)
            v["verdict"] = "ok"
        elif 0 < dur <= 130:
            v["say"] = "短，能一口气看完。评论区比正片还热闹。"
            v["verdict"] = "like"
        elif top and top["like"] >= 1000:
            v["say"] = "评论区第一条有%s个赞，大家都被这句话戳到了。" % top["like"]
            v["verdict"] = "like"
        else:
            v["say"] = "还行，看完没什么想说的。"
            v["verdict"] = "ok"


# ---------- 输出 ----------
VERDICT_CN = {"like": "喜欢", "ok": "还行", "dislike": "不喜欢"}


def build_html(pack):
    today = pack["fetched_at"][:10]
    cards = []
    for i, v in enumerate(pack["videos"], 1):
        dur = int(v.get("duration") or 0)
        durs = ("%d分%d秒" % (dur // 60, dur % 60)) if dur else "—"
        cs = "".join(
            '<li><span class="lk">%s赞</span>%s</li>' % (c["like"], esc(c["text"][:110]))
            for c in v["comments"][:3]) or "<li>评论区没捞到东西</li>"
        cards.append(f"""
<article class="card v-{v.get('verdict','ok')}">
  <div class="idx">{i}</div>
  <h2><a href="https://www.bilibili.com/video/{v['bvid']}" target="_blank">{esc(v['title'])}</a></h2>
  <p class="meta">{esc(str(v['owner']))} · {esc(str(v['tname']))} · {durs} · 播放 {fmt(v['view'])}</p>
  <p class="say">「{esc(v.get('say',''))}」</p>
  <p class="verdict">{VERDICT_CN.get(v.get('verdict','ok'))}</p>
  <ul class="cmts">{cs}</ul>
</article>""")
    stat = {"like": 0, "ok": 0, "dislike": 0}
    for v in pack["videos"]:
        stat[v.get("verdict", "ok")] = stat.get(v.get("verdict", "ok"), 0) + 1
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>大肥鱼日报 {today}</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;padding:16px;background:#0b1220;color:#dbe6f5;
font:16px/1.7 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}}
header{{padding:20px 4px 8px}}
h1{{font-size:22px;margin:0 0 6px;color:#7dc4ff;font-weight:600}}
.sub{{color:#7d8ea8;font-size:13px}}
.stat{{margin:10px 0 18px;font-size:13px;color:#93a7c0}}
.stat b{{color:#7dc4ff}}
.card{{background:#131e30;border-radius:14px;padding:16px;margin:0 0 14px;position:relative;
border-left:4px solid #3a4d68}}
.card.v-like{{border-left-color:#38b96a}}
.card.v-dislike{{border-left-color:#6b7a90;opacity:.85}}
.idx{{position:absolute;right:14px;top:12px;color:#2f4258;font-size:26px;font-weight:700}}
h2{{font-size:16px;margin:0 34px 6px 0;line-height:1.5}}
h2 a{{color:#e8f1ff;text-decoration:none}}
.meta{{margin:0 0 10px;color:#7d8ea8;font-size:12px}}
.say{{margin:0 0 8px;color:#ffe08a;font-size:15px}}
.verdict{{margin:0 0 10px;font-size:12px;color:#8fa6c2}}
.v-like .verdict{{color:#4fd285}}
.cmts{{margin:0;padding:0;list-style:none;border-top:1px dashed #24344b;padding-top:8px}}
.cmts li{{font-size:13px;color:#9fb2c9;margin:5px 0}}
.lk{{color:#e0a05a;margin-right:6px;font-size:12px}}
footer{{padding:18px 4px 40px;color:#5d6d84;font-size:12px;text-align:center}}
</style></head><body>
<header>
  <h1>大肥鱼日报</h1>
  <div class="sub">{today} · 捞于 {pack['fetched_at'][11:16]}</div>
  <div class="stat">吃了 <b>{len(pack['videos'])}</b> 条 · 喜欢 <b>{stat['like']}</b> · 还行 <b>{stat['ok']}</b> · 不喜欢 <b>{stat['dislike']}</b></div>
</header>
{''.join(cards)}
<footer>只读抓取 · 零账号 · 不评论不点赞<br>鱼在 GitHub 上自己觅食</footer>
</body></html>"""


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def fmt(n):
    try:
        n = int(n)
    except Exception:
        return "—"
    return ("%.1f万" % (n / 10000.0)) if n >= 10000 else str(n)


def build_md(pack):
    out = ["# 大肥鱼日报 · %s" % pack["fetched_at"][:10], ""]
    for i, v in enumerate(pack["videos"], 1):
        out.append("## %d. %s" % (i, v["title"]))
        out.append("%s ｜ %s ｜ 播放 %s" % (v["owner"], v["tname"], fmt(v["view"])))
        out.append("")
        out.append("> %s" % v.get("say", ""))
        out.append("")
        out.append("**%s**" % VERDICT_CN.get(v.get("verdict", "ok")))
        for c in v["comments"][:3]:
            out.append("- %s赞：%s" % (c["like"], c["text"][:100]))
        out.append("")
    return "\n".join(out)


def main():
    limit = int(os.environ.get("LIMIT", "8"))
    kw = os.environ.get("BILI_KEYWORD", "").strip()
    warmup()
    vids = get_videos(limit, kw)
    print("[list] %d 条 (kw=%s)" % (len(vids), kw or "热门"))
    if not vids:
        print("[abort] 一条都没捞到，保留昨天的页面不动")
        sys.exit(0)
    for i, v in enumerate(vids, 1):
        v["comments"] = get_comments(v["aid"], v["bvid"])
        print("[%d/%d] %s 评论%d" % (i, len(vids), (v["title"] or "")[:24], len(v["comments"])))
        time.sleep(1.2 + random.random() * 0.8)

    now = datetime.now(TZ)
    pack = {"fetched_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "keyword": kw, "count": len(vids), "videos": vids}
    if not llm_comment(pack):
        rule_comment(pack)

    os.makedirs("data", exist_ok=True)
    os.makedirs("daily", exist_ok=True)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(build_html(pack))
    with open(os.path.join("daily", now.strftime("%Y-%m-%d") + ".md"), "w", encoding="utf-8") as f:
        f.write(build_md(pack))
    with open(os.path.join("data", "latest.json"), "w", encoding="utf-8") as f:
        json.dump(pack, f, ensure_ascii=False, indent=1)
    print("[OK] index.html + daily/%s.md + data/latest.json" % now.strftime("%Y-%m-%d"))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
