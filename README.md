# 每日时政

公考备考「每日时政要点」数据仓库。

## 工作原理

1. **GitHub Actions 定时任务**（每天 07:00 北京时间）运行 `scripts/fetch.py`
2. 抓取官方权威新闻源：新华网、人民网、中国政府网、央视新闻
3. 清洗去重、自动分类（要闻/政策/经济/民生/科技/国际/法治）、截取摘要
4. 生成两个文件：
   - `data/politics.json` —— 供前端 PWA 经 jsDelivr CDN 读取展示（含近 90 天历史）
   - `data/每日时政-YYYY-MM-DD.md` —— 供 RAGFlow 知识库自动入库

## 前端读取地址

```
https://cdn.jsdelivr.net/gh/bukeliyu2002/daily-politics@main/data/politics.json
```

## 本地手动运行

```bash
python3 scripts/fetch.py
```

## 合规声明

- 仅抓取官方权威来源，保留原文链接，摘要只截取不改写
- 内容版权归原媒体所有，本仓库仅供个人学习使用
