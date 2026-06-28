# 武科大课表 ICS 订阅

武汉科技大学强智教务系统 → ICS 日历订阅，支持 Apple 日历 / Google 日历 / Outlook。

✅ **验证码自动识别**（ddddocr + 算术题后处理）  
✅ **Session 过期自动重登**（无需人工干预）  
✅ **一键推送到 GitHub Pages**（`--push`）

## 🚀 快速开始

### 1. 克隆 & 安装

```bash
git clone git@github.com:xsddszrc/wust-schedule-ics.git
cd wust-schedule-ics
pip install playwright beautifulsoup4 ddddocr
playwright install chromium
```

### 2. 设置凭证

```bash
cp .env.example .env
# 编辑 .env 填入你的学号和密码
```

`.env` 文件内容：
```
WUST_USERNAME=你的学号
WUST_PASSWORD=你的密码
```

### 3. 首次运行

```bash
python3 generate_ics.py --login
```

自动完成：CAS 登录（验证码自动识别）→ 进入教务系统 → 抓取课表 → 生成 `schedule.ics`

### 4. 启用 GitHub Pages（一次性）

在仓库 **Settings → Pages**：
- Source: `Deploy from a branch`
- Branch: `main` → Save

订阅链接：
```
https://xsddszrc.github.io/wust-schedule-ics/schedule.ics
```

### 5. 日常更新

```bash
python3 generate_ics.py --push
```

每次运行：自动抓取（session 过期会自动重新登录）→ 生成 ICS → git push → GitHub Pages 自动更新。

---

## ⏰ 定时自动运行

### Linux / macOS（crontab）

```bash
# 编辑 crontab
crontab -e
```

添加（每周一早 8 点）：

```
0 8 * * 1 cd /path/to/wust-schedule-ics && python3 generate_ics.py --push
```

确保 `.env` 文件在项目目录里，脚本会自动读取凭证。

### Windows（任务计划程序）

1. 打开「任务计划程序」→ 创建基本任务
2. 触发器：每周一 8:00
3. 操作：启动程序 → `python3 generate_ics.py --push`
4. 起始于：项目目录路径

---

## 🔧 命令参考

| 命令 | 说明 |
|------|------|
| `python3 generate_ics.py --login` | 首次登录（验证码自动识别，headless 模式） |
| `python3 generate_ics.py --login --no-headless` | 同上，显示浏览器窗口（调试用） |
| `python3 generate_ics.py` | 使用已保存状态抓取课表，过期自动重登 |
| `python3 generate_ics.py --push` | 抓取 + git commit & push |
| `python3 generate_ics.py --semester-start 2026-03-09` | 手动指定学期第一周周一 |

---

## 📁 文件说明

| 文件 | 用途 | 提交 Git |
|------|------|----------|
| `generate_ics.py` | 主脚本 | ✅ |
| `wust-schedule-ics.user.js` | 油猴脚本备选方案 | ✅ |
| `schedule.ics` | 生成的日历文件 | ✅ |
| `.env` | 学号密码（从 `.env.example` 复制） | ❌ gitignore |
| `auth_state.json` | 浏览器登录状态（自动生成） | ❌ gitignore |
| `.wust_ics_config.json` | 学期配置（自动生成） | ❌ gitignore |

---

## 🛠 技术架构

```
crontab 每周一 8:00
    │
    ▼
generate_ics.py --push
    │
    ├── 加载 auth_state.json → 访问课表页面
    │   ├── ✅ 成功 → 直接解析
    │   └── ❌ 过期 → 自动 CAS 登录
    │         ├── ddddocr 识别算术验证码（后处理修正 100% 准确率）
    │         ├── 自动填写凭证（从 .env 读取）
    │         └── 最多重试 6 次
    │
    ▼
解析 HTML <table id="kbtable"> → 27 门课程
    │
    ▼
生成 ICS（RRULE 连续周次 + 逐周展开复杂模式）
    │
    ▼
git commit & push → GitHub Pages 自动部署
    │
    ▼
https://xsddszrc.github.io/wust-schedule-ics/schedule.ics
```

---

## ⚠️ 注意事项

1. **新学期**：开学后首次运行会自动检测周次并推算第一周周一，检测不到时会提示输入
2. **节次时间**：如果学校作息不同，可修改 `generate_ics.py` 开头的 `PERIOD_TIME` 字典
3. **API 已封禁**：武科大 `/app.do` 移动端 API 返回"非法访问"，无法使用
