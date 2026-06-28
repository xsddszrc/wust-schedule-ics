# 武科大课表 ICS 订阅

武汉科技大学强智教务系统 → ICS 日历，支持 Apple 日历 / Google 日历 / Outlook。

> **关键事实**：武科大 CAS 登录页仅允许国内 IP 访问，因此 GitHub Actions（海外 IP）不可用。Gitee Go 在国内 → 可用。

---

## 方案一：Gitee 全自动（⭐ 推荐）

### 1. 导入仓库到 Gitee

Gitee 顶部 `+` → 从 GitHub 导入 → 输入 `xsddszrc/wust-schedule-ics` → 导入

### 2. 设置凭证

仓库 → **服务** → **Gitee Go** → 开通 → 流水线变量 → 添加两个：

| 变量名 | 值 |
|--------|-----|
| `WUST_USERNAME` | 你的学号 |
| `WUST_PASSWORD` | 你的密码 |

### 3. 启用 Gitee Pages

仓库 → **服务** → **Gitee Pages** → 开通 → 部署分支选 `main` → 启动

订阅链接：`https://你的用户名.gitee.io/wust-schedule-ics/schedule.ics`

### 4. 触发首次运行

提交任意内容触发流水线，或者在 Gitee Go 界面手动触发。

之后每次 push 都会自动跑，也可以配置定时触发。Gitee Go 免费额度每月 **500 分钟**，每周跑一次绰绰有余。

### 5. 定时触发

编辑 `.gitee-ci.yml`，在文件顶部加入触发条件后推送即可生效。

---

## 方案二：本地自动运行

在自己电脑上，同样全自动。密码不离开电脑。

```bash
git clone git@github.com:xsddszrc/wust-schedule-ics.git
cd wust-schedule-ics
pip install playwright beautifulsoup4 ddddocr
playwright install chromium
cp .env.example .env
# 编辑 .env 填入学号和密码
```

运行：

```bash
python3 generate_ics.py --login   # 首次
python3 generate_ics.py --push    # 日常：抓取 + 推送 GitHub Pages
```

定时：

```bash
crontab -e
# 每周一早 8:00
0 8 * * 1 cd /path/to/wust-schedule-ics && python3 generate_ics.py --push
```

---

## 方案三：油猴脚本（手动）

安装 `wust-schedule-ics.user.js` → 登录教务 → 课表页面点击"导出ICS"。

仅适合偶尔手动导出。

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
| `.gitee-ci.yml` | Gitee Go 流水线配置 |
| `.github/workflows/update-schedule.yml` | GitHub Actions（备用） |
| `wust-schedule-ics.user.js` | 油猴脚本 |
| `.env` | 本地凭证（gitignore） |
