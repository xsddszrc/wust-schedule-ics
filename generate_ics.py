#!/usr/bin/env python3
"""
武科大强智教务系统 → ICS 课表导出工具

═══════════════════════════════════════════════════════════
快速开始:
  # 1. 首次使用 — 手动登录（验证码）
  python3 generate_ics.py --login --no-headless

  # 2. 设置 crontab 定时任务（Mac/Linux）
  # crontab -e  添加:
  # 0 8 * * 1 cd /path/to/project && python3 generate_ics.py --push

═══════════════════════════════════════════════════════════
依赖: pip install playwright beautifulsoup4
      playwright install chromium
═══════════════════════════════════════════════════════════
"""

import argparse
import json
import os
import re
import subprocess
import sys
import uuid as uuid_mod
from datetime import date, datetime, timedelta
from pathlib import Path

# ============ 路径配置 ============
SCRIPT_DIR = Path(__file__).parent.resolve()
AUTH_FILE = SCRIPT_DIR / "auth_state.json"
OUTPUT_FILE = SCRIPT_DIR / "schedule.ics"
CONFIG_FILE = SCRIPT_DIR / ".wust_ics_config.json"
ENV_FILE = SCRIPT_DIR / ".env"


def load_dotenv():
    """加载 .env 文件到环境变量（不覆盖已有值）"""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


# 自动加载
load_dotenv()

# ============ 教务系统 URL ============
LOGIN_URL = "https://bkjx.wust.edu.cn/jsxsd/"
SCHEDULE_URL = "https://bkjx.wust.edu.cn/jsxsd/xskb/xskb_list.do"

# ============ 节次 → 时间映射（黄家湖校区） ============
# 45 分钟/节，两节之间休息 10min，两大节之间休息 20min
# 如需修改：key 为节次号，value 为 (开始时间, 结束时间)
# 青山校区上午早 20 分钟：1-2节 08:00-09:40，3-4节 10:00-11:40
PERIOD_TIME = {
    1:  ("08:20", "09:05"),
    2:  ("09:15", "10:00"),
    3:  ("10:20", "11:05"),
    4:  ("11:15", "12:00"),
    5:  ("14:00", "14:45"),
    6:  ("14:55", "15:40"),
    7:  ("16:00", "16:45"),
    8:  ("16:55", "17:40"),
    9:  ("18:40", "19:25"),
    10: ("19:35", "20:20"),
    11: ("20:40", "21:25"),
    12: ("21:35", "22:20"),
}


# ═══════════════════════════════════════════════════════════
# 配置管理
# ═══════════════════════════════════════════════════════════

def load_config():
    """加载配置文件"""
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    return {}


def save_config(cfg):
    """保存配置文件"""
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# ═══════════════════════════════════════════════════════════
# HTML 解析（与油猴脚本逻辑一致）
# ═══════════════════════════════════════════════════════════

def parse_weeks(week_str):
    """解析周次字符串。例如 '1-17(周)' → [1..17], '1,3-4,6-11,13,15,17(周)' → [1,3,4,6,7,8,9,10,11,13,15,17]"""
    if not week_str:
        return []
    week_str = week_str.replace("(周)", "").strip()
    if not week_str:
        return []

    weeks = set()
    for part in week_str.split(","):
        part = part.strip()
        if "-" in part:
            r = part.split("-")
            if len(r) == 2:
                try:
                    start, end = int(r[0]), int(r[1])
                    for w in range(start, end + 1):
                        weeks.add(w)
                except ValueError:
                    pass
        else:
            try:
                weeks.add(int(part))
            except ValueError:
                pass
    return sorted(weeks)


def parse_periods(period_str):
    """解析节次字符串。例如 '[01-02节]' → [1,2], '[07-08-09-10节]' → [7,8,9,10], '[12节]' → [12]"""
    if not period_str:
        return []
    m = re.search(r'\[([^\]]+)\]', period_str)
    if not m:
        return []
    inner = m.group(1).replace("节", "")
    nums = [int(x) for x in inner.split("-") if x.strip().isdigit()]
    if len(nums) >= 2:
        return list(range(nums[0], nums[-1] + 1))
    elif len(nums) == 1:
        return [nums[0]]
    return []


def periods_to_time_range(periods):
    """从节次列表计算开始/结束时间"""
    if not periods:
        return "08:00", "09:35"
    first = periods[0]
    last = periods[-1]
    start = PERIOD_TIME.get(first, ("08:00", "08:45"))[0]
    end = PERIOD_TIME.get(last, ("21:35", "22:20"))[1]
    return start, end


def parse_course_block(html_text):
    """解析一个课程 div 的 innerHTML"""
    if not html_text or html_text.strip() in ("", "&nbsp;"):
        return None

    # 提取 <font title='...'>...</font>
    font_data = {}
    for m in re.finditer(r'''<font[^>]*title\s*=\s*["']([^"']*)["'][^>]*>([^<]*)</font>''', html_text):
        font_data[m.group(1)] = m.group(2)

    teacher = font_data.get("老师", "")
    classroom = font_data.get("教室", "")
    class_name = font_data.get("课堂名称", "")

    # 周次(节次)
    week_period_raw = font_data.get("周次(节次)", "")
    week_str = ""
    period_str = ""
    if week_period_raw:
        wp_match = re.match(r"^(.+\(周\))(\[.+\])$", week_period_raw)
        if wp_match:
            week_str = wp_match.group(1)
            period_str = wp_match.group(2)
        else:
            wm = re.search(r"(.+\(周\))", week_period_raw)
            pm = re.search(r"(\[.+\])", week_period_raw)
            if wm:
                week_str = wm.group(1)
            if pm:
                period_str = pm.group(1)

    # 课程名：取第一个 <br> 之前的内容，去除 HTML 标签
    first_br = re.split(r"<br\s*/?\s*>", html_text, maxsplit=1)[0]
    course_name = re.sub(r"<[^>]+>", "", first_br).strip()
    if not course_name:
        before_font = re.split(r"<font", html_text, maxsplit=1)[0]
        course_name = re.sub(r"<[^>]+>", "", before_font).strip()

    if not course_name:
        return None

    weeks = parse_weeks(week_str)
    periods = parse_periods(period_str)

    return {
        "course_name": course_name,
        "teacher": teacher,
        "class_name": class_name,
        "classroom": classroom,
        "weeks": weeks,
        "periods": periods,
        "week_str": week_str,
        "period_str": period_str,
    }


def parse_schedule_from_html(html):
    """从课表页面 HTML 中解析所有课程。返回 (courses, detected_semester, detected_week)"""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="kbtable")
    if not table:
        raise ValueError("未找到课表表格 #kbtable")

    # 检测当前学期
    detected_semester = ""
    semester_select = soup.find("select", id="xnxq01id")
    if semester_select:
        selected = semester_select.find("option", selected=True)
        if selected:
            detected_semester = selected.get("value", "")

    # 检测当前周次
    detected_week = None
    zc_select = soup.find("select", id="zc")
    if zc_select:
        selected = zc_select.find("option", selected=True)
        if selected and selected.get("value"):
            try:
                detected_week = int(selected["value"])
            except ValueError:
                pass

    # 收集所有 class="kbcontent" 的详细 div
    detail_divs = table.find_all("div", class_="kbcontent")
    course_map = {}

    for div in detail_divs:
        div_id = div.get("id", "")
        inner_html = "".join(str(c) for c in div.children)

        if not inner_html.strip() or inner_html.strip() == "&nbsp;":
            continue

        id_parts = div_id.split("-")
        if len(id_parts) < 3:
            continue
        weekday = int(id_parts[-2])
        uuid_prefix = "-".join(id_parts[:-2])

        # 分割多课程
        course_blocks = re.split(r"<br\s*/?\s*>\s*[-—]{10,}\s*<br\s*/?\s*>", inner_html)

        for block in course_blocks:
            block = block.strip()
            if not block or block == "&nbsp;":
                continue

            info = parse_course_block(block)
            if not info:
                continue

            week_key = info.get("week_str", "") or ",".join(str(w) for w in info.get("weeks", []))
            sub_key = f"{uuid_prefix}-{weekday}|{week_key}"

            if sub_key in course_map:
                existing = course_map[sub_key]
                all_periods = set(existing["periods"] + info["periods"])
                existing["periods"] = sorted(all_periods)
            else:
                info["weekday"] = weekday
                info["uuid"] = uuid_prefix
                course_map[sub_key] = info

    courses = list(course_map.values())

    # 最终去重：同课程名+同星期+同教师+周次有交集→合并
    dedup_map = {}
    for c in courses:
        key = (c["course_name"], c["weekday"], c.get("teacher", ""))
        if key in dedup_map:
            existing = dedup_map[key]
            existing_weeks = set(existing["weeks"])
            current_weeks = set(c["weeks"])
            if existing_weeks & current_weeks:
                all_periods = set(existing["periods"] + c["periods"])
                existing["periods"] = sorted(all_periods)
            else:
                dedup_map[key + ("__split__" + str(len(dedup_map)),)] = c
        else:
            dedup_map[key] = c

    return list(dedup_map.values()), detected_semester, detected_week


# ═══════════════════════════════════════════════════════════
# ICS 生成
# ═══════════════════════════════════════════════════════════

def fmt_date(d):
    return d.strftime("%Y%m%d")

def fmt_time(t):
    return t.replace(":", "") + "00"

def escape_ics(text):
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def generate_ics(courses, semester_start):
    """生成 ICS 日历文件内容"""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//WUST Schedule ICS//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:武科大课表",
        "X-WR-TIMEZONE:Asia/Shanghai",
    ]

    for course in courses:
        name = course["course_name"]
        teacher = course.get("teacher", "")
        classroom = course.get("classroom", "")
        weeks = course["weeks"]
        periods = course["periods"]
        weekday = course["weekday"]

        if not weeks or not periods:
            continue

        time_start, time_end = periods_to_time_range(periods)
        is_consecutive = len(weeks) > 1 and weeks[-1] - weeks[0] == len(weeks) - 1

        if is_consecutive and len(weeks) >= 2:
            first_week = weeks[0]
            count = len(weeks)
            first_date = semester_start + timedelta(days=(weekday - 1) + (first_week - 1) * 7)

            dtstart = fmt_date(first_date) + "T" + fmt_time(time_start)
            dtend = fmt_date(first_date) + "T" + fmt_time(time_end)
            summary = escape_ics(name)

            desc_parts = []
            if teacher: desc_parts.append(f"教师: {teacher}")
            if classroom: desc_parts.append(f"教室: {classroom}")
            desc_parts.append(f"周次: {weeks[0]}-{weeks[-1]}周")
            desc_parts.append(f"节次: 第{periods[0]}-{periods[-1]}节")
            description = escape_ics("\\n".join(desc_parts))
            location = escape_ics(classroom or "")

            lines += [
                "BEGIN:VEVENT",
                f"UID:{uuid_mod.uuid4()}@wust-ics",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{description}",
                f"LOCATION:{location}",
                f"DTSTART;TZID=Asia/Shanghai:{dtstart}",
                f"DTEND;TZID=Asia/Shanghai:{dtend}",
                f"RRULE:FREQ=WEEKLY;COUNT={count}",
                "END:VEVENT",
            ]
        else:
            for w in weeks:
                date_obj = semester_start + timedelta(days=(weekday - 1) + (w - 1) * 7)
                dtstart = fmt_date(date_obj) + "T" + fmt_time(time_start)
                dtend = fmt_date(date_obj) + "T" + fmt_time(time_end)
                summary = escape_ics(name)

                desc_parts = []
                if teacher: desc_parts.append(f"教师: {teacher}")
                if classroom: desc_parts.append(f"教室: {classroom}")
                desc_parts.append(f"第{w}周")
                desc_parts.append(f"节次: 第{periods[0]}-{periods[-1]}节")
                description = escape_ics("\\n".join(desc_parts))
                location = escape_ics(classroom or "")

                lines += [
                    "BEGIN:VEVENT",
                    f"UID:{uuid_mod.uuid4()}@wust-ics",
                    f"SUMMARY:{summary}",
                    f"DESCRIPTION:{description}",
                    f"LOCATION:{location}",
                    f"DTSTART;TZID=Asia/Shanghai:{dtstart}",
                    f"DTEND;TZID=Asia/Shanghai:{dtend}",
                    "END:VEVENT",
                ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 学期日期自动检测
# ═══════════════════════════════════════════════════════════

def auto_detect_semester_start(detected_week, detected_semester, saved_config):
    """
    自动检测学期第一周周一日期。

    策略（按优先级）：
    1. 如果页面显示了当前周次，根据系统日期倒推
    2. 如果配置文件中已有本学期记录，直接使用
    3. 交互式询问用户
    """
    # 策略 1：根据当前周次 + 系统日期倒推
    if detected_week and detected_week > 0:
        today = date.today()
        this_monday = today - timedelta(days=today.weekday())
        week1_monday = this_monday - timedelta(days=(detected_week - 1) * 7)
        print(f"🔍 自动检测: 当前第{detected_week}周, 今天{today}, 推算第一周周一 = {week1_monday}")
        return week1_monday

    # 策略 2：使用配置文件中的记录
    if saved_config.get("semester_start") and saved_config.get("last_semester") == detected_semester:
        return datetime.strptime(saved_config["semester_start"], "%Y-%m-%d")

    # 策略 3：交互式询问
    return None


def resolve_semester_start(detected_week, detected_semester, saved_config, cli_value):
    """确定学期开始日期。cli_value 为命令行 --semester-start 参数"""
    if cli_value:
        return datetime.strptime(cli_value, "%Y-%m-%d")

    start = auto_detect_semester_start(detected_week, detected_semester, saved_config)
    if start:
        return start

    # 交互式输入
    print()
    print(f"📅 当前学期: {detected_semester}")
    print("   请输入本学期第一周周一的日期。")
    print("   格式: YYYY-MM-DD，例如: 2026-03-09")
    print()
    user_input = input("   日期: ").strip()
    if user_input:
        try:
            return datetime.strptime(user_input, "%Y-%m-%d")
        except ValueError:
            print("❌ 日期格式无效")
            sys.exit(1)
    else:
        print("❌ 必须提供学期开始日期")
        sys.exit(1)


# ═══════════════════════════════════════════════════════════
# Playwright 浏览器自动化（含自动登录 + 验证码识别）
# ═══════════════════════════════════════════════════════════

# CAS 统一认证登录页
CAS_LOGIN_URL = "https://auth.wust.edu.cn/lyuapServer/login?service=https://portal.wust.edu.cn/shiro-cas"


def solve_captcha(page):
    """截取验证码图片，用 ddddocr 识别算术表达式并计算答案。

    WUST CAS 验证码特征：始终是 X+Y=? 形式的加法题（单数字+单数字）。
    返回 (answer, expression) 或 (None, None)"""
    import ddddocr

    captcha_img = page.query_selector('.index-formContent-2fe6T img[alt="logo"]')
    if not captcha_img:
        for img in page.query_selector_all('img'):
            src = img.get_attribute('src') or ''
            if 'base64' in src:
                captcha_img = img
                break
    if not captcha_img:
        return None, None

    img_bytes = captcha_img.screenshot()
    ocr = ddddocr.DdddOcr(show_ad=False)
    raw = ocr.classification(img_bytes).strip()
    if not raw:
        return None, None

    # ── 后处理：修正 ddddocr 常见误识别 ──
    cleaned = raw
    cleaned = re.sub(r'[=\s]+$', '', cleaned)
    corrections = {
        '*': '+', 'x': '+', 'X': '+',
        'o': '0', 'O': '0', 'Q': '0',
        'l': '1', 'I': '1', 'i': '1',
        'Z': '2', 'z': '2',
        'S': '5', 's': '5',
        'B': '8',
        'g': '9',
    }
    for wrong, right in corrections.items():
        cleaned = cleaned.replace(wrong, right)

    # 尝试匹配算术表达式: 数字 运算符 数字
    expr_match = re.match(r'^\s*(\d+)\s*([+\-])\s*(\d+)', cleaned)
    if expr_match:
        a, op, b = int(expr_match.group(1)), expr_match.group(2), int(expr_match.group(3))
        answer = str(a + b) if op == '+' else str(a - b)
        return answer, f"{raw} → {cleaned} = {answer}"

    # 回退：尝试只提取数字做加法
    digits = re.findall(r'\d', cleaned)
    if len(digits) >= 2:
        a, b = int(digits[0]), int(digits[1])
        answer = str(a + b)
        return answer, f"{raw} → digits:{digits} → {a}+{b}={answer}"

    # 最后回退：直接返回 cleaned
    return cleaned, raw


def auto_login_cas(page, username, password, max_retries=6):
    """自动登录 CAS 统一认证平台（含验证码 OCR + 重试）"""
    print("🤖 开始自动登录 CAS 统一认证...")

    for attempt in range(1, max_retries + 1):
        print(f"   [{attempt}/{max_retries}] ", end="", flush=True)

        # 确保在正确的标签页，且表单已渲染
        try:
            tab = page.query_selector('text=账号登录')
            if tab:
                parent = tab.evaluate('el => el.parentElement')
                is_active = page.evaluate('''
                    el => {
                        let p = el.parentElement;
                        return p && p.className && p.className.includes("active");
                    }
                ''', tab)
                if not is_active:
                    tab.click()
                    page.wait_for_timeout(800)
        except Exception:
            pass

        try:
            page.wait_for_selector('#userName', timeout=10000)
        except Exception:
            print("刷新页面...")
            page.goto(CAS_LOGIN_URL, wait_until='networkidle', timeout=30000)
            page.wait_for_timeout(5000)
            # 重新点账号登录
            try:
                page.click('text=账号登录')
                page.wait_for_timeout(800)
            except Exception:
                pass
            page.wait_for_selector('#userName', timeout=10000)

        # 关闭可能覆盖在表单上的错误通知
        dismiss_modals(page)
        page.wait_for_timeout(500)

        # OCR 验证码
        answer, expr = solve_captcha(page)
        if not answer:
            print("无法识别验证码，刷新重试...")
            refresh_captcha(page)
            continue

        print(f"识别: [{expr}] → 答案: [{answer}]")

        # 清空并填写表单
        page.fill('#userName', '')
        page.fill('#password', '')
        page.fill('#captcha', '')
        page.wait_for_timeout(200)
        page.fill('#userName', username)
        page.fill('#password', password)
        page.fill('#captcha', answer)

        # 点击登录（JS 强制点击绕过遮挡）
        dismiss_modals(page)
        login_btn = page.query_selector('button:has-text("登 录")')
        if not login_btn:
            login_btn = page.query_selector('button:has-text("登录")')
        if login_btn:
            try:
                login_btn.click(timeout=5000)
            except Exception:
                login_btn.evaluate('el => el.click()')
        else:
            print("❌ 未找到登录按钮")
            return False

        # 等待响应
        page.wait_for_timeout(3000)
        dismiss_modals(page)

        # ── 判断登录结果 ──
        current_url = page.url
        page_title = page.title()

        # 成功
        if ('portal.wust.edu.cn' in current_url and 'service=' not in current_url) or \
           '服务门户' in page_title:
            print(f"   ✅ 登录成功! → {page_title}")
            return True

        # 检查错误提示
        body_text = page.evaluate('() => document.body.innerText')
        found_error = None
        for kw in ["验证码错误", "验证码不正确", "验证码过期",
                    "用户名或密码", "账号或密码", "用户名不存在",
                    "密码错误", "账号错误"]:
            if kw in body_text:
                found_error = kw
                break

        if found_error:
            print(f"   ⚠️  {found_error}")
        else:
            print(f"   ⚠️  未跳转(仍在校验页)")

        if attempt < max_retries:
            refresh_captcha(page)
            page.wait_for_timeout(800)

    print(f"   ❌ {max_retries} 次尝试后仍未成功")
    return False


def dismiss_modals(page):
    """关闭 Ant Design 消息弹窗/通知"""
    # 方式1：点「知道了」按钮关闭通知
    try:
        for text in ['知道了', '确定']:
            btn = page.query_selector(f'button:has-text("{text}")')
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(300)
                return
    except Exception:
        pass
    # 方式2：Escape 键
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    except Exception:
        pass


def refresh_captcha(page):
    """点击验证码图片刷新"""
    try:
        img = page.query_selector('.index-formContent-2fe6T img[alt="logo"]')
        if img:
            img.click()
            page.wait_for_timeout(800)
            return
    except Exception:
        pass
    # 备选：点重置按钮
    try:
        reset_btn = page.query_selector('button:has-text("重 置")')
        if reset_btn:
            reset_btn.click()
            page.wait_for_timeout(800)
    except Exception:
        pass


def login_and_save_state(username=None, password=None, headless=False):
    """登录教务系统并保存浏览器状态。
    优先尝试自动登录（需要 ddddocr），失败则回退到手动登录。

    凭证来源优先级：
    1. 函数参数
    2. 环境变量 WUST_USERNAME / WUST_PASSWORD（cron 模式）
    3. 交互式输入
    """
    from playwright.sync_api import sync_playwright

    # 读取学号密码
    if not username:
        username = os.environ.get("WUST_USERNAME", "")
    if not username:
        username = input("学号: ").strip()
    if not password:
        password = os.environ.get("WUST_PASSWORD", "")
    if not password:
        import getpass
        password = getpass.getpass("密码: ").strip()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        page = context.new_page()

        # ── 第一步：CAS 统一认证登录 ──
        print("=" * 60)
        print("🔐 CAS 统一认证登录")
        print("=" * 60)

        page.goto(CAS_LOGIN_URL, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(4000)  # 等 SPA 渲染

        # 尝试自动登录
        auto_success = auto_login_cas(page, username, password)

        if not auto_success:
            # 自动登录失败 → 手动登录
            print()
            print("=" * 60)
            print("⚠️  自动登录未成功，切换到手动模式")
            print("   请在浏览器中手动输入验证码并完成登录")
            if headless:
                print("   ❌ 当前为 headless 模式，无法手动操作")
                print("   请重新运行: python3 generate_ics.py --login --no-headless")
                browser.close()
                sys.exit(1)
            print("=" * 60)

        # ── 第二步：进入教务系统课表页面 ──
        schedule_loaded = False

        if auto_success:
            print()
            print("   自动导航到教务系统课表...")
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)
            try:
                portal_btn = page.query_selector('a:has-text("教学一体化"), a:has-text("教务系统")')
                if portal_btn:
                    portal_btn.click()
                    page.wait_for_timeout(2000)
            except Exception:
                pass
            page.goto(SCHEDULE_URL, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)
            try:
                page.wait_for_selector("#kbtable", timeout=15000)
                sfFD = page.query_selector("#sfFD")
                if sfFD and not sfFD.is_checked():
                    sfFD.check()
                    page.wait_for_timeout(500)
                print("   ✅ 课表页面加载成功")
                schedule_loaded = True
            except Exception:
                print("   ⚠️  未能自动加载课表")

        if not schedule_loaded:
            print()
            print("   请手动完成: 登录 → 教务系统 → 学期课表 → 勾选放大")
            if headless:
                print("   ❌ headless 模式无法手动操作")
                print("   请运行: python3 generate_ics.py --login --no-headless")
                browser.close()
                sys.exit(1)
            input("   确认完成后按 Enter...")

        context.storage_state(path=str(AUTH_FILE))
        print(f"✅ 浏览器状态已保存到 {AUTH_FILE.name}")
        browser.close()


def fetch_schedule(headless=True, auto_relogin=True):
    """使用已保存的浏览器状态自动抓取课表 HTML。
    如果 session 过期且 auto_relogin=True，自动重新登录。
    返回 (html, detected_semester, detected_week)"""

    from playwright.sync_api import sync_playwright

    if not AUTH_FILE.exists():
        if auto_relogin:
            print("🔐 首次使用，需要登录...")
            login_and_save_state(headless=headless)
            # 登录成功后重新调用自己
            return fetch_schedule(headless=headless, auto_relogin=False)
        else:
            print(f"❌ 未找到认证文件 {AUTH_FILE}")
            sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
            storage_state=str(AUTH_FILE),
        )
        page = context.new_page()

        print("🌐 正在访问课表页面...")
        page.goto(SCHEDULE_URL, wait_until="networkidle", timeout=30000)

        # 等待课表表格加载
        try:
            page.wait_for_selector("#kbtable", timeout=15000)
        except Exception:
            # Session 过期 → 自动重新登录
            current_url = page.url
            browser.close()

            if auto_relogin and 'auth.wust.edu.cn' in current_url:
                print("⏰ Session 已过期，自动重新登录...")
                AUTH_FILE.unlink(missing_ok=True)
                login_and_save_state(headless=headless)
                return fetch_schedule(headless=headless, auto_relogin=False)
            else:
                print("⚠️  无法加载课表表格")
                print(f"   当前页面 URL: {current_url}")
                sys.exit(1)

        # 检测当前学期和周次
        detected_semester = ""
        detected_week = None

        try:
            semester_el = page.query_selector("#xnxq01id option[selected]")
            if not semester_el:
                semester_el = page.query_selector("#xnxq01id")
            if semester_el:
                detected_semester = semester_el.evaluate("el => el.value") or ""
        except Exception:
            pass

        try:
            week_el = page.query_selector("#zc option[selected]")
            if week_el:
                val = week_el.evaluate("el => el.value") or ""
                if val:
                    detected_week = int(val)
        except Exception:
            pass

        print(f"   检测到学期: {detected_semester}, 当前周次: {detected_week or '未选中'}")

        # 切换到「全部」周次以获取完整课表
        try:
            zc_select = page.query_selector("#zc")
            if zc_select:
                current_val = zc_select.evaluate("el => el.value") or ""
                if current_val != "":
                    zc_select.select_option("")
                    page.wait_for_timeout(1000)
                    page.wait_for_selector("#kbtable", timeout=10000)
                    detected_week = None
        except Exception:
            pass

        # 勾选「放大」复选框
        try:
            sfFD = page.query_selector("#sfFD")
            if sfFD and not sfFD.is_checked():
                sfFD.check()
                page.wait_for_timeout(500)
        except Exception:
            pass

        html = page.content()
        print(f"✅ 成功获取课表页面 ({len(html)} bytes)")
        browser.close()
        return html, detected_semester, detected_week


# ═══════════════════════════════════════════════════════════
# Git 操作
# ═══════════════════════════════════════════════════════════

def git_push(message="Update schedule.ics", branch="main"):
    """将 ICS 文件提交并推送到 GitHub"""
    os.chdir(SCRIPT_DIR)

    # 检查是否在 git 仓库中
    result = subprocess.run(["git", "rev-parse", "--git-dir"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        print("⚠️  当前目录不是 Git 仓库，跳过推送")
        print("   初始化方式: git init && git remote add origin <你的仓库URL>")
        return False

    # git add
    subprocess.run(["git", "add", str(OUTPUT_FILE)], check=True)

    # 检查是否有变更
    diff_result = subprocess.run(
        ["git", "diff", "--staged", "--quiet", str(OUTPUT_FILE)],
        capture_output=True
    )
    if diff_result.returncode == 0:
        print("📦 课表无变化，跳过提交")
        return True

    # git commit
    subprocess.run(["git", "commit", "-m", message], check=True)
    print(f"📝 已提交: {message}")

    # git push
    subprocess.run(["git", "push", "origin", branch], check=True)
    print(f"🚀 已推送到 origin/{branch}")

    return True


# ═══════════════════════════════════════════════════════════
# 主程序
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="武科大强智教务系统 → ICS 课表导出工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 generate_ics.py --login --no-headless   首次登录
  python3 generate_ics.py                          日常抓取
  python3 generate_ics.py --push                   抓取并推送到 GitHub
  python3 generate_ics.py --semester-start 2026-03-09  手动指定学期日期
        """
    )
    parser.add_argument("--login", action="store_true",
                        help="手动登录并保存浏览器状态")
    parser.add_argument("--no-headless", action="store_true",
                        help="显示浏览器窗口（调试或首次登录时使用）")
    parser.add_argument("--semester-start", type=str, default=None,
                        help="学期第一周周一日期 YYYY-MM-DD（留空则自动检测）")
    parser.add_argument("--push", action="store_true",
                        help="自动 git commit & push ICS 文件")
    parser.add_argument("--push-message", type=str, default="Update schedule.ics",
                        help="Git 提交信息（默认: 'Update schedule.ics'）")
    parser.add_argument("--branch", type=str, default="main",
                        help="Git 推送分支（默认: main）")
    parser.add_argument("-o", "--output", type=str, default=None,
                        help=f"输出 ICS 文件路径（默认: {OUTPUT_FILE}）")
    parser.add_argument("--html-file", type=str, default=None,
                        help="直接解析本地 HTML 文件（调试用，跳过浏览器）")

    args = parser.parse_args()
    headless = not args.no_headless

    # ===== 获取课表 HTML =====

    if args.html_file:
        # 本地 HTML 调试模式
        html_path = Path(args.html_file)
        if not html_path.exists():
            print(f"❌ 文件不存在: {html_path}")
            sys.exit(1)
        html = html_path.read_text(encoding="utf-8")
        print(f"📄 从本地文件解析: {html_path}")
        detected_semester = ""
        detected_week = None
    elif args.login:
        # 登录模式
        login_and_save_state(headless=not args.no_headless)
        print()
        # 登录后立即抓取
        html, detected_semester, detected_week = fetch_schedule(headless=headless)
    else:
        # 正常模式：使用已保存状态
        html, detected_semester, detected_week = fetch_schedule(headless=headless)

    # ===== 解析课表 =====
    print("🔍 正在解析课表...")
    try:
        courses, parsed_semester, parsed_week = parse_schedule_from_html(html)
        detected_semester = parsed_semester or detected_semester
        if parsed_week is not None:
            detected_week = parsed_week
    except Exception as e:
        print(f"❌ 解析失败: {e}")
        debug_file = SCRIPT_DIR / "debug_schedule.html"
        debug_file.write_text(html, encoding="utf-8")
        print(f"   已保存 HTML 到 {debug_file} 供调试")
        sys.exit(1)

    print(f"✅ 解析到 {len(courses)} 门课程")

    # 打印课程列表
    for c in courses:
        weeks_display = f"{c['weeks'][0]}-{c['weeks'][-1]}" if c['weeks'] else "?"
        period_display = f"第{c['periods'][0]}-{c['periods'][-1]}节" if c['periods'] else "?"
        print(f"   📚 {c['course_name']} | 星期{c['weekday']} | "
              f"{weeks_display}周 | {period_display} | "
              f"{c.get('classroom', '')} | {c.get('teacher', '')}")

    # ===== 处理学期日期 =====
    saved_config = load_config()
    semester_start = resolve_semester_start(
        detected_week, detected_semester, saved_config, args.semester_start
    )

    if semester_start.weekday() != 0:
        print(f"⚠️  警告: {semester_start.strftime('%Y-%m-%d')} 不是周一（是星期{semester_start.weekday() + 1}）")

    print(f"📅 学期第一周周一: {semester_start.strftime('%Y-%m-%d')}")

    # 保存配置（记住已设置的学期日期，下次自动使用）
    saved_config["semester_start"] = semester_start.strftime("%Y-%m-%d")
    saved_config["last_semester"] = detected_semester
    save_config(saved_config)

    # ===== 生成 ICS =====
    print("📝 正在生成 ICS...")
    ics_content = generate_ics(courses, semester_start)

    output_path = Path(args.output) if args.output else OUTPUT_FILE
    output_path.write_text(ics_content, encoding="utf-8")
    event_count = ics_content.count("BEGIN:VEVENT")
    print(f"✅ ICS 文件已保存: {output_path}")
    print(f"   {event_count} 个日历事件, {len(ics_content)} bytes")

    # ===== 推送到 GitHub =====
    if args.push:
        print()
        git_push(message=args.push_message, branch=args.branch)

    # ===== 输出摘要 =====
    print()
    print("=" * 60)
    print("📱 ICS 订阅设置:")
    print()
    if args.push:
        # 尝试推断 GitHub Pages URL
        try:
            remote = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True
            ).stdout.strip()
            # 转换 git URL 为 Pages URL
            # git@github.com:user/repo.git → https://user.github.io/repo/schedule.ics
            # https://github.com/user/repo.git → https://user.github.io/repo/schedule.ics
            pages_url = remote
            pages_url = re.sub(r'^git@github\.com:', 'https://github.com/', pages_url)
            pages_url = re.sub(r'\.git$', '', pages_url)
            pages_url = re.sub(r'https://github\.com/', 'https://', pages_url)
            pages_url = re.sub(r'https://([^/]+)/([^/]+)$', r'https://\1.github.io/\2', pages_url)
            pages_url += '/schedule.ics'
            print(f"   🔗 订阅链接: {pages_url}")
            print(f"   ⚠️  需要在 GitHub 仓库 Settings → Pages 中启用 GitHub Pages")
            print(f"       Source 选择 'Deploy from a branch' → 分支选 '{args.branch}'")
        except Exception:
            print("   🔗 推送后访问: https://用户名.github.io/仓库名/schedule.ics")
    else:
        print("   💡 使用 --push 自动推送到 GitHub Pages")
        print(f"   💡 或设置 crontab 定时运行:")
        print(f"      0 8 * * 1 cd {SCRIPT_DIR} && python3 generate_ics.py --push")
    print("=" * 60)


if __name__ == "__main__":
    main()
