#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日时政 → NAS 知识库目录归档脚本
- 从本地 data/politics.json 读取完整按天归档数据
- 按天生成完整版 md（含当天全部条目）
- 复制到 NAS 共享目录：考公知识库/01-时政热点/

用法：
  python3 archive_to_nas.py            # 归档全部天
  python3 archive_to_nas.py 2026-08-17 # 只归档指定日期
"""

import os
import sys
import json
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
JSON_PATH = os.path.join(DATA_DIR, "politics.json")

# NAS 挂载路径（macOS Finder 手动挂载后的 /Volumes 路径）
NAS_MOUNT = "/Volumes/ai knowledge base"
NAS_TARGET = os.path.join(NAS_MOUNT, "考公知识库", "01-时政热点")

CATEGORY_ORDER = ["要闻", "政策", "经济", "民生", "科技", "国际", "法治"]


def is_nas_mounted():
    """检查 NAS 共享是否已挂载"""
    return os.path.isdir(NAS_MOUNT) and os.path.isdir(NAS_TARGET)


def build_md(date_str, items):
    """生成当天完整版 md 内容"""
    lines = [f"# 每日时政要点（{date_str}）", "",
             f"> 数据来源：新华网 / 人民网 / 中国政府网 / 央视新闻，仅供个人学习使用。", ""]
    for cat in CATEGORY_ORDER:
        cat_items = [it for it in items if it.get("category") == cat]
        if not cat_items:
            continue
        lines.append(f"## {cat}")
        for it in cat_items:
            lines.append(f"- **{it['title']}**")
            if it.get("summary"):
                lines.append(f"  - {it['summary']}…")
            lines.append(f"  - 来源：{it.get('source', '')} | {it.get('url', '')}")
        lines.append("")
    return "\n".join(lines)


def archive_day(date_str, items, overwrite=False):
    """归档单天"""
    if not is_nas_mounted():
        print("[err] NAS 共享未挂载，请先在 Finder 挂载（⌘K → smb://100.80.126.35）")
        return False
    os.makedirs(NAS_TARGET, exist_ok=True)
    md_name = f"每日时政-{date_str}.md"
    md_path = os.path.join(NAS_TARGET, md_name)
    if os.path.exists(md_path) and not overwrite:
        print(f"[i] {md_name} 已存在，跳过（如需覆盖加 --overwrite）")
        return True
    content = build_md(date_str, items)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[+] 已归档 {md_path}（{len(items)} 条）")
    return True


def main():
    if not os.path.exists(JSON_PATH):
        print(f"[err] 找不到 {JSON_PATH}")
        return 1
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    days = data.get("days", [])
    if not days:
        print("[i] politics.json 暂无数据")
        return 0

    # 指定日期 or 全部
    target = sys.argv[1] if len(sys.argv) > 1 else None
    overwrite = "--overwrite" in sys.argv

    print(f"[*] NAS 挂载: {'OK' if is_nas_mounted() else '未挂载'}")
    print(f"[*] 目标目录: {NAS_TARGET}")
    print(f"[*] 共 {len(days)} 天数据" + (f"，过滤日期 {target}" if target else ""))

    done = 0
    for day in days:
        date_str = day.get("date", "")
        if target and date_str != target:
            continue
        if archive_day(date_str, day.get("items", []), overwrite):
            done += 1
    print(f"[*] 完成，归档 {done} 天")
    return 0


if __name__ == "__main__":
    sys.exit(main())