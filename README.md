# 武科大课表 ICS 订阅

武汉科技大学强智教务系统 → ICS 日历，支持 Apple 日历 / Google 日历 / Outlook。

> CAS 登录页仅允许国内 IP 访问，因此需要在国内服务器上运行脚本。

---

## 方案一：服务器部署（⭐ 推荐）

在任意国内服务器（阿里云/腾讯云/校园网主机/树莓派）上部署，完全自动化。

### 1. 部署

```bash
git clone https://github.com/xsddszrc/wust-schedule-ics.git
cd wust-schedule-ics
pip install playwright beautifulsoup4 ddddocr
playwright install --with-deps chromium
cp .env.example .env
```

编辑 `.env`：
```
WUST_USERNAME=你的学号
WUST_PASSWORD=你的密码
```

### 2. 首次运行

```bash
python3 generate_ics.py --login
```

自动完成 CAS 登录（验证码自动识别）→ 抓取课表 → 生成 `schedule.ics`

### 3. 定时任务

```bash
crontab -e
# 每周一早 8:00
0 8 * * 1 cd /path/to/wust-schedule-ics && python3 generate_ics.py
```

### 4. 提供订阅

**方式 A — Nginx 直接托管**（最简单）：

```nginx
server {
    listen 80;
    location /schedule.ics {
        alias /path/to/wust-schedule-ics/schedule.ics;
        add_header Content-Type "text/calendar; charset=utf-8";
    }
}
```

订阅链接：`http://你的服务器IP/schedule.ics`

**方式 B — 推送到 GitHub Pages**：

服务器生成 ICS 后自动推送到 GitHub，利用 GitHub Pages 提供 HTTPS 订阅。

```bash
crontab -e
0 8 * * 1 cd /path/to/wust-schedule-ics && python3 generate_ics.py --push
```

订阅链接：`https://xsddszrc.github.io/wust-schedule-ics/schedule.ics`

---

## 方案二：本地电脑

在自己电脑上跑，同样全自动。电脑需要在周一早上开着。

安装部署同方案一，加上 crontab 即可。

---

## 方案三：油猴脚本（手动）

安装 `wust-schedule-ics.user.js` → 登录教务 → 课表页面 → 点击"📅 导出ICS"。

零依赖，适合偶尔手动导出。每次课表变化需重新操作。

---

## 🔧 命令参考

| 命令 | 说明 |
|------|------|
| `python3 generate_ics.py --login` | 首次登录 |
| `python3 generate_ics.py` | 抓取课表，生成 ICS |
| `python3 generate_ics.py --push` | 抓取 + 推送到 GitHub |
| `python3 generate_ics.py --semester-start 2026-03-09` | 手动指定开学日期 |

---

## 📁 文件

| 文件 | 用途 |
|------|------|
| `generate_ics.py` | 主脚本 |
| `wust-schedule-ics.user.js` | 油猴脚本 |
| `.env` | 凭证（gitignore） |
| `schedule.ics` | 生成的日历（gitignore） |
