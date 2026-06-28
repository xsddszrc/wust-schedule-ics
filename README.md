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

### 4. 提供内部订阅

ICS 文件只需服务器内部能访问即可，不用暴露到公网。

**方式 A — 丢到现有网站目录下**（最简单）：

```bash
# 假设你的网站根目录是 /var/www/html
python3 generate_ics.py --output /var/www/html/schedule.ics
crontab -e
0 8 * * 1 cd /path/to/wust-schedule-ics && python3 generate_ics.py --output /var/www/html/schedule.ics
```

网站直接访问 `http://127.0.0.1/schedule.ics` 即可订阅。

**方式 B — 独立端口**（网站和脚本解耦）：

```bash
# 启动内部 HTTP 服务（只监听 127.0.0.1，外部无法访问）
python3 -m http.server 9999 --bind 127.0.0.1 --directory /path/to/wust-schedule-ics &

# crontab
0 8 * * 1 cd /path/to/wust-schedule-ics && python3 generate_ics.py
```

订阅链接：`http://127.0.0.1:9999/schedule.ics`

两种方式都只绑定本地回环地址，端口 80/443 被占也无所谓。

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
