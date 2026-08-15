# 学习打卡 PWA · 数据存储原理与位置

## 三层存储架构

### 第一层：时政数据（每日时政，本项目新增）
- **存储位置**：GitHub 公开仓库 `bukeliyu2002/每日时政` → `data/politics.json`
- **CDN 分发**：jsDelivr `https://cdn.jsdelivr.net/gh/bukeliyu2002/每日时政@main/data/politics.json`
- **更新机制**：GitHub Actions 每日 07:00（北京时间）自动抓取官方新闻源生成
- **浏览器缓存**：localStorage 键 `shizheng_cache_v1`（首次访问后保留）
- **可见范围**：任何人可见（公开仓库）
- **恢复方式**：无需恢复，全自动

### 第二层：PWA 静态资源（Service Worker 缓存）
- **存储位置**：浏览器 Cache Storage · 缓存名 `study-checkin-v2.6.6`
- **内容**：index.html、tailwind.js、chart.js、words-data.js、icon-*.png、manifest.json
- **特点**：用户首次打开页面后下载到本地，断网可用；版本更新由 sw.js 中 CACHE_NAME 控制
- **可见范围**：仅当前设备当前浏览器

### 第三层：用户个人数据（浏览器内嵌 KV 存储）
- **存储位置**：浏览器 localStorage 数据库（不是 cookie，可达 5-10MB）
- **数据条目（全部以 `exam_` 或 `w8_` 为命名前缀）**：

| 键名 | 内容 | 大小估算 |
|------|------|----------|
| `exam_users_v2` | 多用户档案、主题、设置 | < 50KB |
| `exam_dailyData` | 所有日期的刷题/刷课/复盘数据 | 增长型，每条任务约 200B |
| `exam_wrongQ` | 错题集 | 增长型 |
| `exam_menus` | 侧栏菜单配置（你新增的「时政要点」也存这里） | < 5KB |
| `exam_mindmap_progress` | 思维导图掌握度 | < 30KB |
| `exam_todo` | 待办事项 | < 10KB |
| `exam_checkInDays` | 连续打卡天数 | 极小 |
| `exam_currentDate/Page/User` | 当前会话状态 | < 1KB |
| `w8_order` / `w8_selGroup` / `w8_studied` / `w8_tab` | 800 词学习进度 | < 20KB |
| `shizheng_cache_v1` | **本项目新增**：时政数据缓存 | < 500KB（视历史天数） |

## 关键提示

1. **数据仅存于当前浏览器**：换设备、换浏览器、清除浏览数据 = 数据丢失
2. **无云同步**：这是纯前端 PWA，没有后端数据库
3. **导出/迁移**：可在浏览器控制台输入 `JSON.stringify(localStorage)` 复制全部数据
4. **导出位置**：复制后保存到本地 .json 文件，换设备时反向 `Object.entries(JSON.parse(text)).forEach(([k,v])=>localStorage.setItem(k,v))` 还原

## 数据备份建议

如果数据量大、担心丢失，建议：
- 定期在浏览器开发者工具 → Application → Local Storage 手动备份
- 或扩展本项目：增加"导出/导入"按钮，把 localStorage 序列化成 JSON 文件下载