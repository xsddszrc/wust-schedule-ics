# 武科大课表 ICS 订阅

武汉科技大学强智教务系统 → ICS 日历，支持 Apple 日历 / Google 日历 / Outlook。

---

## 方案一：GitHub Actions 全自动（⭐ 推荐）

无需电脑开机，部署后完全不管。GitHub 每周自动运行。

### 1. Fork 仓库 & 设置 Secrets

Fork 本仓库，然后在你自己仓库的 **Settings → Secrets and variables → Actions** 添加两个 Secret：

| Name | Value |
|------|-------|
| `WUST_USERNAME` | 你的学号 |
| `WUST_PASSWORD` | 你的密码 |

> 🔒 GitHub Secrets 是加密存储的，只有 Actions 运行时才能解密读取，日志中会自动屏蔽。学号密码不会泄露。

### 2. 启用 GitHub Pages

**Settings → Pages**：
- Source: `Deploy from a branch`
- Branch: `main` → Save

订阅链接（约 1 分钟后生效）：

```
https://你的用户名.github.io/wust-schedule-ics/schedule.ics
```

### 3. 触发首次运行

**Actions** 标签 → **Update Schedule ICS** → **Run workflow**

之后每周一早 8:00 自动运行，完全不用管。

### 原理

```
GitHub Actions (每周一早 8:00)
    │
    ▼
Playwright → CAS 登录（ddddocr 识别验证码）
    │
    ▼
抓取课表 → 解析 → 生成 schedule.ics
    │
    ▼
git commit & push → GitHub Pages 自动更新
```

---

## 方案二：本地自动运行

适合不想把密码放 GitHub 的用户。在自己电脑上跑，同样全自动。

### 安装

```bash
git clone git@github.com:xsddszrc/wust-schedule-ics.git
cd wust-schedule-ics
pip install playwright beautifulsoup4 ddddocr
playwright install chromium
cp .env.example .env
# 编辑 .env 填入学号和密码
```

### 运行

```bash
python3 generate_ics.py --login   # 首次
python3 generate_ics.py --push    # 日常：抓取 + 推送 GitHub Pages
```

### 定时

```bash
crontab -e
# 每周一早 8:00
0 8 * * 1 cd /path/to/wust-schedule-ics && python3 generate_ics.py --push
```

---

## 方案三：油猴脚本（手动）

安装 `wust-schedule-ics.user.js` → 登录教务 → 课表页面点击"导出ICS"。

仅适合偶尔手动导出，无需 Python。

---

## 🔧 命令参考

| 命令 | 说明 |
|------|------|
| `python3 generate_ics.py` | 抓取课表，生成 ICS |
| `python3 generate_ics.py --push` | 抓取 + git push |
| `python3 generate_ics.py --login` | 强制重新登录 |
| `python3 generate_ics.py --semester-start 2026-03-09` | 手动指定开学日期 |

---

## 📁 文件说明

| 文件 | 用途 |
|------|------|
| `generate_ics.py` | 主脚本 |
| `.github/workflows/update-schedule.yml` | GitHub Actions 配置 |
| `wust-schedule-ics.user.js` | 油猴脚本 |
| `.env` | 本地凭证（gitignore） |
| `auth_state.json` | 浏览器状态（gitignore） |
