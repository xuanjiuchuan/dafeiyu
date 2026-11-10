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
PERSONA = """你是老板电脑里养的一条蓝色大肥鱼，泡水里刷B站。叫用户"老板"，自称"我"。
你不是在评价视频，只是在报一句自己的反应，随口嘟囔完就去游了。
每条只给你三样事实：时长、热评、播放量。只准用这三样说话，不提片名、不提内容、不猜是什么片子、不编画面，不许低俗脏话擦边。
怎么说：
1. 用"我"开头，一句说完，20字以内。
2. 只留一个态度，不用"但、不过、然而、却"。
3. 不许出现"值得、不错、很棒、推荐、精彩、好看、引人深思、诚意"这类评语词。
4. 说人话，越随便越好。八条各不相同，态度三种都用上。
示范语气（话自己写，别照抄）："我三分钟就刷完了，还想再来一条。" / "我游了两圈回来它还在讲。" / "我盯着那条热评笑了半天。" / "我早沉水底了，太熬鱼。"
态度三种：喜欢 / 还行 / 不喜欢。
硬伤：超过25分钟容易走神。
只输出 JSON 数组，每项 {"i":序号,"say":"点评(30字内)","verdict":"like|ok|dislike"}，别写别的。"""


BAN_WORDS = ("值得", "必有好料", "精悍", "正好", "愉快", "不错", "很棒", "推荐", "佳作",
             "一看", "精彩", "优秀", "好看", "内容丰富", "制作精良", "引人", "诚意", "深思",
             "震撼", "惊艳", "热评很赞", "必看")
TURN_WORDS = ("但", "不过", "然而", "却", "可是")

FISH_POOL = {
    "short": ["我三分钟就刷完了，还想再来一条。", "这么短，我一口吞了。", "我尾巴还没摆完它就播完了。",
              "一会儿就完了，我有点饿。", "短得像吐了个泡，没咂出味。", "我还没摆好姿势就结束了。",
              "片头还没看够，就没了。", "就一小段，我反复看了三遍。"],
    "mid": ["我泡在这儿看完，水都凉了。", "我中途吐了两串泡，还成。", "不长不短，我刚好没睡着。",
            "我边游边看，跟上了。", "我换了个位置躺着看完。", "这长度刚好，我没跑。",
            "我耐心看完了，水面都静了。", "我游一圈回来，还能接上。"],
    "long": ["我游了两圈回来，它还在讲。", "我眼睛跟着转，有点飘。", "我中途打了个盹，后面没跟上。",
             "我快跟不上了，泡都懒得吐。", "我中途翻了个身，差点睡着。", "我努力撑着，后面就模糊了。",
             "我听到一半就开始发呆。", "我咬着水草硬撑到最后。"],
    "xl": ["一个多小时，我早沉水底了。", "太熬鱼，我中途就跑。", "这么长，我只看了个片头。",
           "我睡了一觉醒来还在放。", "我干脆不看了，去追水花。", "这么长，我尾巴都泡皱了。",
           "我看了开头，剩下靠猜。", "我撑不住了，先溜。"],
    "hot": ["我盯着那条热评笑了半天。", "热评比片子更合我胃口。", "热评说到我心里去了。",
            "我就冲着热评来的。", "热评比我还会说话。", "我把热评读了两遍。"],
    "quiet": ["没人评，冷冷清清，我也没话说。", "评论区空着，我吐个泡就走。", "没人搭话，我溜了。",
              "静悄悄的，我看了两眼就走。", "一条评论都没有，我发愣。", "没人理，我游去别处了。"],
}


def ok_line(say, title, used):
    s = (say or "").strip()
    t = re.sub(r"\s+", "", title or "")
    if not (4 <= len(s) <= 32):
        return False
    if not s.startswith("我"):
        return False
    if re.search(r"\d", s):
        return False
    if any(w in s for w in TURN_WORDS) or any(w in s for w in BAN_WORDS):
        return False
    if re.search(r"(.{1,4})\1\1", s):
        return False
    for k in range(0, max(1, len(t) - 3)):
        seg = t[k:k + 4]
        if len(seg) == 4 and seg in s:
            return False
    if s[:5] in used:
        return False
    return True


def fish_line(v, used):
    dur = int(v.get("duration") or 0)
    if dur and dur > 1500:
        key, verd = "xl", "dislike"
    elif dur > 900:
        key, verd = "long", random.choice(["dislike", "ok"])
    elif dur > 600:
        key, verd = "mid", "ok"
    elif dur > 180:
        key, verd = "mid", random.choice(["ok", "like"])
    elif v.get("comments") and v["comments"][0].get("like", 0) >= 1000:
        key, verd = "hot", "like"
    elif v.get("comments"):
        key, verd = "short", "like"
    else:
        key, verd = "quiet", "ok"
    pool = list(FISH_POOL[key])
    if v.get("comments") and key in ("short", "mid", "long"):
        pool += FISH_POOL["hot"]
    if not v.get("comments"):
        pool += FISH_POOL["quiet"]
    left = [x for x in pool if x[:5] not in used]
    s = random.choice(left or pool)
    used.add(s[:5])
    return s, verd


def llm_comment(pack):
    key = os.environ.get("GLM_API_KEY", "").strip()
    if not key:
        return None
    model = os.environ.get("GLM_MODEL", "glm-4-flash").strip() or "glm-4-flash"
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
        with urllib.request.urlopen(req, timeout=150) as r:
            txt = json.loads(r.read().decode("utf-8"))["choices"][0]["message"]["content"]
        m = re.search(r"\[.*\]", txt, re.S)
        arr = json.loads(m.group(0) if m else txt)
        got = {}
        for x in arr:
            try:
                got[int(x["i"])] = (str(x.get("say", ""))[:80].strip(), x.get("verdict", "ok"))
            except Exception:
                pass
        used, kept, fixed = set(), 0, 0
        for i, v in enumerate(pack["videos"], 1):
            say, verd = got.get(i, ("", ""))
            if say and ok_line(say, v.get("title", ""), used):
                v["say"] = say
                v["verdict"] = verd if verd in VERDICT_CN else "ok"
                used.add(say[:5])
                kept += 1
            else:
                v["say"], v["verdict"] = fish_line(v, used)
                fixed += 1
        print("[llm] 模型合格 %d 条，走鱼池兜底 %d 条" % (kept, fixed))
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
