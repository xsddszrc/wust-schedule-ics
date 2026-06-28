# 武科大课表 ICS 订阅

武汉科技大学强智教务系统 → ICS 日历订阅，支持 Apple 日历 / Google 日历 / Outlook。

**测试结果**：`/app.do` API 已被武科大封禁（返回"非法访问"），因此采用 Playwright 浏览器自动化方案。

## 🚀 快速开始

### 1. 安装

```bash
git clone <你的仓库地址> && cd <仓库目录>
pip install playwright beautifulsoup4
playwright install chromium
```

### 2. 首次登录（需要输入验证码）

```bash
python3 generate_ics.py --login --no-headless
```

- 浏览器窗口会自动打开
- 手动完成登录（学号 + 密码 + 验证码）
- 进入「教学一体化服务平台」→ 点击「学期课表」
- 勾选页面上的「放大」复选框
- 回到终端按 Enter

### 3. 以后每次更新

```bash
python3 generate_ics.py --push
```

这一步自动完成：抓取课表 → 解析 → 生成 ICS → git push 到 GitHub

### 4. 启用 GitHub Pages

在 GitHub 仓库 → Settings → Pages：
- Source: `Deploy from a branch`
- Branch: `main` → Save

订阅链接：`https://你的用户名.github.io/仓库名/schedule.ics`

### 5. 定时自动更新（可选）

```bash
# Linux/macOS — 每周一早8点自动运行
crontab -e
# 添加：
0 8 * * 1 cd /path/to/project && python3 generate_ics.py --push
```

Windows 用「任务计划程序」创建每周任务。

---

## 📁 文件说明

| 文件 | 用途 |
|------|------|
| `generate_ics.py` | 主脚本：登录 / 抓取 / 解析 / 生成 ICS / git push |
| `wust-schedule-ics.user.js` | 油猴脚本：在课表页面一键导出 ICS（手动） |
| `auth_state.json` | 浏览器登录状态（不提交 Git） |
| `.wust_ics_config.json` | 自动保存的学期配置 |
| `schedule.ics` | 生成的日历文件 |

---

## 🔧 命令参考

```bash
# 首次登录
python3 generate_ics.py --login --no-headless

# 日常自动抓取
python3 generate_ics.py

# 抓取 + 推送到 GitHub
python3 generate_ics.py --push

# 手动指定学期开始日期
python3 generate_ics.py --semester-start 2026-03-09

# 调试：解析本地保存的 HTML 文件
python3 generate_ics.py --html-file xskb_list.do --semester-start 2026-03-09
```

---

## ⚠️ 注意事项

1. **Cookie 有效期**：教务系统登录状态约 1-2 周过期。如果脚本报"无法加载课表"，重新运行 `--login --no-headless`
2. **新学期**：每学期开学后需要更新第一周周一日期（脚本会自动检测，检测不到时会提示输入）
3. **验证码**：登录时必须手动输入，这是强智系统的硬限制
4. **节次时间**：如果学校作息时间不同，可修改脚本开头的 `PERIOD_TIME` 字典

---

## 🛠 技术架构

```
你的电脑 (cron 定时)
    │
    ▼
Playwright (加载已保存的 cookie)
    │
    ▼
访问 bkjx.wust.edu.cn → 抓取课表 JSP 页面
    │
    ▼
解析 HTML <table id="kbtable"> → 提取课程信息
    │
    ▼
生成 ICS 文件（支持 RRULE 连续周次 + 逐周展开复杂模式）
    │
    ▼
git commit & push → GitHub Pages
    │
    ▼
https://用户名.github.io/仓库名/schedule.ics ← 订阅这个 URL
```

### 关于 API

武科大强智教务的 `/app.do` 移动端 API 已完全封禁（POST 请求返回"非法访问"），无法像其他学校那样直接调 JSON 接口。因此只能通过浏览器自动化走 Web 页面。
