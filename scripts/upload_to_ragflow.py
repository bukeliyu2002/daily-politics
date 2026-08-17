#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日时政 → RAGFlow 知识库自动入库脚本
- 从 GitHub 公开仓库「每日时政」拉取当天的时政 Markdown
- 通过 RAGFlow HTTP API 上传到 NAS 的「考公知识库」
- 触发文档解析，纳入 RAG 检索体系

需要配置：
- RAGFLOW_API_KEY：在 RAGFlow Web（http://192.168.0.105:8080）→ 设置 → API Key 生成
- 其他参数已在脚本顶部默认填好
"""

import os
import sys
import datetime
import urllib.request
import urllib.error
import json

# ============ 配置（请填入） ============
# 自动加载同目录 .env 文件（RAGFLOW_API_KEY 存放在 .env，不入 git）
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(_env_path):
    try:
        with open(_env_path, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip())
    except Exception as _e:
        print(f"[warn] 读取 .env 失败: {_e}")

# RAGFlow 地址列表：优先 Tailscale（远程可访问），回退局域网 IP（在家直连）
# 顺序 = 尝试优先级，第一个能连通的即使用
RAGFLOW_BASE_URLS = [
    "http://100.80.126.35:9380",   # Tailscale 地址（首选，不受局域网限制）
    "http://192.168.0.105:9380",   # 局域网地址（兜底）
]
RAGFLOW_API_KEY = os.environ.get("RAGFLOW_API_KEY", "")  # 在 RAGFlow Web 设置 → API Key 创建，存放于 .env
DATASET_ID = "a0486a9a980911f181954d2a096f88c6"  # 考公知识库

def pick_ragflow_base(timeout=5):
    """探测哪个 RAGFlow 地址可用（Tailscale 优先）"""
    for base in RAGFLOW_BASE_URLS:
        try:
            req = urllib.request.Request(base + "/api/v1/datasets", headers={"Authorization": f"Bearer {RAGFLOW_API_KEY}"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                code = resp.read().decode("utf-8", errors="ignore")
                if '"code"' in code or resp.status in (200, 401, 400):
                    print(f"[+] 使用 RAGFlow 地址: {base}")
                    return base
        except Exception:
            continue
    print(f"[warn] 所有 RAGFlow 地址均不可达: {RAGFLOW_BASE_URLS}")
    return RAGFLOW_BASE_URLS[0]

RAGFLOW_BASE_URL = os.environ.get("RAGFLOW_BASE_URL", "") or pick_ragflow_base()

# GitHub 公开仓库（每日时政）
GITHUB_USER = "bukeliyu2002"
GITHUB_REPO = "daily-politics"
GITHUB_BRANCH = "main"
RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}/data/"

# ============ 工具函数 ============

def http_post_json(url, headers, body, timeout=30):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={**headers, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        return {"code": e.code, "message": err_body}
    except Exception as e:
        return {"code": -1, "message": str(e)}


def http_get_text(url, timeout=20):
    # 对 URL 中的中文等非 ASCII 字符做百分号编码（raw.githubusercontent 要求）
    try:
        url = urllib.request.quote(url, safe=":/?=&%+-._~")
    except Exception:
        pass
    req = urllib.request.Request(url, headers={"User-Agent": "shizheng-uploader/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        print(f"[warn] GET {url}: {e}")
        return ""


# ============ 主流程 ============

def delete_old_shizheng_docs(headers):
    """删除知识库中所有旧的「每日时政-*.md」文档（替换旧版：库里只保留最新一份）"""
    deleted = 0
    try:
        list_url = f"{RAGFLOW_BASE_URL}/api/v1/datasets/{DATASET_ID}/documents?page=1&page_size=100"
        req = urllib.request.Request(list_url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        docs = data.get("data", {}).get("docs", [])
        # 筛选名称匹配「每日时政-」的文档
        old_ids = [d["id"] for d in docs if d.get("name", "").startswith("每日时政-")]
        if not old_ids:
            print("[i] 无旧时政文档，直接上传新版本")
            return 0
        # 调用删除 API（RAGFlow 用 ids 字段）
        del_url = f"{RAGFLOW_BASE_URL}/api/v1/datasets/{DATASET_ID}/documents"
        del_body = json.dumps({"ids": old_ids}).encode("utf-8")
        del_req = urllib.request.Request(del_url, data=del_body, method="DELETE", headers={**headers, "Content-Type": "application/json"})
        with urllib.request.urlopen(del_req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if result.get("code") == 0:
            deleted = len(old_ids)
            print(f"[+] 已删除 {deleted} 份旧时政文档（替换旧版）")
        else:
            print(f"[warn] 删除旧文档失败: {result}")
    except urllib.error.HTTPError as e:
        print(f"[warn] 查询/删除旧文档 HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')[:150]}")
    except Exception as e:
        print(f"[warn] 删除旧文档异常: {e}")
    return deleted


def upload_to_ragflow(date_str):
    """把 data/每日时政-YYYY-MM-DD.md 下载并上传到 RAGFlow（先删旧版，再传新版）"""
    if not RAGFLOW_API_KEY:
        print("[err] RAGFLOW_API_KEY 未设置，请先在 RAGFlow Web 设置 → API Key 创建并填入")
        return False

    headers = {"Authorization": f"Bearer {RAGFLOW_API_KEY}"}
    # 替换旧版：先删旧时政文档
    delete_old_shizheng_docs(headers)
    md_url = RAW_URL + f"每日时政-{date_str}.md"
    print(f"[*] 拉取: {md_url}")
    content = http_get_text(md_url)
    if not content:
        print("[err] 拉取失败，今天可能还没更新（GitHub Actions 在 07:00 跑）")
        return False
    print(f"[+] 拉取成功 {len(content)} 字")

    # 保存到临时文件以备上传
    tmp = f"/tmp/每日时政-{date_str}.md"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)

    # 用 multipart/form-data 上传（RAGFlow 要求）
    import urllib.request
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = []
    file_bytes = content.encode("utf-8")
    body.append(f"--{boundary}".encode())
    body.append(f'Content-Disposition: form-data; name="file"; filename="每日时政-{date_str}.md"'.encode())
    body.append(b"Content-Type: text/markdown")
    body.append(b"")
    body.append(file_bytes)
    body.append(f"--{boundary}".encode())
    body.append(b'Content-Disposition: form-data; name="language"\r\n')
    body.append(b"Chinese")
    body.append(f"--{boundary}--".encode())
    body.append(b"")
    multipart_body = b"\r\n".join(body)

    upload_url = f"{RAGFLOW_BASE_URL}/api/v1/datasets/{DATASET_ID}/documents"
    req = urllib.request.Request(
        upload_url,
        data=multipart_body,
        headers={**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="ignore")
        print(f"[err] 上传失败 HTTP {e.code}: {err}")
        return False
    except Exception as e:
        print(f"[err] 上传异常: {e}")
        return False

    if result.get("code") != 0:
        print(f"[err] 上传业务错误: {result}")
        return False

    doc_ids = [d.get("id") for d in result.get("data", []) if d.get("id")]
    if not doc_ids:
        print(f"[err] 上传成功但未返回文档 ID: {result}")
        return False
    print(f"[+] 上传成功，document_id={doc_ids[0]}")

    # 触发解析
    parse_url = f"{RAGFLOW_BASE_URL}/api/v1/datasets/{DATASET_ID}/chunks"
    parse_result = http_post_json(parse_url, headers, {"document_ids": doc_ids})
    if parse_result.get("code") == 0:
        print(f"[+] 解析已触发：{parse_result.get('data')}")
    else:
        print(f"[warn] 解析触发失败（不影响入库，已上传）：{parse_result}")
    return True


def main():
    # 北京时间（脚本可能在 UTC 环境下运行，必须显式用北京时间）
    try:
        from zoneinfo import ZoneInfo
        _tz = ZoneInfo("Asia/Shanghai")
    except ImportError:
        _tz = datetime.timezone(datetime.timedelta(hours=8))
    _now = datetime.datetime.now(_tz)
    today = _now.date().isoformat()
    print(f"[*] RAGFlow 入库任务，启动时间 {_now.strftime('%Y-%m-%d %H:%M:%S')} (北京时间)")
    print(f"[*] 目标数据集：{DATASET_ID}（考公知识库）")
    print(f"[*] RAGFlow 地址：{RAGFLOW_BASE_URL}")
    print(f"[*] 目标日期：{today}")
    ok = upload_to_ragflow(today)
    if ok:
        print("[*] 完成 ✅")
        return 0
    print("[*] 失败 ❌")
    return 1


if __name__ == "__main__":
    sys.exit(main())