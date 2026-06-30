// ==UserScript==
// @name         武科大课表导出 ICS（仅手动）
// @namespace    https://xsddszrc.github.io/wust-schedule-ics
// @version      1.3.0
// @description  仅用于手动获取 ICS 日历：在学期课表页面（武科大是 https://bkjx.wust.edu.cn/jsxsd/xskb/xskb_list.do ）添加"导出ICS"按钮，点击下载 .ics 文件。如需自动订阅请用配套 Python 脚本。
// @author       xsddszrc
// @homepage     https://github.com/xsddszrc/wust-schedule-ics
// @updateURL    https://xsddszrc.github.io/wust-schedule-ics/wust-schedule-ics.meta.js
// @downloadURL  https://xsddszrc.github.io/wust-schedule-ics/wust-schedule-ics.user.js
// @match        https://bkjx.wust.edu.cn/jsxsd/xskb/xskb_list.do*
// @grant        none
// ==/UserScript==

(function () {
    'use strict';

    // ============ 配置区（可按需修改） ============
    // 黄家湖校区作息时间。key: 节次号, value: [开始时间, 结束时间]
    // 青山校区上午早 20 分钟，参照 Python 脚本开头的注释修改
    const PERIOD_TIME = {
        1:  ['08:20', '09:05'],
        2:  ['09:15', '10:00'],
        3:  ['10:20', '11:05'],
        4:  ['11:15', '12:00'],
        5:  ['14:00', '14:45'],
        6:  ['14:55', '15:40'],
        7:  ['16:00', '16:45'],
        8:  ['16:55', '17:40'],
        9:  ['18:40', '19:25'],
        10: ['19:35', '20:20'],
        11: ['20:40', '21:25'],
        12: ['21:35', '22:20'],
    };

    // 学期第一周周一日期（用户首次使用时会弹出输入框，之后保存在 localStorage）
    const STORAGE_KEY = 'wust_ics_semester_start';

    // ============ 工具函数 ============

    /** 解析周次字符串，返回周次数组。例如 "1-17(周)" → [1..17], "1,3-4,6-11,13,15,17(周)" → [1,3,4,6,7,8,9,10,11,13,15,17] */
    function parseWeeks(weekStr) {
        if (!weekStr) return [];
        // 去掉 "(周)" 后缀
        weekStr = weekStr.replace(/\(周\)/g, '').trim();
        if (!weekStr) return [];

        const weeks = new Set();
        const parts = weekStr.split(',');
        for (const part of parts) {
            const range = part.split('-');
            if (range.length === 2) {
                const start = parseInt(range[0], 10);
                const end = parseInt(range[1], 10);
                if (!isNaN(start) && !isNaN(end)) {
                    for (let w = start; w <= end; w++) weeks.add(w);
                }
            } else {
                const w = parseInt(range[0], 10);
                if (!isNaN(w)) weeks.add(w);
            }
        }
        return [...weeks].sort((a, b) => a - b);
    }

    /** 解析节次字符串，返回节次数组。例如 "[01-02节]" → [1,2], "[07-08-09-10节]" → [7,8,9,10], "[12节]" → [12] */
    function parsePeriods(periodStr) {
        if (!periodStr) return [];
        const match = periodStr.match(/\[([^\]]+)\]/);
        if (!match) return [];
        const inner = match[1].replace(/节/g, '');
        const allNums = inner.split('-').map(n => parseInt(n, 10)).filter(n => !isNaN(n));
        if (allNums.length === 0) return [];
        if (allNums.length === 1) return [allNums[0]];
        // 取首尾组成连续区间
        const s = allNums[0];
        const e = allNums[allNums.length - 1];
        const periods = [];
        for (let p = s; p <= e; p++) periods.push(p);
        return periods;
    }

    /** 从节次数组计算开始时间和结束时间 */
    function periodsToTime(periods) {
        if (periods.length === 0) return { start: '08:00', end: '09:35' };
        const first = periods[0];
        const last = periods[periods.length - 1];
        const start = PERIOD_TIME[first] ? PERIOD_TIME[first][0] : '08:00';
        const end = PERIOD_TIME[last] ? PERIOD_TIME[last][1] : '09:35';
        return { start, end };
    }

    /** 格式化日期为 YYYYMMDD */
    function fmtDate(date) {
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, '0');
        const d = String(date.getDate()).padStart(2, '0');
        return y + m + d;
    }

    /** 格式化时间为 HHMMSS */
    function fmtTime(timeStr) {
        return timeStr.replace(/:/g, '') + '00';
    }

    /** 转义 ICS 文本 */
    function escapeICS(text) {
        return text.replace(/[\\;,]/g, '\\$&').replace(/\n/g, '\\n');
    }

    /** 生成唯一 UID */
    function uid() {
        return Date.now().toString(36) + Math.random().toString(36).substr(2, 9) + '@wust-ics';
    }

    // ============ 主解析逻辑 ============

    function parseSchedule() {
        const table = document.getElementById('kbtable');
        if (!table) {
            alert('未找到课表表格 #kbtable，请确认你在学期课表页面。');
            return null;
        }

        // 获取学年学期
        const semesterSelect = document.getElementById('xnxq01id');
        const semester = semesterSelect ? semesterSelect.value : '';

        // 收集所有课程的详细 div（class="kbcontent"）
        // 注意：CSS 选择器 .kbcontent 不会匹配 .kbcontent1，只匹配 <div class="kbcontent">
        const detailDivs = table.querySelectorAll('div.kbcontent');
        const courseMap = new Map();

        for (const div of detailDivs) {
            const html = div.innerHTML.trim();
            if (html === '&nbsp;' || html === '') continue;

            // 从 div id 解析 UUID 和 weekday
            // id 格式: UUID-weekday-displayType (如 E6302A12DEDC40D2A67B38AB22ECC910-1-2)
            const divId = div.id;
            const idParts = divId.split('-');
            const weekday = parseInt(idParts[idParts.length - 2], 10);
            const uuid = idParts.slice(0, -2).join('-');
            const key = uuid + '-' + weekday;

            // 按 --------------------- 分割多个课程（同一格内有线上线下交替等）
            const courseBlocks = html.split(/<br\s*\/?\s*>[-—]{10,}<br\s*\/?\s*>/);

            for (const block of courseBlocks) {
                const trimmed = block.trim();
                if (!trimmed || trimmed === '&nbsp;') continue;

                const info = parseCourseBlock(trimmed);
                if (!info) continue;

                // 使用 (uuid, weekday, weekStr) 作为去重 key
                // 同一周次=跨行连堂课→合并；不同周次=独立课程→保留
                const weekKey = info.weekStr || info.weeks.join(',');
                const subKey = key + '|' + weekKey;

                if (courseMap.has(subKey)) {
                    const existing = courseMap.get(subKey);
                    const allPeriods = new Set([...existing.periods, ...info.periods]);
                    existing.periods = [...allPeriods].sort((a, b) => a - b);
                } else {
                    info.weekday = weekday;
                    info.uuid = uuid;
                    courseMap.set(subKey, info);
                }
            }
        }

        let courses = [...courseMap.values()];

        // 最终去重：同课程名+同星期+同教师+周次有交集→合并（处理跨行重复 UUID）
        const dedupMap = new Map();
        for (const c of courses) {
            const dedupKey = c.courseName + '|' + c.weekday + '|' + (c.teacher || '');
            if (dedupMap.has(dedupKey)) {
                const existing = dedupMap.get(dedupKey);
                const existingWeeks = new Set(existing.weeks);
                const hasOverlap = c.weeks.some(w => existingWeeks.has(w));
                if (hasOverlap) {
                    const allPeriods = new Set([...existing.periods, ...c.periods]);
                    existing.periods = [...allPeriods].sort((a, b) => a - b);
                } else {
                    dedupMap.set(dedupKey + '__split__' + dedupMap.size, c);
                }
            } else {
                dedupMap.set(dedupKey, c);
            }
        }
        courses = [...dedupMap.values()];

        return { courses, semester };
    }

    function parseCourseBlock(html) {
        // 格式:
        //   课程名<br/>
        //   <font title='老师'>教师名</font><br/>
        //   <font title='课堂名称'>教学班XXXX</font><br/>
        //   <font title='周次(节次)'>1-17(周)[01-02节]</font><br/>
        //   <font title='教室'>教室名</font><br/>
        if (!html || html.trim() === '&nbsp;' || html.trim() === '') return null;

        // --- 课程名：取第一个 <br> 之前的内容，去除 HTML 标签 ---
        const firstBr = html.split(/<br\s*\/?\s*>/i)[0];
        let courseName = firstBr.replace(/<[^>]+>/g, '').trim();
        // 如果课程名为空（比如直接以 <font 开头），尝试取 <font 之前的内容
        if (!courseName) {
            const beforeFont = html.split(/<font/i)[0];
            courseName = beforeFont.replace(/<[^>]+>/g, '').trim();
        }
        if (!courseName) return null;

        // --- 提取 <font title='...'>...</font>（同时支持单双引号） ---
        const fontData = {};
        const fontRegex = /<font[^>]*title\s*=\s*['"]([^'"]*)['"][^>]*>([^<]*)<\/font>/gi;
        let fm;
        while ((fm = fontRegex.exec(html)) !== null) {
            fontData[fm[1]] = fm[2];
        }

        const teacher = fontData['老师'] || '';
        const classroom = fontData['教室'] || '';
        const className = fontData['课堂名称'] || '';

        // --- 周次(节次) ---
        const weekPeriodRaw = fontData['周次(节次)'] || '';
        let weekStr = '';
        let periodStr = '';
        if (weekPeriodRaw) {
            // "1-17(周)[01-02节]" 或 "1,3-4,6-11,13,15,17(周)[05-06节]"
            const wpMatch = weekPeriodRaw.match(/^(.+\(周\))(\[.+\])$/);
            if (wpMatch) {
                weekStr = wpMatch[1];
                periodStr = wpMatch[2];
            } else {
                const wMatch = weekPeriodRaw.match(/(.+\(周\))/);
                const pMatch = weekPeriodRaw.match(/(\[.+\])/);
                if (wMatch) weekStr = wMatch[1];
                if (pMatch) periodStr = pMatch[1];
            }
        }

        const weeks = parseWeeks(weekStr);
        const periods = parsePeriods(periodStr);

        return {
            courseName,
            teacher,
            className,
            classroom,
            weeks,
            periods,
            weekStr,
            periodStr,
        };
    }

    // ============ ICS 生成 ============

    function generateICS(courses, semesterStart) {
        const lines = [];
        lines.push('BEGIN:VCALENDAR');
        lines.push('VERSION:2.0');
        lines.push('PRODID:-//WUST Schedule ICS//CN');
        lines.push('CALSCALE:GREGORIAN');
        lines.push('METHOD:PUBLISH');
        lines.push('X-WR-CALNAME:武科大课表');
        lines.push('X-WR-TIMEZONE:Asia/Shanghai');

        for (const course of courses) {
            const { courseName, teacher, classroom, weeks, periods, weekday } = course;
            if (weeks.length === 0 || periods.length === 0) continue;

            const { start: timeStart, end: timeEnd } = periodsToTime(periods);

            // 周次连续 → 使用 RRULE；否则逐周生成独立事件
            const isConsecutive = weeks.length > 1 &&
                weeks[weeks.length - 1] - weeks[0] === weeks.length - 1;

            if (isConsecutive && weeks.length >= 2) {
                const firstWeek = weeks[0];
                const count = weeks.length;

                // 学期第一周周一 + (weekday-1) 天 + (firstWeek-1)*7 天
                const firstDate = new Date(semesterStart);
                firstDate.setDate(firstDate.getDate() + (weekday - 1) + (firstWeek - 1) * 7);

                const dtstart = fmtDate(firstDate) + 'T' + fmtTime(timeStart);
                const dtend = fmtDate(firstDate) + 'T' + fmtTime(timeEnd);

                const summary = escapeICS(courseName);
                const descParts = [];
                if (teacher) descParts.push('教师: ' + teacher);
                if (classroom) descParts.push('教室: ' + classroom);
                descParts.push('周次: ' + weeks[0] + '-' + weeks[weeks.length - 1] + '周');
                descParts.push('节次: 第' + periods[0] + '-' + periods[periods.length - 1] + '节');
                const description = escapeICS(descParts.join('\\n'));
                const location = escapeICS(classroom || '');

                lines.push('BEGIN:VEVENT');
                lines.push('UID:' + uid());
                lines.push('SUMMARY:' + summary);
                if (description) lines.push('DESCRIPTION:' + description);
                if (location) lines.push('LOCATION:' + location);
                lines.push('DTSTART;TZID=Asia/Shanghai:' + dtstart);
                lines.push('DTEND;TZID=Asia/Shanghai:' + dtend);
                lines.push('RRULE:FREQ=WEEKLY;COUNT=' + count);
                lines.push('END:VEVENT');
            } else {
                for (const w of weeks) {
                    const date = new Date(semesterStart);
                    date.setDate(date.getDate() + (weekday - 1) + (w - 1) * 7);

                    const dtstart = fmtDate(date) + 'T' + fmtTime(timeStart);
                    const dtend = fmtDate(date) + 'T' + fmtTime(timeEnd);

                    const summary = escapeICS(courseName);
                    const descParts = [];
                    if (teacher) descParts.push('教师: ' + teacher);
                    if (classroom) descParts.push('教室: ' + classroom);
                    descParts.push('第' + w + '周');
                    descParts.push('节次: 第' + periods[0] + '-' + periods[periods.length - 1] + '节');
                    const description = escapeICS(descParts.join('\\n'));
                    const location = escapeICS(classroom || '');

                    lines.push('BEGIN:VEVENT');
                    lines.push('UID:' + uid());
                    lines.push('SUMMARY:' + summary);
                    if (description) lines.push('DESCRIPTION:' + description);
                    if (location) lines.push('LOCATION:' + location);
                    lines.push('DTSTART;TZID=Asia/Shanghai:' + dtstart);
                    lines.push('DTEND;TZID=Asia/Shanghai:' + dtend);
                    lines.push('END:VEVENT');
                }
            }
        }

        lines.push('END:VCALENDAR');
        return lines.join('\r\n');
    }

    // ============ UI 按钮 ============

    function addExportButton() {
        const toolbar = document.querySelector('.Nsb_layout_r.title');
        const container = toolbar ? toolbar.parentElement : document.querySelector('.Nsb_layout_r');

        if (!container) {
            const btn = document.createElement('button');
            btn.textContent = '📅 导出ICS';
            btn.style.cssText = 'position:fixed;top:10px;right:10px;z-index:9999;padding:10px 20px;font-size:16px;background:#4CAF50;color:white;border:none;border-radius:5px;cursor:pointer;';
            btn.onclick = doExport;
            document.body.appendChild(btn);
            return;
        }

        const btn = document.createElement('button');
        btn.textContent = '📅 导出ICS';
        btn.className = 'button el-button';
        btn.style.cssText = 'margin-left:12px;background:#4CAF50;color:white;font-weight:bold;';
        btn.onclick = doExport;

        if (toolbar) {
            toolbar.appendChild(btn);
        } else {
            container.insertBefore(btn, container.firstChild);
        }
    }

    function doExport() {
        let semesterStartStr = localStorage.getItem(STORAGE_KEY);
        const semesterSelect = document.getElementById('xnxq01id');
        const currentSemester = semesterSelect ? semesterSelect.options[semesterSelect.selectedIndex].text : '';

        const promptMsg = semesterStartStr
            ? '学期第一周周一日期（留空使用已保存的 ' + semesterStartStr + '）：\n当前学期: ' + currentSemester
            : '请设置学期第一周周一的日期（格式 YYYY-MM-DD）：\n当前学期: ' + currentSemester + '\n例如: 2026-02-23';

        const input = prompt(promptMsg, semesterStartStr || '');
        if (input === null) return;

        if (input.trim()) {
            semesterStartStr = input.trim();
            localStorage.setItem(STORAGE_KEY, semesterStartStr);
        }

        if (!semesterStartStr) {
            alert('请先设置学期开始日期！');
            return;
        }

        const semesterStart = new Date(semesterStartStr + 'T00:00:00+08:00');
        if (isNaN(semesterStart.getTime())) {
            alert('日期格式无效，请使用 YYYY-MM-DD 格式，例如: 2026-02-23');
            return;
        }

        // getDay() 返回 0=周日, 1=周一, ..., 6=周六
        if (semesterStart.getDay() !== 1) {
            const dayNames = '日一二三四五六';
            const confirmMsg = '输入的日期是星期' + dayNames[semesterStart.getDay()] +
                '，不是周一。\n是否自动调整为当周周一？';
            if (confirm(confirmMsg)) {
                const day = semesterStart.getDay();
                const diff = day === 0 ? 6 : day - 1;
                semesterStart.setDate(semesterStart.getDate() - diff);
            } else {
                return;
            }
        }

        const result = parseSchedule();
        if (!result || result.courses.length === 0) {
            alert('未能解析到课表数据，请确认页面已加载完整。');
            return;
        }

        const ics = generateICS(result.courses, semesterStart);
        const blob = new Blob([ics], { type: 'text/calendar;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = '武科大课表_' + (result.semester || 'schedule') + '.ics';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        alert('课表已导出！\n共 ' + result.courses.length + ' 门课程。\n\n📱 导入方法：\n• iPhone: 设置→日历→账户→添加账户→其他→添加已订阅的日历\n• Mac: 日历→文件→导入\n• Android: 用 Google 日历或 Outlook 打开 .ics 文件');
    }

    // ============ 入口 ============

    function init() {
        if (document.getElementById('kbtable')) {
            addExportButton();
        } else {
            setTimeout(init, 500);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
