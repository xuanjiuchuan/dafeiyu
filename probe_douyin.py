# -*- coding: utf-8 -*-
"""云端探测：GitHub Actions 的 IP 能否在无登录态下拿到抖音数据。"""
import json, urllib.request, urllib.error, ssl, re, sys

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

TARGETS = [
    ("抖音热榜-web", "https://www.douyin.com/aweme/v1/web/hot/search/list/?device_platform=webapp&aid=6383&channel=channel_pc_web&detail_list=1", "https://www.douyin.com/"),
    ("抖音热榜-旧ies", "https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/", "https://www.iesdouyin.com/"),
    ("分享页-SSR", "https://www.iesdouyin.com/share/video/7673446541528550665/", "https://www.iesdouyin.com/"),
    ("recommend-feed", "https://www.douyin.com/aweme/v1/web/tab/feed/?device_platform=webapp&aid=6383&channel=channel_pc_web&count=10", "https://www.douyin.com/"),
    ("discover页面", "https://www.douyin.com/discover", "https://www.douyin.com/"),
    ("tophub抖音热榜", "https://tophub.today/n/K7GdaMgdQy", "https://tophub.today/"),
]


def probe(name, url, ref):
    h = {"User-Agent": UA, "Referer": ref,
         "Accept": "application/json, text/html, */*",
         "Accept-Language": "zh-CN,zh;q=0.9"}
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=25, context=CTX)
        body = r.read()
        txt = body.decode("utf-8", "ignore")
        flags = []
        for k in ("word_list", "aweme_list", "hot_search", "RENDER_DATA", "_ROUTER_DATA",
                  "aweme_id", "desc", "digg_count", "verify", "captcha"):
            if k in txt:
                flags.append(k)
        print("[%s] status=%s bytes=%d flags=%s" % (name, r.status, len(body), ",".join(flags)))
        head = re.sub(r"\s+", " ", txt[:260])
        print("    head: %s" % head)
        # 若是 JSON 就打印顶层键
        try:
            j = json.loads(txt)
            if isinstance(j, dict):
                print("    json_keys: %s" % list(j.keys())[:12])
                d = j.get("data")
                if isinstance(d, dict):
                    print("    data_keys: %s" % list(d.keys())[:12])
        except Exception:
            pass
    except urllib.error.HTTPError as e:
        body = e.read()[:200].decode("utf-8", "ignore")
        print("[%s] HTTP %s | %s" % (name, e.code, re.sub(r"\s+", " ", body)))
    except Exception as e:
        print("[%s] ERR %s %s" % (name, type(e).__name__, e))


print("=== python", sys.version.split()[0], "===")
for n, u, r in TARGETS:
    probe(n, u, r)
    print("-" * 60)
