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
python3 -m venv .venv
source .venv/bin/activate
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
.venv/bin/python generate_ics.py --login
```

自动完成 CAS 登录（验证码自动识别）→ 抓取课表 → 生成 `schedule.ics`

### 3. 定时任务

```bash
crontab -e
# 每周一早 8:00（先拉取更新，再执行）
0 8 * * 1 cd /path/to/wust-schedule-ics && git pull && .venv/bin/python generate_ics.py
```

### 4. 提供内部订阅

ICS 文件只需服务器内部能访问即可，不用暴露到公网。

**方式 A — 丢到现有网站目录下**（最简单）：

```bash
# 假设你的网站根目录是 /var/www/html
.venv/bin/python generate_ics.py --output /var/www/html/schedule.ics
crontab -e
0 8 * * 1 cd /path/to/wust-schedule-ics && .venv/bin/python generate_ics.py --output /var/www/html/schedule.ics
```

网站直接访问 `http://127.0.0.1/schedule.ics` 即可订阅。

**方式 B — 独立端口**（网站和脚本解耦）：

```bash
# 启动内部 HTTP 服务（只监听 127.0.0.1，外部无法访问）
python3 -m http.server 9999 --bind 127.0.0.1 --directory /path/to/wust-schedule-ics &

# crontab
0 8 * * 1 cd /path/to/wust-schedule-ics && .venv/bin/python generate_ics.py
```

订阅链接：`http://127.0.0.1:9999/schedule.ics`

两种方式都只绑定本地回环地址，端口 80/443 被占也无所谓。

---

## 方案二：本地电脑

在自己电脑上跑，同样全自动。电脑需要在周一早上开着。

安装部署同方案一，加上 crontab 即可。

---

## 方案三：油猴脚本（手动）

安装 [wust-schedule-ics.user.js](https://xsddszrc.github.io/wust-schedule-ics/wust-schedule-ics.user.js) → 登录教务 → 课表页面 → 点击"📅 导出ICS"。

零依赖，适合偶尔手动导出。每次课表变化需重新操作。

---

## 🔧 命令参考

| 命令 | 说明 |
|------|------|
| `.venv/bin/python generate_ics.py --login` | 首次登录 |
| `.venv/bin/python generate_ics.py` | 抓取课表，生成 ICS |
| `.venv/bin/python generate_ics.py --push` | 抓取 + 推送到 GitHub |
| `.venv/bin/python generate_ics.py --semester-start 2026-03-09` | 手动指定开学日期 |

---

## 🔬 技术细节

### 第一周周一自动检测

无需手动配置。脚本从课表页面读取当前是第几周，结合系统日期倒推：

```
第一周周一 = 今天的周一日期 − (当前周次 − 1) × 7 天
```

结果存到 `.wust_ics_config.json`，下次直接读取。换学期后自动重新检测。

### 验证码自动识别

武科大 CAS 登录的验证码是算术加法题（如 `3+5=?`）。流程：

```
截图验证码 → ddddocr 识别 → 后处理修正误识别 → 计算答案 → 填入
```

ddddocr 对 `+` 和 `0` 容易识别为 `*` 和 `o`，脚本内置了字符修正表（`*→+`、`o→0` 等），修正后准确率 100%。单次失败自动刷新重试，最多 6 次。

### Session 过期处理

CAS 票据 2-8 小时过期，教务 session 更短。脚本每次运行先尝试已保存状态 → 如果过期则自动重新登录（ddddocr 识别验证码），用户无感知。

### 课表解析

从 `#kbtable` 的 `<div class="kbcontent">` 中提取每门课的：课程名、教师、教室、周次模式、节次范围。

周次支持 `1-17`、`1,3-4,6-11,13,15,17` 等复杂写法。节次支持 `[01-02节]`、`[07-08-09-10节]`（连堂课）等。连续周次生成 `RRULE`，不连续则逐周展开。

### 节次时间映射

默认使用黄家湖校区时间，青山校区注释在代码里。

| 大节 | 小节 | 时间 | 课间 |
|------|------|------|------|
| 1-2 | 1-2 | 08:20-10:00 | 20min |
| 3-4 | 3-4 | 10:20-12:00 | 午饭 |
| 5-6 | 5-6 | 14:00-15:40 | 20min |
| 7-8 | 7-8 | 16:00-17:40 | 晚饭 |
| 9-10 | 9-10 | 18:40-20:20 | 20min |
| 11-12 | 11-12 | 20:40-22:20 | — |

45 分钟/节，两小节间 10 分钟，两大节间 20 分钟。如需调整，修改 `generate_ics.py` 开头的 `PERIOD_TIME` 字典即可（key=节次号，value=开始/结束时间）。

---

## 📁 文件

| 文件 | 用途 |
|------|------|
| `generate_ics.py` | 主脚本 |
| `wust-schedule-ics.user.js` | 油猴脚本 |
| `.env` | 凭证（gitignore） |
| `schedule.ics` | 生成的日历（gitignore） |

> **PS**:如果需要ics订阅链接，但是没有服务器可以私信我
