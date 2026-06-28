# 武科大课表 ICS 订阅

武汉科技大学强智教务系统 → ICS 日历，支持 Apple 日历 / Google 日历 / Outlook。

✅ **验证码自动识别**（ddddocr）  
✅ **Session 过期自动重登**（无需人工干预）  

---

## 安装（两个方案共用）

```bash
git clone git@github.com:xsddszrc/wust-schedule-ics.git
cd wust-schedule-ics
pip install playwright beautifulsoup4 ddddocr
playwright install chromium
cp .env.example .env
```

编辑 `.env`：
```
WUST_USERNAME=你的学号
WUST_PASSWORD=你的密码
```

---

## 方案一：本地使用（个人）

适合只需要偶尔导出课表、导入自己手机的用户。

### 生成 ICS

```bash
python3 generate_ics.py --login
```

自动完成登录 → 抓取课表 → 在当前目录生成 `schedule.ics`。

### 导入日历

把 `schedule.ics` 发送到手机，用日历 App 打开即可导入。

### 更新课表

课表变动时重新运行一次即可：

```bash
python3 generate_ics.py
```

> 💡 也可以安装[油猴脚本](wust-schedule-ics.user.js)，在课表页面手动点击导出。

---

## 方案二：GitHub Pages 订阅（全自动，可分享）

适合需要稳定订阅链接、或分享给全班同学的用户。

### 1. 启用 GitHub Pages

仓库 **Settings → Pages**：
- Source: `Deploy from a branch`
- Branch: `main` → Save

订阅链接（部署后约 1 分钟生效）：

```
https://xsddszrc.github.io/wust-schedule-ics/schedule.ics
```

### 2. 定时自动推送

**Linux / macOS**（crontab）：

```bash
crontab -e
```

```
0 8 * * 1 cd /path/to/wust-schedule-ics && python3 generate_ics.py --push
```

**Windows**（任务计划程序）：创建每周一早 8 点运行 `python3 generate_ics.py --push`。

### 3. 流程

```
crontab 每周一早 8:00
    │
    ▼
generate_ics.py --push
    │
    ├── session 有效 → 直接抓取课表
    └── session 过期 → 自动 CAS 登录（ddddocr 识别验证码）
    │
    ▼
解析课表 → 生成 schedule.ics
    │
    ▼
git commit & push → GitHub Pages 自动更新
    │
    ▼
订阅者自动收到更新
```

### 4. 分享

把订阅链接发给同学，任何人添加到日历 App 后，每周课表自动同步，无需任何操作。

---

## 🔧 命令参考

| 命令 | 说明 |
|------|------|
| `python3 generate_ics.py --login` | 首次登录 |
| `python3 generate_ics.py --login --no-headless` | 同上，显示浏览器窗口（调试用） |
| `python3 generate_ics.py` | 抓取课表，生成 ICS |
| `python3 generate_ics.py --push` | 抓取 + 推送到 GitHub |
| `python3 generate_ics.py --semester-start 2026-03-09` | 手动指定学期第一周周一 |

---

## 📁 文件说明

| 文件 | 用途 | 提交 Git |
|------|------|----------|
| `generate_ics.py` | 主脚本 | ✅ |
| `wust-schedule-ics.user.js` | 油猴脚本（方案一手动备选） | ✅ |
| `schedule.ics` | 生成的日历文件 | ❌ gitignore |
| `.env` | 学号密码 | ❌ gitignore |
| `auth_state.json` | 浏览器登录状态 | ❌ gitignore |
| `.wust_ics_config.json` | 学期配置 | ❌ gitignore |

---

## ⚠️ 注意事项

- **新学期**：首次运行会自动检测周次推算开学日期，检测不到时提示输入
- **节次时间**：如需修改作息，编辑 `generate_ics.py` 开头的 `PERIOD_TIME`
- **API**：武科大 `/app.do` 移动端 API 已封禁，只能走浏览器自动化
