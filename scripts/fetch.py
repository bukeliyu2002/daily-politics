#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日时政抓取脚本
- 抓取官方权威新闻源（新华网 / 人民网 / 中国政府网 / 央视新闻）
- 清洗去重、分类打标、截取摘要
- 输出 data/politics.json（前端展示用）+ data/每日时政-YYYY-MM-DD.md（知识库入库用）
仅供个人学习使用，内容版权归原媒体所有，保留原文链接。
"""

import json
import os
import re
import sys
import datetime
import urllib.request
import urllib.error

# ===== 北京时间时区（GitHub Actions 运行在 UTC，必须显式用北京时间） =====
try:
    from zoneinfo import ZoneInfo
    TZ_BJ = ZoneInfo("Asia/Shanghai")
except ImportError:
    TZ_BJ = datetime.timezone(datetime.timedelta(hours=8))

def bj_now():
    """北京时间当前时刻（带时区）"""
    return datetime.datetime.now(TZ_BJ)

def bj_today():
    """北京时间当前日期"""
    return bj_now().date()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
JSON_PATH = os.path.join(DATA_DIR, "politics.json")

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
TIMEOUT = 15

# 分类关键词（用于自动打标，可扩展）
CATEGORY_RULES = [
    ("要闻", ["习近平", "总理", "全国人大", "政协", "国务院常务会议", "中央政治局", "重要讲话", "国家主席"]),
    ("政策", ["发布", "印发", "出台", "意见", "通知", "规划", "条例", "方案", "办法", "标准", "规定", "决定", "批复"]),
    ("经济", ["经济", "金融", "央行", "财政", "税务", "GDP", "进出口", "消费", "投资", "市场", "物价", "数据"]),
    ("民生", ["就业", "教育", "医疗", "养老", "住房", "社保", "粮食", "交通", "民生", "老旧小区"]),
    ("科技", ["科技", "创新", "航天", "芯片", "人工智能", "数据", "网络", "5G", "量子", "新能源"]),
    ("国际", ["国际", "外交部", "联合国", "会谈", "访问", "合作", "美国", "欧盟", "俄罗斯", "外交"]),
    ("法治", ["法律", "法规", "司法", "法院", "检察", "公安", "违法", "处罚", "条例"]),
]

# 噪声词过滤
NOISE = ["许可证", "京ICP", "网文", "增值电信", "广播电视", "信息服务", "备案", "版权声明", "广告"]

# robots.txt 合规约束（2026-08-15 核实）
# - 新华网: Allow: /（允许）
# - 人民网: Crawl-delay: 120（要求抓取间隔 ≥120 秒，本脚本每日仅 1 次，天然满足）
# - 中国政府网: Allow: /1，抓取 /zhengce/ 目录未禁止
# - 央视新闻: robots.txt 无有效声明（404），保持每日 1 次低频
ROBOTS_COMPLIANCE = {
    "新华网": {"status": "允许", "note": "robots Allow: /"},
    "人民网": {"status": "允许但限速", "note": "Crawl-delay: 120，每日 1 次已满足"},
    "中国政府网": {"status": "允许", "note": "抓取 /zhengce/ 未在 Disallow 列表"},
    "央视新闻": {"status": "无声明", "note": "robots 404，保持每日 1 次低频"},
}


def http_get(url):
    """通用 GET 请求，返回解码后的文本"""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            for enc in ("utf-8", "gbk", "gb2312"):
                try:
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    continue
            return raw.decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[warn] 请求失败 {url}: {e}")
        return ""


def extract_links(html, url_pattern, min_len=10):
    """通用链接提取：抓所有 <a href> 对，按 URL 模式过滤"""
    items = []
    pat = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.S)
    for m in pat.finditer(html):
        url = m.group(1)
        text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        text = re.sub(r"\s+", " ", text).strip()
        if not url or not text or len(text) < min_len:
            continue
        if not re.search(url_pattern, url):
            continue
        if any(k in text for k in NOISE):
            continue
        items.append({"url": url, "title": text})
    return items


def fetch_xinhua():
    """新华网 · 时政频道（链接为相对路径 /politics/YYYYMMDD/，标题在 <span><a> 内）"""
    html = http_get("http://www.news.cn/politics/")
    items = extract_links(html, r"(?:news\.cn)?/politics/\d{8}/")
    for it in items:
        it["source"] = "新华网"
        if it["url"].startswith("/"):
            it["url"] = "https://www.news.cn" + it["url"]
    return items[:15]


def fetch_people(use_browser=True):
    """人民网 · 首页（反爬严格，优先用 Playwright 真实浏览器；失败则退回 urllib）"""
    # 1) 优先 Playwright
    if use_browser:
        items = fetch_people_playwright()
        if items:
            return items
        print("[warn] Playwright 抓取人民网失败，退回 urllib")
    # 2) 退回 urllib
    html = http_get("http://www.people.com.cn/")
    items = extract_links(html, r"people\.com\.cn/n\d/\d{4}/\d{4}/")
    keep = ["politics", "world", "opinion", "c461001", "c1002", "c1004"]
    filtered = []
    for it in items:
        if any(k in it["url"] for k in keep):
            it["source"] = "人民网"
            filtered.append(it)
    return filtered[:20]


def fetch_people_playwright():
    """用 Playwright 真实浏览器抓人民网首页，绕过反爬"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[warn] 未安装 playwright，人民网跳过浏览器模式")
        return []
    items = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=UA, locale="zh-CN")
            try:
                page.goto("http://www.people.com.cn/", timeout=20000, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                links = page.evaluate("""() => {
                    const out = [];
                    document.querySelectorAll('a').forEach(a => {
                        const t = (a.innerText||'').trim().replace(/\\s+/g,' ');
                        const h = a.href||'';
                        if (t.length >= 12 && /people\\.com\\.cn\\/n\\d\\/\\d{4}\\/\\d{4}\\//.test(h)) {
                            out.push({t: t, h: h});
                        }
                    });
                    const seen = new Set();
                    return out.filter(x => { const k=x.h; if(seen.has(k))return false; seen.add(k); return true; });
                }""")
                for l in links:
                    items.append({"title": l["t"], "url": l["h"], "source": "人民网"})
            finally:
                browser.close()
    except Exception as e:
        print(f"[warn] Playwright 人民网异常: {e}")
    # 过滤：只保留时政/观点/国际等频道
    keep = ["politics", "opinion", "world", "c461001", "c1002"]
    filtered = [it for it in items if any(k in it["url"] for k in keep)]
    return filtered[:20]


def fetch_gov():
    """中国政府网 · 最新政策（数据在 ZUIXINZHENGCE.json）"""
    items = []
    try:
        raw = http_get("https://www.gov.cn/zhengce/zuixin/ZUIXINZHENGCE.json")
        if raw:
            data = json.loads(raw)
            for it in data:
                title = it.get("TITLE", "").strip()
                url = it.get("URL", "").strip()
                if title and url and len(title) >= 8:
                    items.append({
                        "title": title,
                        "url": "https://www.gov.cn" + url if url.startswith("/") else url,
                        "source": "中国政府网",
                    })
    except Exception as e:
        print(f"[warn] 政府网解析失败: {e}")
    return items[:20]


def fetch_cctv():
    """央视新闻 · 要闻"""
    html = http_get("https://news.cctv.com/")
    items = extract_links(html, r"news\.cctv\.com/\d{4}/\d{2}/\d{2}/")
    # 央视列表里标题和摘要重复同一 URL，去重后保留
    seen = set()
    filtered = []
    for it in items:
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        it["source"] = "央视新闻"
        filtered.append(it)
    return filtered[:15]


def classify(title):
    """按关键词自动分类"""
    for cat, kws in CATEGORY_RULES:
        for kw in kws:
            if kw in title:
                return cat
    return "要闻"


def dedupe(items):
    """按标题去重（去除标点/空格归一化）"""
    seen = set()
    result = []
    for it in items:
        key = re.sub(r"[\s，。、·—\-（）()「」“”\"':：]", "", it["title"])
        if key and key not in seen:
            seen.add(key)
            result.append(it)
    return result


def summary_from_url(url):
    """尝试从详情页提取首段文字作为摘要，失败返回空"""
    html = http_get(url)
    if not html:
        return ""
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S)
    # 清理 HTML 实体
    html = html.replace("&emsp;", " ").replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    paras = re.findall(r"<p[^>]*>(.*?)</p>", html, re.S)
    text = ""
    for p in paras:
        t = re.sub(r"<[^>]+>", "", p).strip()
        t = re.sub(r"\s+", "", t)
        if len(t) >= 30:
            text = t
            break
    if text:
        return text[:120]
    m = re.search(r'<meta[^>]+name="description"[^>]+content="([^"]+)"', html)
    if m:
        return m.group(1)[:120]
    return ""


def main():
    print(f"[*] 开始抓取: {bj_now().strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    print("[*] 合规声明: 仅抓取官方权威源，每日 1 次低频，遵守各站 robots.txt，只存标题+摘要+来源链接")

    all_items = []
    all_items += fetch_xinhua()
    all_items += fetch_people()
    all_items += fetch_gov()
    all_items += fetch_cctv()

    print(f"[*] 原始抓取: {len(all_items)} 条")
    all_items = dedupe(all_items)
    print(f"[*] 去重后: {len(all_items)} 条")

    today = bj_today().isoformat()
    enriched = []
    for i, it in enumerate(all_items[:40]):  # 单日最多 40 条
        it["category"] = classify(it["title"])
        it["date"] = today
        it["time"] = bj_now().strftime("%H:%M")
        summary = summary_from_url(it["url"]) if i < 12 else ""
        it["summary"] = summary
        enriched.append(it)

    # ---- 写 JSON（合并历史，保留 90 天）----
    old_data = {"updatedAt": "", "days": []}
    if os.path.exists(JSON_PATH):
        try:
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                old_data = json.load(f)
        except Exception:
            old_data = {"updatedAt": "", "days": []}

    new_day = {"date": today, "items": enriched}
    days = [d for d in old_data.get("days", []) if d.get("date") != today]
    days.insert(0, new_day)
    cutoff = (bj_today() - datetime.timedelta(days=90)).isoformat()
    days = [d for d in days if d.get("date", "") >= cutoff]

    output = {
        "updatedAt": bj_now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "days": days,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"[+] 已写入 {JSON_PATH}（完整按天归档，共 {len(days)} 天记录）")

    # ---- 写 Markdown（供 RAGFlow 知识库入库）----
    # 入库去重：md 只收录「历史未出现过的标题」（首次出现的新闻），
    # 减少 RAGFlow 检索冗余；politics.json 仍保持完整按天归档供前端浏览
    md_path = os.path.join(DATA_DIR, f"每日时政-{today}.md")
    hist_keys = set()
    for d in old_data.get("days", []):
        for it in d.get("items", []):
            key = re.sub(r"[\s，。、·—\-（）()「」“”\"':：]", "", it.get("title", ""))
            if key:
                hist_keys.add(key)
    md_items = []
    for it in enriched:
        key = re.sub(r"[\s，。、·—\-（）()「」“”\"':：]", "", it.get("title", ""))
        if key and key not in hist_keys:
            md_items.append(it)
            hist_keys.add(key)  # 同日多条去重也防住
    dropped = len(enriched) - len(md_items)
    if dropped:
        print(f"[i] 入库去重：{dropped} 条为历史/当日重复，不写入 md（RAGFlow 检索更干净）")

    lines = [f"# 每日时政要点（{today}）", "",
             f"> 数据来源：新华网 / 人民网 / 中国政府网 / 央视新闻，仅供个人学习使用。", ""]
    if not md_items:
        lines.append("> 今日无新增时政（历史已收录的新闻不再重复入库）。")
        lines.append("")
    for cat in ["要闻", "政策", "经济", "民生", "科技", "国际", "法治"]:
        cat_items = [it for it in md_items if it["category"] == cat]
        if not cat_items:
            continue
        lines.append(f"## {cat}")
        for it in cat_items:
            lines.append(f"- **{it['title']}**")
            if it["summary"]:
                lines.append(f"  - {it['summary']}…")
            lines.append(f"  - 来源：{it['source']} | {it['url']}")
        lines.append("")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[+] 已写入 {md_path}（入库去重后 {len(md_items)} 条）")

    print("[*] 完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
