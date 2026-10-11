# -*- coding: utf-8 -*-
import os
import sys

if os.name == 'nt':
    try:
        os.system('chcp 65001 > nul')
    except Exception:
        pass
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    except Exception:
        pass

import requests
import json
import re
import random
import time
import uuid
import base64
import shutil
import asyncio
from datetime import datetime
from urllib.parse import urlencode

try:
    from rich.console import Console, Group
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    from rich.align import Align
    from rich.prompt import Prompt as RichPrompt
    from rich import box
    _HAS_RICH = True
except ImportError:
    _HAS_RICH = False

TOTAL_TOKENS = 0
MAX_THREADS = 1
NAME_TYPE = "vn"
INTERACT_MIN = 300
INTERACT_MAX = 600

VERSION = "1.6"
AUTHOR = "KhuyCoderxThaiViLuan"

console = Console() if _HAS_RICH else None

dashboard_lines = {}
dashboard_stats = {
    "total_ok": 0,
    "total_fail": 0,
    "total_tokens": 0,
    "start_ts": 0,
    "spin_tick": 0,
}
log_buffer = []
MAX_LOG_LINES = 5

_stop_flag = False


def _term_width():
    try:
        return shutil.get_terminal_size((120, 30)).columns
    except Exception:
        return 120


def _term_height():
    try:
        return shutil.get_terminal_size((120, 30)).lines
    except Exception:
        return 30


def _dash_update(idx, **kw):
    st = dashboard_lines.setdefault(idx, {
        "status": "Khởi động",
        "success": 0,
        "fail": 0,
        "reason": "",
        "finished": False,
        "bar": None,
        "flag": None,
        "last_was_fail": False,
        "uid": None,
        "start_ts": time.time(),
        "end_ts": None,
    })
    for k, v in kw.items():
        if k == "done":
            if v and not st["finished"]:
                st["finished"] = True
                st["end_ts"] = time.time()
        else:
            st[k] = v


def _dash_bump_ok(n=1):
    dashboard_stats["total_ok"] += n


def _dash_bump_fail(n=1):
    dashboard_stats["total_fail"] += n


def _push_log(idx, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    log_buffer.append(f"[dim]{ts}[/] [bold cyan]>>> [{idx}][/] {msg}")
    if len(log_buffer) > MAX_LOG_LINES:
        log_buffer.pop(0)


def _gradient_bar(current, total, length=18, btype=None):
    if total <= 0:
        return Text("-" * length, style="grey37")
    ratio = max(0.0, min(1.0, current / total))
    n_filled = int(length * ratio)
    n_empty = length - n_filled

    t = Text()
    for i in range(n_filled):
        pos = i / max(1, length - 1)
        if pos < 0.5:
            r = 255
            g = int(255 * (pos * 2))
            b = 0
        else:
            r = int(255 * (1 - (pos - 0.5) * 2))
            g = 255
            b = 0
        t.append("▰", style=f"rgb({r},{g},{b})")
    t.append("▱" * n_empty, style="grey30")
    return t


def _shorten(text, max_len):
    if text is None:
        return ""
    text = str(text)
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return text[:max_len - 3] + "..."


def render_dashboard():
    w = _term_width()
    term_h = _term_height()
    now = time.time()
    elapsed = now - dashboard_stats["start_ts"] if dashboard_stats["start_ts"] else 0
    done = sum(1 for s in dashboard_lines.values() if s["finished"])
    total_ok = dashboard_stats["total_ok"]
    total_fail = dashboard_stats["total_fail"]
    total_tokens = dashboard_stats["total_tokens"] or TOTAL_TOKENS
    speed = total_ok / elapsed if elapsed > 0 else 0

    elements = []

    header = Table(show_header=False, expand=True, box=None, padding=(0, 1))
    header.add_column("L", justify="left")
    header.add_column("R", justify="right")
    header.add_row(
        f"[bold black on dark_orange] HOT [/] "
        f"[bold dodger_blue1]AUTO[/] [bold magenta]REG[/] [bold cyan]PRO5[/]  |  "
        f"[bold yellow]{total_tokens} acc[/]  |  [bold green]{MAX_THREADS} luồng[/]",
        f"[bold gold1]v{VERSION} by {AUTHOR}[/]"
    )
    header.add_row(
        f"[bold green]{total_ok} page[/]  [bold red]{total_fail} lỗi[/]  "
        f"[bold cyan]{done}/{total_tokens} xong[/]",
        f"[bold yellow]{speed:.2f}/s[/]  [bold magenta]{int(elapsed)}s[/]"
    )
    elements.append(Panel(
        header,
        title="[bold gold1]AUTO REG PRO5 - DASHBOARD[/]",
        border_style="deep_sky_blue1",
        box=box.ROUNDED,
        padding=(0, 1)
    ))

    tbl = Table(
        show_header=True, header_style="bold gold1",
        expand=True, box=box.SIMPLE,
        border_style="cyan",
        padding=(0, 0)
    )
    tbl.add_column("#", width=3, justify="center", no_wrap=True)
    tbl.add_column("UID", width=20, justify="center", no_wrap=True)
    tbl.add_column("TRẠNG THÁI", width=24, no_wrap=True, overflow="ellipsis")
    tbl.add_column("TIẾN TRÌNH", width=18, no_wrap=True)
    tbl.add_column("OK", width=4, justify="right", no_wrap=True)
    tbl.add_column("FAIL", width=5, justify="right", no_wrap=True)
    tbl.add_column("TIME", width=8, justify="right", no_wrap=True)

    if not dashboard_lines:
        tbl.add_row(
            Text("-", style="cyan"),
            Text("--", style="grey37"),
            Text("Đang chờ dữ liệu...", style="grey37"),
            Text("▱" * 14, style="grey37"),
            Text("0", style="grey37"),
            Text("0", style="grey37"),
            Text("0s", style="grey37"),
        )
    else:
        for idx in sorted(dashboard_lines.keys()):
            st = dashboard_lines[idx]
            flag = st.get("flag")
            s, f = st["success"], st["fail"]

            if flag == "stop":
                icon = Text("X", style="bold red")
            elif flag == "block":
                icon = Text("B", style="bold magenta")
            elif flag == "rate_limit":
                icon = Text("R", style="bold yellow")
            elif flag == "die":
                icon = Text("D", style="bold red")
            elif st["finished"]:
                icon = Text("v", style="bold blue")
            else:
                icon = Text("*", style="cyan")

            if flag == "stop":
                status = Text("LUỒNG ĐÃ DỪNG", style="bold red")
            elif flag == "block":
                status = Text("BỊ BLOCK", style="bold magenta")
            elif flag == "rate_limit":
                status = Text("RATE LIMIT", style="bold yellow")
            elif flag == "die":
                status = Text("DIE", style="bold red")
            elif st["finished"]:
                status = Text(f"{st['status']}", style="bold blue")
            else:
                last_was_fail = st.get("last_was_fail", False)
                if last_was_fail and f > 0:
                    col = "red" if s == 0 else "yellow"
                elif s > 0:
                    col = "green"
                elif f > 0:
                    col = "red"
                else:
                    col = "cyan"
                status = Text(_shorten(st.get("status", ""), 22), style=col)

            bar_info = st.get("bar")
            if flag in ("stop", "block", "die", "rate_limit") or st["finished"]:
                prog = _gradient_bar(1, 1, 12)
            elif bar_info:
                cur, tot, btype = bar_info
                prog = _gradient_bar(cur, tot, 10, btype=btype)
                prog.append(" ")
                if btype == "reg":
                    prog.append(f"{int(cur)}/{int(tot)}", style="grey70")
                elif btype == "delay":
                    prog.append(f"{int(max(0, tot-cur))}s", style="grey70")
            else:
                prog = Text("▱" * 12, style="grey37")

            start_ts = st.get("start_ts", now)
            if st["finished"] and st.get("end_ts"):
                el = int(st["end_ts"] - start_ts)
            else:
                el = int(now - start_ts)
            if el < 60:
                time_txt = Text(f"{el}s", style="cyan")
            elif el < 3600:
                time_txt = Text(f"{el//60}m{el%60:02d}s", style="cyan")
            else:
                time_txt = Text(f"{el//3600}h{(el%3600)//60:02d}m", style="cyan")

            ok_txt = Text(str(s), style="bold green" if s > 0 else "grey37")
            fail_txt = Text(str(f), style="bold red" if f > 0 else "grey37")

            uid = st.get("uid")
            if uid:
                label = Text(f"{uid}", style="bold white")
            else:
                label = Text(f"[{idx}]", style="bold white")

            tbl.add_row(icon, label, status, prog, ok_txt, fail_txt, time_txt)

    elements.append(Panel(
        tbl,
        title="[bold cyan]BẢNG ĐIỀU KHIỂN ĐA LUỒNG[/]",
        border_style="cyan", box=box.ROUNDED, padding=(0, 0)
    ))

    if term_h < 30:
        log_show = 3
    elif term_h < 40:
        log_show = 6
    elif term_h < 50:
        log_show = 10
    else:
        log_show = MAX_LOG_LINES
    recent = log_buffer[-log_show:] if log_buffer else ["[dim]Đang khởi động...[/]"]
    elements.append(Panel(
        "\n".join(recent),
        title="[bold green]NHẬT KÝ HOẠT ĐỘNG[/]",
        border_style="green", box=box.ROUNDED, padding=(0, 1)
    ))

    return Group(*elements)


async def ui_render_loop():
    while True:
        try:
            with Live(render_dashboard(), refresh_per_second=2, console=console, screen=True) as live:
                while True:
                    dashboard_stats["spin_tick"] += 1
                    live.update(render_dashboard())
                    await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(0.5)


TOKEN_STATS = {}


def _update_stat(idx, token, proxy, status, success, fail, reason="", existing=None):
    TOKEN_STATS[idx] = {
        "token": token[:40] if token else "",
        "proxy": proxy or "DIRECT",
        "status": status,
        "success": success,
        "fail": fail,
        "reason": reason,
        "existing": existing,
    }


def render_logo(width=None):
    if width is None:
        width = _term_width()
    logo = Text()
    if width >= 110:
        logo.append("██████╗ ███████╗ ██████╗     ██████╗ ██████╗  ██████╗ ███████╗\n", style="bold dodger_blue1")
        logo.append("██╔══██╗██╔════╝██╔════╝     ██╔══██╗██╔══██╗██╔═══██╗██╔════╝\n", style="bold deep_sky_blue1")
        logo.append("██████╔╝█████╗  ██║  ███╗    ██████╔╝██████╔╝██║   ██║███████╗\n", style="bold cyan")
        logo.append("██╔══██╗██╔══╝  ██║   ██║    ██╔═══╝ ██╔══██╗██║   ██║╚════██║\n", style="bold violet")
        logo.append("██║  ██║███████╗╚██████╔╝    ██║     ██║  ██║╚██████╔╝███████║\n", style="bold magenta")
        logo.append("╚═╝  ╚═╝╚══════╝ ╚═════╝     ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚══════╝\n", style="bold magenta")
    else:
        logo.append(" +---------------------------+\n", style="bold dodger_blue1")
        logo.append(f" |  PRO5 AUTO REG - v{VERSION}     |\n", style="bold cyan")
        logo.append(" |  Android Real Behavior    |\n", style="bold deep_sky_blue1")
        logo.append(f" |  by {AUTHOR}  |\n", style="bold gold1")
        logo.append(" +---------------------------+", style="bold magenta")
    return logo


def print_banner():
    console.print(Align.center(render_logo(_term_width())))
    console.print()


def print_section(title, icon="*", color="cyan"):
    console.print()
    console.print(Panel(
        Align.center(Text.from_markup(f"[bold {color}]{title}[/]")),
        border_style=color, box=box.ROUNDED, padding=(0, 1)
    ))


def ask_prompt(question, default=""):
    return RichPrompt.ask(f"[bold yellow]> {question}[/]", default=default).strip()


def ask_menu(question, choices, default="1"):
    return RichPrompt.ask(f"[bold yellow]> {question}[/]",
                          choices=[str(c) for c in choices], default=default).strip()


def show_menu(title, options, color="cyan"):
    t = Table(show_header=False, box=None, padding=(0, 2), expand=True)
    t.add_column("K", style="bold yellow", width=6, justify="center", no_wrap=True)
    t.add_column("L", style="bold white")
    t.add_column("N", style="dim cyan", justify="right", no_wrap=True)
    for key, label, note in options:
        t.add_row(f"[{key}]", label, note or "")
    console.print(Panel(t, title=f"[bold {color}]{title}[/]",
                        border_style=color, box=box.ROUNDED, padding=(0, 1)))


def print_info(text, title="", color="cyan"):
    console.print(Panel(text, title=f"[bold {color}]{title}[/]" if title else None,
                        border_style=color, box=box.ROUNDED, padding=(0, 1)))


def print_welcome():
    guide = Table(show_header=False, expand=True, box=None, padding=(0, 1))
    guide.add_column("I", style="bold gold1", width=4)
    guide.add_column("T", style="bold white")
    guide.add_row("1.", "Công cụ tự động [bold green]tạo Page PRO5[/] từ token Facebook (Android API).")
    guide.add_row("2.", "Hỗ trợ [bold cyan]chạy đa luồng[/] - mỗi token một luồng riêng.")
    guide.add_row("3.", "Token sẽ được [bold green]check UID ngay khi nhập[/], token lỗi nhập lại.")
    guide.add_row("4.", "Proxy nạp từ [bold yellow]file .txt[/], tự đổi proxy khi tạo page lỗi.")
    guide.add_row("5.", f"Tác giả: [bold gold1]{AUTHOR}[/]  |  Phiên bản: [bold gold1]v{VERSION}[/]")
    console.print(Panel(guide, title="[bold gold1]HƯỚNG DẪN SỬ DỤNG[/]",
                        border_style="gold1", box=box.ROUNDED, padding=(0, 1)))


def _split_4parts_proxy(s):
    p = s.split(':')
    if len(p) != 4: return None
    idx = [i for i, x in enumerate(p) if x.isdigit() and 1 <= len(x) <= 5]
    if len(idx) != 1: return None
    pi = idx[0]
    if pi == 1: host, port, user, pwd = p
    elif pi == 3: user, pwd, host, port = p
    else: return None
    if host.isdigit(): return None
    return user, pwd, host, port


def format_proxy(s):
    if not s: return None
    s = s.strip()
    if not s: return None
    if s.startswith(("http://", "https://", "socks")):
        return s
    if '@' in s: return f"http://{s}"
    if re.match(r'^[\w\.\-]+:\d{2,5}$', s): return f"http://{s}"
    parsed = _split_4parts_proxy(s)
    if parsed:
        u, p, h, po = parsed
        return f"http://{u}:{p}@{h}:{po}"
    return s


def _looks_like_proxy(s):
    if not s: return False
    s = s.strip()
    if s.startswith(("http://", "https://", "socks")): return True
    if re.match(r'^[\w\.\-]+:\d{2,5}$', s): return True
    if re.match(r'^[\w\.\-]+:[\w\.\-]+@[\w\.\-]+:\d{2,5}$', s): return True
    if _split_4parts_proxy(s): return True
    return False


def load_proxies_from_file(filepath):
    """Đọc danh sách proxy từ file txt (mỗi dòng 1 proxy)."""
    proxies = []
    if not filepath:
        return proxies
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                fmt = format_proxy(line)
                if fmt:
                    proxies.append(fmt)
    except Exception as e:
        if console:
            console.print(f"[bold red]Lỗi đọc file proxy: {e}[/]")
    return proxies


def verify_proxy(proxy_str, timeout=12):
    if not proxy_str:
        return {"alive": True, "ip":"?","country":"?","countryCode":"",
                "timezone":"UTC","reason":"DIRECT","display":"DIRECT"}
    formatted = format_proxy(proxy_str)
    proxies = {"http": formatted, "https": formatted}
    try:
        r = requests.get(
            "http://ip-api.com/json/?fields=query,country,countryCode,isp,timezone,status,message",
            proxies=proxies, timeout=(5, timeout))
        if r.status_code == 200:
            try: d = r.json()
            except: return {"alive": False, "reason": "non-json", "countryCode": "", "timezone": "UTC"}
            if d.get("status") == "success":
                return {"alive": True, "ip": d.get("query","?"),
                        "country": d.get("country","?"), "countryCode": d.get("countryCode",""),
                        "timezone": d.get("timezone","UTC"), "reason": ""}
            return {"alive": False, "reason": f"ip-api: {d.get('message','?')}",
                    "countryCode": "", "timezone": "UTC"}
        return {"alive": False, "reason": f"HTTP {r.status_code}", "countryCode": "", "timezone": "UTC"}
    except Exception as e:
        return {"alive": False, "reason": f"{type(e).__name__}: {str(e)[:60]}",
                "countryCode": "", "timezone": "UTC"}


def _is_token(s):
    if not s: return False
    return bool(re.match(r'^EAAAA[A-Za-z0-9_\-]{20,}', s.strip()))


def parse_token_line(line):
    result = {"token": "", "proxy": None}
    if not line: return result
    raw = line.strip()
    if not raw: return result

    parts = [p.strip() for p in raw.split('|') if p.strip()]
    if not parts:
        return result

    first = parts[0]
    result["token"] = first

    for p in parts[1:]:
        if _looks_like_proxy(p):
            result["proxy"] = format_proxy(p)
            break
    return result


ANDROID_PROFILES = [
    ("SM-S928B",  "Samsung Galaxy S24 Ultra", "samsung", "qcom",       12, 1440, 3120, 505, "14"),
    ("SM-S918B",  "Samsung Galaxy S23 Ultra", "samsung", "qcom",       12, 1440, 3088, 500, "14"),
    ("SM-S911B",  "Samsung Galaxy S23",       "samsung", "qcom",        8, 1080, 2340, 425, "14"),
    ("SM-S921B",  "Samsung Galaxy S24",       "samsung", "exynos",      8, 1080, 2340, 416, "14"),
    ("SM-A546E",  "Samsung Galaxy A54",       "samsung", "exynos",      8, 1080, 2340, 405, "14"),
    ("SM-A155F",  "Samsung Galaxy A15",       "samsung", "mediatek",    6, 1080, 2340, 396, "14"),
    ("SM-F946B",  "Samsung Galaxy Z Fold5",   "samsung", "qcom",       12, 1812, 2176, 373, "14"),
    ("SM-F731B",  "Samsung Galaxy Z Flip5",   "samsung", "qcom",        8, 1080, 2640, 426, "14"),
    ("2210132C",  "Xiaomi 13",                "Xiaomi",  "qcom",       12, 1080, 2400, 414, "14"),
    ("2211133C",  "Xiaomi 13 Pro",            "Xiaomi",  "qcom",       12, 1440, 3200, 522, "14"),
    ("2304FPN6DC", "Xiaomi 13 Ultra",         "Xiaomi",  "qcom",       16, 1440, 3200, 522, "14"),
    ("23078PND5G", "Xiaomi 13T Pro",          "Xiaomi",  "mediatek",   12, 1220, 2712, 446, "14"),
    ("23127PN0CC", "Xiaomi 14",               "Xiaomi",  "qcom",       12, 1200, 2670, 460, "14"),
    ("2311DRK48G", "Redmi Note 13 Pro",       "Xiaomi",  "mediatek",    8, 1220, 2712, 446, "14"),
    ("M2101K6G",  "Xiaomi Redmi Note 10 Pro", "Xiaomi",  "qcom",        8, 1080, 2400, 395, "13"),
    ("CPH2525",   "OPPO Reno8 Pro",           "OPPO",    "mediatek",   12, 1080, 2412, 394, "13"),
    ("CPH2557",   "OPPO Reno11",              "OPPO",    "mediatek",    8, 1080, 2412, 394, "14"),
    ("PHK110",    "OnePlus 11",               "OnePlus", "qcom",       12, 1440, 3216, 525, "14"),
    ("CPH2451",   "OnePlus Nord 3",           "OnePlus", "mediatek",   12, 1240, 2772, 451, "14"),
    ("PJD110",    "OnePlus 12",               "OnePlus", "qcom",       16, 1440, 3168, 510, "14"),
    ("V2220A",    "vivo X90 Pro",             "vivo",    "mediatek",   12, 1260, 2800, 453, "14"),
    ("V2311",     "vivo X100",                "vivo",    "mediatek",   12, 1260, 2800, 453, "14"),
    ("V2318",     "vivo V30",                 "vivo",    "qcom",        8, 1260, 2800, 453, "14"),
    ("RMX3741",   "realme GT5",               "realme",  "qcom",       12, 1240, 2772, 451, "14"),
    ("RMX3823",   "realme 11 Pro",            "realme",  "mediatek",    8, 1080, 2412, 394, "14"),
    ("M2103K19G", "POCO X3 Pro",              "Xiaomi",  "qcom",        8, 1080, 2400, 395, "13"),
    ("23049PCD8G", "POCO F5",                 "Xiaomi",  "qcom",       12, 1080, 2400, 395, "14"),
    ("24069PC21G", "POCO F6",                 "Xiaomi",  "qcom",       12, 1220, 2712, 446, "14"),
    ("N2301",     "OnePlus Nord CE 3",        "OnePlus", "qcom",        8, 1080, 2412, 394, "14"),
    ("V2204",     "vivo Y36",                 "vivo",    "qcom",        8, 1080, 2388, 395, "13"),
    ("CPH2387",   "OPPO A78",                 "OPPO",    "mediatek",    8, 1080, 2400, 394, "14"),
    ("moto g84 5G", "Motorola Moto G84",      "motorola", "qcom",       8, 1080, 2400, 402, "14"),
    ("moto g stylus 5G", "Motorola Moto G Stylus 5G", "motorola", "qcom", 6, 1080, 2400, 393, "14"),
    ("Pixel 8 Pro",  "Google Pixel 8 Pro",    "Google",  "tensor",     12, 1344, 2992, 489, "14"),
    ("Pixel 8",      "Google Pixel 8",        "Google",  "tensor",      8, 1080, 2400, 428, "14"),
    ("Pixel 8a",     "Google Pixel 8a",       "Google",  "tensor",      8, 1080, 2400, 428, "14"),
    ("Pixel 7 Pro",  "Google Pixel 7 Pro",    "Google",  "tensor",     12, 1440, 3120, 512, "14"),
    ("Pixel 7a",     "Google Pixel 7a",       "Google",  "tensor",      8, 1080, 2400, 429, "14"),
    ("2201117TG", "Xiaomi 12",                "Xiaomi",  "qcom",        8, 1080, 2400, 419, "13"),
    ("22081212C", "Xiaomi 12S Ultra",         "Xiaomi",  "qcom",       12, 1440, 3200, 522, "13"),
    ("SM-G991B",  "Samsung Galaxy S21",       "samsung", "exynos",      8, 1080, 2400, 421, "14"),
    ("SM-G998B",  "Samsung Galaxy S21 Ultra", "samsung", "exynos",     12, 1440, 3200, 515, "14"),
    ("SM-S901B",  "Samsung Galaxy S22",       "samsung", "qcom",        8, 1080, 2340, 425, "14"),
    ("SM-S908B",  "Samsung Galaxy S22 Ultra", "samsung", "qcom",       12, 1440, 3088, 500, "14"),
    ("LE2123",    "OnePlus 9 Pro",            "OnePlus", "qcom",       12, 1440, 3216, 525, "13"),
    ("IN2023",    "OnePlus 8 Pro",            "OnePlus", "qcom",       12, 1440, 3168, 513, "12"),
    ("GM1913",    "OnePlus 7 Pro",            "OnePlus", "qcom",       12, 1440, 3120, 516, "12"),
]

ANDROID_OS_BUILDS = {
    "12": ["SQ1A.220205.002", "SQ3A.220605.009.B1", "SP1A.210812.016"],
    "13": ["TQ1A.230105.001", "TQ3A.230605.012", "TP1A.220905.004"],
    "14": ["UP1A.231005.007", "UQ1A.240205.004", "UKQ1.230917.001"],
    "15": ["AP1A.240505.003", "AP2A.240605.003"],
}

ANDROID_KERNEL = {
    "12": "4.19.191-g1e8d7c4b1a2c",
    "13": "5.10.101-android13-8-g4b5c6d7e8f9a",
    "14": "5.15.104-android14-11-g1a2b3c4d5e6f",
    "15": "6.1.25-android15-8-g7a8b9c0d1e2f",
}

ANDROID_SECURITY_PATCH = {
    "12": "2023-08-05",
    "13": "2024-01-05",
    "14": "2024-06-05",
    "15": "2024-09-05",
}

FBAV_POOL_ANDROID = [
    "555.0.0.49.59", "556.0.0.41.87", "557.0.0.38.101",
    "558.0.0.43.95", "559.0.0.39.78", "560.0.0.44.90",
    "561.0.0.42.83", "562.0.0.40.76",
]
FBBV_POOL_ANDROID = ["926292501", "935874623", "944512387", "951203477", "962834551"]

ANDROID_CARRIERS = {
    "VN": [("Viettel","45204"),("Mobifone","45201"),("Vinaphone","45202"),
           ("Vietnamobile","45205"),("Gmobile","45207"),("Reddi","45208"),("Itelecom","45209")],
    "US": [("Verizon","311480"),("AT&T","310410"),("T-Mobile","310260"),("Sprint","310120"),("US Cellular","311220")],
    "CA": [("Rogers","302720"),("Bell","302610"),("Telus","302220"),("Freedom","302490")],
    "GB": [("EE","23430"),("O2","23410"),("Vodafone","23415"),("Three","23420")],
    "DE": [("Telekom","26201"),("Vodafone","26202"),("O2","26203"),("1&1","26223")],
    "FR": [("Orange","20801"),("SFR","20810"),("Bouygues","20820"),("Free","20815")],
    "IT": [("TIM","22201"),("Vodafone","22210"),("WindTre","22288"),("Iliad","22250")],
    "ES": [("Movistar","21407"),("Vodafone","21401"),("Orange","21403"),("Yoigo","21404")],
    "NL": [("KPN","20408"),("Vodafone","20404"),("T-Mobile","20416")],
    "SE": [("Telia","24001"),("Tele2","24007"),("Telenor","24008")],
    "CH": [("Swisscom","22801"),("Sunrise","22802"),("Salt","22803")],
    "AT": [("A1","23201"),("Magenta","23203"),("Drei","23205")],
    "BE": [("Proximus","20601"),("Orange","20610"),("BASE","20620")],
    "PT": [("MEO","26803"),("NOS","26801"),("Vodafone","26806")],
    "IE": [("Vodafone","27201"),("Three","27205"),("Eir","27203")],
    "PL": [("Orange","26003"),("Play","26006"),("T-Mobile","26002"),("Plus","26001")],
    "CZ": [("O2","23002"),("T-Mobile","23001"),("Vodafone","23003")],
    "NO": [("Telenor","24201"),("Telia","24202"),("Ice","24206")],
    "DK": [("TDC","23801"),("Telenor","23802"),("Telia","23820")],
    "FI": [("Elisa","24405"),("Telia","24491"),("DNA","24412")],
    "JP": [("NTT Docomo","44010"),("au","44051"),("SoftBank","44020"),("Rakuten","44011")],
    "KR": [("SK Telecom","45005"),("KT","45008"),("LG U+","45006")],
    "SG": [("Singtel","52501"),("StarHub","52505"),("M1","52503"),("Simba","52510")],
    "HK": [("CSL","45400"),("SmarTone","45406"),("3 Hong Kong","45404"),("China Mobile HK","45412")],
    "TW": [("Chunghwa","46692"),("Taiwan Mobile","46697"),("FarEasTone","46601")],
    "MY": [("Maxis","50212"),("Celcom","50219"),("Digi","50216"),("U Mobile","50218")],
    "TH": [("AIS","52003"),("TrueMove","52004"),("dtac","52005")],
    "PH": [("Globe","51502"),("Smart","51503"),("Sun Cellular","51505"),("DITO","51566")],
    "AE": [("Etisalat","42402"),("du","42403")],
    "IL": [("Partner","42501"),("Cellcom","42502"),("Pelephone","42503")],
    "AU": [("Telstra","50501"),("Optus","50502"),("Vodafone","50503")],
    "NZ": [("Spark","53001"),("Vodafone","53002"),("2degrees","53024")],
}

ANDROID_LOCALE_MAP = {
    "VN": ("vi_VN", "Asia/Ho_Chi_Minh", "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"),
    "US": ("en_US", "America/New_York", "en-US,en;q=0.9"),
    "CA": ("en_CA", "America/Toronto", "en-CA,en;q=0.9"),
    "GB": ("en_GB", "Europe/London", "en-GB,en;q=0.9"),
    "DE": ("de_DE", "Europe/Berlin", "de-DE,de;q=0.9,en;q=0.8"),
    "FR": ("fr_FR", "Europe/Paris", "fr-FR,fr;q=0.9,en;q=0.8"),
    "IT": ("it_IT", "Europe/Rome", "it-IT,it;q=0.9,en;q=0.8"),
    "ES": ("es_ES", "Europe/Madrid", "es-ES,es;q=0.9,en;q=0.8"),
    "NL": ("nl_NL", "Europe/Amsterdam", "nl-NL,nl;q=0.9,en;q=0.8"),
    "SE": ("sv_SE", "Europe/Stockholm", "sv-SE,sv;q=0.9,en;q=0.8"),
    "CH": ("de_CH", "Europe/Zurich", "de-CH,de;q=0.9,en;q=0.8"),
    "AT": ("de_AT", "Europe/Vienna", "de-AT,de;q=0.9,en;q=0.8"),
    "BE": ("nl_BE", "Europe/Brussels", "nl-BE,nl;q=0.9,en;q=0.8"),
    "PT": ("pt_PT", "Europe/Lisbon", "pt-PT,pt;q=0.9,en;q=0.8"),
    "IE": ("en_IE", "Europe/Dublin", "en-IE,en;q=0.9"),
    "PL": ("pl_PL", "Europe/Warsaw", "pl-PL,pl;q=0.9,en;q=0.8"),
    "CZ": ("cs_CZ", "Europe/Prague", "cs-CZ,cs;q=0.9,en;q=0.8"),
    "NO": ("nb_NO", "Europe/Oslo", "nb-NO,nb;q=0.9,en;q=0.8"),
    "DK": ("da_DK", "Europe/Copenhagen", "da-DK,da;q=0.9,en;q=0.8"),
    "FI": ("fi_FI", "Europe/Helsinki", "fi-FI,fi;q=0.9,en;q=0.8"),
    "JP": ("ja_JP", "Asia/Tokyo", "ja-JP,ja;q=0.9,en;q=0.8"),
    "KR": ("ko_KR", "Asia/Seoul", "ko-KR,ko;q=0.9,en;q=0.8"),
    "SG": ("en_SG", "Asia/Singapore", "en-SG,en;q=0.9"),
    "HK": ("zh_HK", "Asia/Hong_Kong", "zh-HK,zh;q=0.9,en;q=0.8"),
    "TW": ("zh_TW", "Asia/Taipei", "zh-TW,zh;q=0.9,en;q=0.8"),
    "MY": ("ms_MY", "Asia/Kuala_Lumpur", "ms-MY,ms;q=0.9,en;q=0.8"),
    "TH": ("th_TH", "Asia/Bangkok", "th-TH,th;q=0.9,en;q=0.8"),
    "PH": ("en_PH", "Asia/Manila", "en-PH,en;q=0.9"),
    "AE": ("ar_AE", "Asia/Dubai", "ar-AE,ar;q=0.9,en;q=0.8"),
    "IL": ("he_IL", "Asia/Jerusalem", "he-IL,he;q=0.9,en;q=0.8"),
    "AU": ("en_AU", "Australia/Sydney", "en-AU,en;q=0.9"),
    "NZ": ("en_NZ", "Pacific/Auckland", "en-NZ,en;q=0.9"),
}


def _gen_android_id():
    return ''.join(random.choice("0123456789abcdef") for _ in range(16))


def _gen_imei_android():
    base = "35" + ''.join(random.choice("0123456789") for _ in range(12))
    ds = [int(d) for d in base]
    total = 0
    for i, d in enumerate(reversed(ds)):
        if i % 2 == 0:
            d *= 2
            if d > 9: d -= 9
        total += d
    return base + str((10 - total % 10) % 10)


def gen_android_device(cc="VN", tz="Asia/Ho_Chi_Minh"):
    cc = (cc or "VN").upper()
    if cc in ANDROID_CARRIERS and cc in ANDROID_LOCALE_MAP:
        loc, tzone, lang = ANDROID_LOCALE_MAP[cc]
        carriers = ANDROID_CARRIERS[cc]
    else:
        loc, tzone, lang = "vi_VN", "Asia/Ho_Chi_Minh", "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"
        carriers = ANDROID_CARRIERS["VN"]
        cc = "VN"
    carrier, mccmnc = random.choice(carriers)
    mcc, mnc = mccmnc[:3], mccmnc[3:]
    model_id, mname, brand, soc, ram, sw, sh, dpi, os_ver = random.choice(ANDROID_PROFILES)
    build = random.choice(ANDROID_OS_BUILDS.get(os_ver, ["UP1A.231005.007"]))
    kernel = ANDROID_KERNEL.get(os_ver, "5.15.104-android14-11-g1a2b3c4d5e6f")
    security_patch = ANDROID_SECURITY_PATCH.get(os_ver, "2024-06-05")
    fbav = random.choice(FBAV_POOL_ANDROID)
    fbbv = random.choice(FBBV_POOL_ANDROID)
    fbrv = str(random.randint(0, 99999999))
    return {
        "platform": "android",
        "brand": brand,
        "model_id": model_id,
        "market_name": mname,
        "soc": soc,
        "ram_gb": ram,
        "screen_w": sw,
        "screen_h": sh,
        "density_dpi": dpi,
        "scale": 2,
        "os_version": os_ver,
        "build": build,
        "kernel": kernel,
        "security_patch": security_patch,
        "device_id": gen_uuid(),
        "machine_id": gen_uuid(),
        "family_device_id": gen_uuid(),
        "advertising_id": gen_uuid(),
        "session_id": gen_uuid(),
        "android_id": _gen_android_id(),
        "install_id": gen_uuid(),
        "carrier": carrier,
        "mcc": mcc,
        "mnc": mnc,
        "mccmnc": mccmnc,
        "sim_hni": mccmnc,
        "locale": loc,
        "timezone": tzone,
        "accept_lang": lang,
        "fbav": fbav,
        "fbbv": fbbv,
        "fbrv": fbrv,
        "conn_type": random.choice(["WIFI", "MOBILE", "WIFI"]),
        "bandwidth": random.choice([1500, 3000, 5000, 8000, 12000, 20000]),
        "battery": random.randint(18, 92),
        "charging": random.choice(["0", "1"]),
        "storage_free_mb": int(random.choice([64, 128, 256, 512]) * 1024 * random.uniform(0.15, 0.75)),
        "country_code": cc,
        "serial_number": gen_uuid()[:16].upper(),
        "wifi_mac": gen_mac(),
        "bluetooth_mac": gen_mac(),
        "meid": ''.join(random.choice("0123456789ABCDEF") for _ in range(14)),
        "imei": _gen_imei_android(),
        "build_fingerprint": f"{brand}/{model_id}/{model_id}:{os_ver}/{build}/{build}:user/release-keys",
        "fingerprint": f"{brand}/{model_id}/{model_id}:{os_ver}/{build}/{build}:user/release-keys",
    }


def build_android_headers(token, d):
    fbav = d["fbav"]
    fbbv = d["fbbv"]
    fbrv = d["fbrv"]
    model_id = d["model_id"]
    os_ver = d["os_version"]
    ua = (
        f"[FBAN/FB4A;FBAV/{fbav};FBBV/{fbbv};"
        f"FBDM/{{density={d['density_dpi']/160:.1f},width={d['screen_w']},height={d['screen_h']}}};"
        f"FBLC/{d['locale']};FBRV/{fbrv};"
        f"FBCR/{d['carrier']};FBMF/{d['brand']};FBBD/{d['brand']};"
        f"FBPN/com.facebook.katana;"
        f"FBDV/{model_id};FBSV/{os_ver};"
        f"FBOP/1;FBCA/arm64-v8a:armeabi-v7a;]"
    )
    return {
        "authorization": f"OAuth {token}",
        "content-type": "application/x-www-form-urlencoded",
        "user-agent": ua,
        "accept-language": d["accept_lang"],
        "x-fb-friendly-name": "FbBloksActionRootQuery",
        "x-graphql-client-library": "graphservice",
        "x-fb-tasos-experimental": "1",
        "x-fb-rmd": "state=URL_ELIGIBLE",
        "x-fb-connection-type": d["conn_type"],
        "x-fb-sim-hni": d["sim_hni"],
        "x-fb-carrier": d["carrier"],
        "x-fb-locale": d["locale"],
        "x-fb-timezone": d["timezone"],
        "x-fb-build": d["build"],
        "x-fb-hardware": d["model_id"],
        "accept-encoding": "gzip, deflate, br",
        "x-fb-http-engine": "Liger",
        "x-fb-device": d["market_name"],
        "x-fb-device-id": d["device_id"],
        "x-fb-machine-id": d["machine_id"],
        "x-fb-family-device-id": d["family_device_id"],
        "x-fb-android-id": d["android_id"],
        "x-fb-connection-bandwidth": str(d["bandwidth"]),
        "x-fb-connection-quality": random.choice(["EXCELLENT","GOOD","MODERATE"]),
        "x-fb-net-hni": d["mccmnc"],
        "x-fb-ram": str(d["ram_gb"]),
        "x-fb-screen": f"{d['screen_w']}x{d['screen_h']}",
        "x-fb-density": str(d["density_dpi"]),
        "x-fb-battery": str(d["battery"]),
        "x-fb-charging": d["charging"],
        "x-fb-storage-free": str(d["storage_free_mb"]),
        "x-fb-fbav": fbav,
        "x-fb-fbbv": fbbv,
        "x-fb-fbrv": fbrv,
        "x-fb-session-id": d["session_id"],
        "x-fb-advertising-id": d["advertising_id"],
        "x-fb-serial": d["serial_number"],
        "x-fb-wifi-mac": d["wifi_mac"],
        "x-fb-bluetooth-mac": d["bluetooth_mac"],
        "x-fb-meid": d["meid"],
        "x-fb-imei": d["imei"],
        "x-fb-fingerprint": d["fingerprint"],
        "x-fb-os-version": os_ver,
        "x-fb-mcc": d["mcc"],
        "x-fb-mnc": d["mnc"],
        "x-fb-soc": d["soc"],
        "x-fb-soc-model": d["model_id"],
        "x-fb-install-id": d["install_id"],
        "x-fb-kernel": d["kernel"],
        "x-fb-security-patch": d["security_patch"],
    }


ANDROID_OUI = ["00:1A:11","00:1B:2F","00:1C:B3","00:1E:64","00:21:19","00:23:76",
    "00:26:37","00:2A:6A","00:37:6D","00:3A:98","00:4C:E5","00:50:F1",
    "00:5A:13","00:6B:8E","00:7B:18","00:8E:F2","00:9A:CD","00:A0:C9",
    "00:B0:D0","00:C0:CA","00:D0:B7","00:E0:4C","00:F4:B9","04:0E:3C",
    "04:18:D6","04:5E:A4","04:79:70","04:8D:38","04:A1:51","04:B1:67",
    "04:C2:3E","04:CE:14","04:D4:C4","04:E6:76","08:00:27","08:10:74",
    "08:3E:5D","08:57:00","08:60:6E","08:6D:41","08:76:95","08:9B:4B",
    "08:B2:A3","08:C5:E1","08:D4:2B","08:E9:F6","0C:16:8C","0C:27:24",
    "0C:3E:9F","0C:47:C9","0C:5F:35","0C:6E:4F","0C:82:30","0C:89:10",
    "0C:9A:42","0C:B1:CF","0C:C4:7A","0C:D6:BD","0C:DC:7E","0C:F3:61"]


def gen_mac():
    oui = random.choice(ANDROID_OUI)
    parts = [int(x, 16) for x in oui.split(":")]
    rest = [random.randint(0, 255) for _ in range(3)]
    return ':'.join(f"{b:02X}" for b in parts + rest)


def gen_uuid(): return str(uuid.uuid4()).upper()


BLOKS_VERSION_ANDROID = "d1583f026cccd22345fea8de656bb1d8162dabcca3249d6a0610be47545ec31a"
STYLES_ID_ANDROID = "6100e7e89411ccf67ace027cedecd84f"

DOC_ID_APPROOT  = "10537346116379767315688237631"
DOC_ID_ACTION   = "119940804217734265480409226803"

APP_ID_UNIFIED_LANDING   = "com.bloks.www.unified.profile.creation"
APP_ID_LANDING_ANDROID   = "com.bloks.www.additional.profile.plus.creation"
APP_ID_NAME_SUBMIT_ANDROID     = f"{APP_ID_LANDING_ANDROID}.action.name.submit"
APP_ID_CAT_SUBMIT_ANDROID      = f"{APP_ID_LANDING_ANDROID}.action.category.submit"
APP_ID_ADDRESS_SEARCH_ANDROID  = f"{APP_ID_LANDING_ANDROID}.action.address.search"
APP_ID_DETAILS_SUBMIT_ANDROID  = f"{APP_ID_LANDING_ANDROID}.action.details.submit"
APP_ID_PHOTO_SUBMIT_ANDROID    = f"{APP_ID_LANDING_ANDROID}.action.photo_and_cta.submit"
APP_ID_NOTIF_SUBMIT_ANDROID    = f"{APP_ID_LANDING_ANDROID}.action.notifications.submit"

REFERRER = "pages_tab_launch_point_unified_creation"
VARIANT  = 8


def _nt_context_android():
    return {
        "using_white_navbar": True,
        "theme_params": [
            {"value": ["three_neutral_gray"], "design_system_name": "XMDS"},
            {"value": ["DARKER_PRIMARY_DEEMPHASIZED_BUTTON_BACKGROUND_TEST"],
             "design_system_name": "FDS"},
        ],
        "styles_id": STYLES_ID_ANDROID,
        "is_flipper_enabled": False,
        "pixel_ratio": 2,
        "is_push_on": True,
        "debug_tooling_metadata_token": None,
        "bloks_version": BLOKS_VERSION_ANDROID,
    }


def _nav_chain():
    return ("PagesManagerActivity:pages_tab_launch_point:"
            "com.bloks.www.unified.profile.creation:"
            "com.bloks.www.additional.profile.plus.creation")


def _base_client_params(profile_plus_id="0", screen="name"):
    return {
        "entrypoint_logging_data": {
            "fb_profile_editing_session_entry_point": None,
            "field_edit_screen_entry_point": None,
        },
        "profile_plus_id": profile_plus_id,
        "cp_upsell_declined": 0,
        "off_platform_creator_reachout_id": "",
        "session_id": None,
        "nav_chain": _nav_chain(),
    }


def _base_server_params(screen, name="", **extra):
    sp = {
        "referrer": REFERRER,
        "INTERNAL__latency_qpl_marker_id": 36707139,
        "creation_source": "android",
        "variant": VARIANT,
        "screen": screen,
        "INTERNAL__latency_qpl_instance_id": int(time.time() * 1000),
    }
    if name:
        sp["name"] = name
    sp.update(extra)
    return sp


def _build_inner(screen, name="", profile_plus_id="0", **cip_extra):
    cip = _base_client_params(profile_plus_id, screen)
    cip.update(cip_extra)
    sp = _base_server_params(screen, name)
    if screen == "name":
        sp["is_applus_creation_mvp"] = 1
    return {"client_input_params": cip, "server_params": sp}


def _post_graphql_android(session, token, device, friendly, app_id, inner,
                           doc_id=DOC_ID_ACTION, purpose="fetch", timeout=60):
    params_str = json.dumps(inner, separators=(",", ":"))
    variables = {
        "params": {
            "params": params_str,
            "bloks_versioning_id": BLOKS_VERSION_ANDROID,
            "app_id": app_id,
        },
        "scale": "2",
        "nt_context": _nt_context_android(),
        "use_native_entrypoint_for_stars_on_reels": True,
    }
    data = {
        "method": "post", "pretty": "false", "format": "json",
        "server_timestamps": "true", "locale": device["locale"], "purpose": purpose,
        "fb_api_req_friendly_name": friendly,
        "fb_api_caller_class": "graphservice",
        "client_doc_id": doc_id,
        "fb_api_client_context": '{"is_background":false}',
        "variables": json.dumps(variables, separators=(",", ":")),
        "fb_api_analytics_tags": '["GraphServices"]',
        "client_trace_id": str(uuid.uuid4()),
    }
    headers = build_android_headers(token, device)
    headers["x-fb-friendly-name"] = friendly
    try:
        r = session.post("https://graph.facebook.com/graphql",
                         data=urlencode(data), headers=headers, timeout=timeout)
    except requests.RequestException as e:
        return None, f"Network: {e}"
    if r.status_code != 200:
        return None, f"HTTP {r.status_code}: {r.text[:300]}"
    try:
        return r.json(), None
    except ValueError:
        return None, f"Not JSON: {r.text[:300]}"


def _extract_action_android(js):
    try:
        b = (js.get("data", {}).get("fb_bloks_action", {})
               .get("root_action", {}).get("action", {})
               .get("action_bundle", {}).get("bloks_bundle_action"))
        if not b: return None
        obj = json.loads(b)
        p = obj.get("layout", {}).get("bloks_payload", {})
        return p.get("action") or obj.get("action") or b
    except Exception:
        return None


def _extract_page_id_android(a, js):
    if a:
        for pat in (r'dq8\s+"ADDITIONAL_PROFILE_PLUS_CREATION:page_id"\s+"(\d+)"',
                    r'"ADDITIONAL_PROFILE_PLUS_CREATION:page_id"\s*,\s*"(\d+)"'):
            m = re.search(pat, a)
            if m: return m.group(1)
    m = re.search(r'"page_id"\s*:\s*"?(\d{6,})"?', json.dumps(js))
    return m.group(1) if m else None


def _extract_pp_id_android(a, js):
    if a:
        m = re.search(
            r'ADDITIONAL_PROFILE_PLUS_CREATION:profile_plus_id["\s,]+["\s]*(\d{6,})',
            a)
        if m:
            return m.group(1)
    try:
        m = re.search(r'"profile_plus_id"\s*:\s*"?(\d{6,})"?', json.dumps(js))
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def _extract_error_android(a, js):
    if a:
        m = re.search(r'\(bk\.action\.io\.Toast,\s*"([^"]+)"', a)
        if m:
            msg = m.group(1)
            if is_rate_limit(msg):
                return f"RATE_LIMIT: {msg}"
            return msg
        for kw in ("create_error", "profile_creation_error", "error_message"):
            if kw in a:
                if is_rate_limit(a):
                    return f"RATE_LIMIT: Detected {kw}"
                return f"Detected {kw}"
    if "errors" in js:
        try:
            s = json.dumps(js["errors"])[:300]
            if is_rate_limit(s):
                return f"RATE_LIMIT: {s}"
            return s
        except: pass
    return None


ARRAY_HO  = ["Nguyễn","Trần","Lê","Phạm","Hoàng","Huỳnh","Võ","Vũ","Phan","Trương","Bùi","Đặng","Đỗ","Ngô","Hồ","Dương","Đinh"]
ARRAY_LOT = ["Công","Đức","Duy","Gia","Anh","Hồng","Đình","Quốc","Quỳnh","Vĩnh","Văn","Thị","Hữu","Minh","Thu","Ngọc","Hải","Xuân","Bảo","Thành","Thanh","Hoài"]
ARRAY_TEN = ["Hưng","Anh","Văn","Tuấn","Hoàng","Quốc","Nam","Giang","Khang","Dương","Phúc","Thiên","Hùng","Kiệt","Châu","Quỳnh","Huệ","Khánh","Trân","Yên","Lợi","Danh","Vinh","Nhi","Hân","Đạt","Cường","Linh","Trang","Lan","Hương","Thảo","Phú","Tâm","Phát","Lộc"]
ARRAY_FIRST_US_MALE = ["James","John","Robert","Michael","William","David","Richard","Joseph","Thomas","Charles"]
ARRAY_FIRST_US_FEMALE = ["Mary","Patricia","Jennifer","Linda","Elizabeth","Barbara","Susan","Jessica","Sarah","Karen"]
ARRAY_LAST_US = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Rodriguez","Martinez"]


def gen_name():
    if NAME_TYPE == "us":
        first = random.choice(ARRAY_FIRST_US_MALE) if random.random() < 0.7 else random.choice(ARRAY_FIRST_US_FEMALE)
        return f"{first} {random.choice(ARRAY_LAST_US)}"
    return f"{random.choice(ARRAY_HO)} {random.choice(ARRAY_LOT)} {random.choice(ARRAY_TEN)}"


TOKEN_DIE_KW = ["OAuthException", "Invalid OAuth access token", "access token has expired",
                "The access token could not be decrypted", "session has been invalidated",
                "session is invalid", "user logged out", "user has been checkpointed",
                "user is blocked", '"code":190', '"code":102', '"code":467',
                '"code":458', '"code":459', '"code":460', '"code":463', '"code":464']

RATE_LIMIT_KW = [
    "gần đây bạn đã tạo quá nhiều trang",
    "gan day ban da tao qua nhieu trang",
    "bạn đã tạo quá nhiều trang",
    "ban da tao qua nhieu trang",
    "quá nhiều trang",
    "qua nhieu trang",
    "too many pages",
    "you've created too many pages",
    "you have created too many pages",
    "recently created too many",
    "create too many pages",
    "rate limit",
    "rate_limit",
    "too many requests",
    "quá nhiều yêu cầu",
]


def is_die(text):
    if not text: return False
    t = text.lower()
    return any(k.lower() in t for k in TOKEN_DIE_KW)


def is_rate_limit(text):
    if not text: return False
    t = str(text).lower()
    return any(k.lower() in t for k in RATE_LIMIT_KW)


def check_user(token, proxy=None):
    params = {"access_token": token, "fields": "id,name"}
    proxies = None
    if proxy:
        fmt = format_proxy(proxy)
        if fmt: proxies = {"http": fmt, "https": fmt}
    try:
        r = requests.get("https://graph.facebook.com/me", params=params, proxies=proxies, timeout=(5, 20))
        try: d = r.json()
        except: return None, None, "proxy_error:non-json"
        if "id" in d: return d["id"], d.get("name", ""), None
        code = d.get("error", {}).get("code")
        if code in (190, 102, 463, 467, 458, 459, 460):
            return None, None, "token_die"
        return None, None, f"api_error_{code}"
    except requests.exceptions.ProxyError as e: return None, None, f"proxy_error:{str(e)[:60]}"
    except requests.exceptions.Timeout: return None, None, "timeout"
    except requests.exceptions.ConnectionError: return None, None, "proxy_error:conn"
    except Exception as e: return None, None, f"net:{type(e).__name__}"


def check_pages(token, proxy=None, thread_idx=None):
    uid, _, err = check_user(token, proxy)
    if not uid:
        if err == "token_die": return None, "token_die", None
        if err and err.startswith("proxy_error"): return None, "proxy_die", None
        if err == "timeout": return None, "timeout", None
        return None, "soft_error", None

    fmt = format_proxy(proxy) if proxy else None
    proxies = {"http": fmt, "https": fmt} if fmt else None

    last_err = None
    for attempt in range(2):
        try:
            r = requests.get(
                "https://graph.facebook.com/me/accounts",
                params={"access_token": token, "fields": "id,name", "limit": 100},
                proxies=proxies, timeout=15)
            try:
                d = r.json()
            except ValueError:
                last_err = "non-json"
                time.sleep(0.8)
                continue

            if "error" in d:
                code = d["error"].get("code")
                if code in (190, 102, 463, 467, 458, 459, 460):
                    return None, "token_die", None
                last_err = f"api_error_{code}"
                time.sleep(0.8)
                continue

            data = d.get("data", [])
            total = len(data)
            next_url = d.get("paging", {}).get("next")
            hops = 0
            while next_url and hops < 10:
                try:
                    rr = requests.get(next_url, proxies=proxies, timeout=15)
                    dd = rr.json()
                    total += len(dd.get("data", []))
                    next_url = dd.get("paging", {}).get("next")
                    hops += 1
                except Exception:
                    break
            return total, "ok", uid
        except requests.exceptions.ProxyError:
            return None, "proxy_die", None
        except requests.exceptions.Timeout:
            last_err = "timeout"
            time.sleep(0.8)
            continue
        except requests.exceptions.ConnectionError:
            return None, "proxy_die", None
        except Exception as e:
            last_err = f"net:{type(e).__name__}"
            time.sleep(0.8)
            continue

    return None, "soft_error", None


def calc_needed(token, proxy, target, thread_idx=None):
    last_status = None
    for i in range(4):
        existing, status, uid = check_pages(token, proxy, thread_idx)
        last_status = status
        if status in ("ok", "token_die", "proxy_die"): break
        if i < 3: time.sleep(1.5 * (i + 1))

    if last_status == "token_die":
        return 0, None, "token_die", None
    if last_status == "proxy_die":
        return 0, None, "proxy_die", None
    if last_status == "ok":
        need = max(0, target - existing)
        if need == 0: return 0, existing, "already_enough", uid
        return need, existing, "ok", uid
    return 0, None, "unknown_soft", None


def _sleep_interruptible(sec):
    end = time.time() + sec
    while time.time() < end:
        if _stop_flag: return
        time.sleep(0.5)


def _step_name_submit(session, token, device, name, thread_idx=None):
    fr = f"FbBloksActionRootQuery-{APP_ID_NAME_SUBMIT_ANDROID}"
    inner = _build_inner("name", name=name, profile_plus_id="0")
    js, err = _post_graphql_android(session, token, device, fr,
                                     APP_ID_NAME_SUBMIT_ANDROID, inner,
                                     doc_id=DOC_ID_ACTION)
    if err:
        return False, f"Name: {err}", False
    if is_die(json.dumps(js)):
        return False, "TOKEN DIE (Name)", True
    a = _extract_action_android(js)
    e = _extract_error_android(a, js)
    if e:
        return False, f"Name error: {e}", False
    return True, None, False


def _step_category_submit(session, token, device, name, category_ids,
                           thread_idx=None):
    fr = f"FbBloksActionRootQuery-{APP_ID_CAT_SUBMIT_ANDROID}"
    inner = _build_inner("category", name=name, profile_plus_id="0")
    inner["client_input_params"]["category_ids"] = category_ids
    js, err = _post_graphql_android(session, token, device, fr,
                                     APP_ID_CAT_SUBMIT_ANDROID, inner,
                                     doc_id=DOC_ID_ACTION)
    if err:
        return False, None, f"Category: {err}", False
    if is_die(json.dumps(js)):
        return False, None, "TOKEN DIE (Category)", True
    a = _extract_action_android(js)
    e = _extract_error_android(a, js)
    if e:
        return False, None, f"Category error: {e}", False
    pp_id = _extract_pp_id_android(a or "", js)
    if not pp_id:
        return False, None, "Không lấy được profile_plus_id", False
    return True, pp_id, None, False


def _step_address_search(session, token, device, query, thread_idx=None):
    fr = f"FbBloksActionRootQuery-{APP_ID_ADDRESS_SEARCH_ANDROID}"
    inner = {
        "client_input_params": {"search_query_string": query},
        "server_params": {
            "search_bar_id": "h4drp5:112",
            "results_container_id": "h4drp5:113",
            "INTERNAL__latency_qpl_marker_id": 36707139,
            "INTERNAL__latency_qpl_instance_id": int(time.time() * 1000),
        },
    }
    js, err = _post_graphql_android(session, token, device, fr,
                                     APP_ID_ADDRESS_SEARCH_ANDROID, inner,
                                     doc_id=DOC_ID_ACTION)
    if err:
        return False, None, f"AddressSearch: {err}", False
    if is_die(json.dumps(js)):
        return False, None, "TOKEN DIE (AddressSearch)", True
    a = _extract_action_android(js)
    city_id = None
    if a:
        m = re.search(r'"city_id"\s*:\s*"?(\d{6,})"?', a)
        if m:
            city_id = m.group(1)
    return True, city_id, None, False


def _step_details_submit(session, token, device, profile_plus_id,
                          name, city_id=None, thread_idx=None):
    fr = f"FbBloksActionRootQuery-{APP_ID_DETAILS_SUBMIT_ANDROID}"
    cip = {
        "profile_plus_id": profile_plus_id,
        "street": "asia",
        "zip": "212435",
        "bio": "coding",
        "website": "",
        "phone_number": "",
        "email": "",
        "regular_hours_type": 0,
    }
    if city_id:
        cip["city_id"] = city_id
    inner = {"client_input_params": cip,
             "server_params": _base_server_params("details")}
    js, err = _post_graphql_android(session, token, device, fr,
                                     APP_ID_DETAILS_SUBMIT_ANDROID, inner,
                                     doc_id=DOC_ID_ACTION)
    if err:
        return False, f"Details: {err}", False
    if is_die(json.dumps(js)):
        return False, "TOKEN DIE (Details)", True
    a = _extract_action_android(js)
    e = _extract_error_android(a, js)
    if e:
        return False, f"Details error: {e}", False
    return True, None, False


def _step_photo_cta_submit(session, token, device, profile_plus_id,
                            thread_idx=None):
    fr = f"FbBloksActionRootQuery-{APP_ID_PHOTO_SUBMIT_ANDROID}"
    cip = {
        "profile_plus_id": profile_plus_id,
        "website": "",
        "profile_photo_id": "",
        "cover_photo_id": "",
    }
    inner = {"client_input_params": cip,
             "server_params": _base_server_params("photo_and_cta")}
    js, err = _post_graphql_android(session, token, device, fr,
                                     APP_ID_PHOTO_SUBMIT_ANDROID, inner,
                                     doc_id=DOC_ID_ACTION)
    if err:
        return False, f"PhotoCTA: {err}", False
    if is_die(json.dumps(js)):
        return False, "TOKEN DIE (PhotoCTA)", True
    a = _extract_action_android(js)
    e = _extract_error_android(a, js)
    if e:
        return False, f"PhotoCTA error: {e}", False
    return True, None, False


def _step_notifications_submit(session, token, device, profile_plus_id,
                                 thread_idx=None):
    fr = f"FbBloksActionRootQuery-{APP_ID_NOTIF_SUBMIT_ANDROID}"
    cip = {
        "email_notifications_set": 1,
        "profile_plus_id": profile_plus_id,
        "cross_profile_notifications_set": 1,
    }
    sp = _base_server_params("notifications")
    sp["is_last_step_of_page_creation"] = 1
    inner = {"client_input_params": cip, "server_params": sp}
    js, err = _post_graphql_android(session, token, device, fr,
                                     APP_ID_NOTIF_SUBMIT_ANDROID, inner,
                                     doc_id=DOC_ID_ACTION)
    if err:
        return False, f"Notifications: {err}", False
    if is_die(json.dumps(js)):
        return False, "TOKEN DIE (Notifications)", True
    a = _extract_action_android(js)
    e = _extract_error_android(a, js)
    if e:
        return False, f"Notifications error: {e}", False
    return True, None, False


def create_pro5_android(token, proxy=None, cc="VN", tz="Asia/Ho_Chi_Minh",
                         device=None, thread_idx=None):
    session = requests.Session()
    if proxy:
        fmt = format_proxy(proxy) if not proxy.startswith(
            ("http://", "https://", "socks")) else proxy
        session.proxies.update({"http": fmt, "https": fmt})
    if device is None:
        device = gen_android_device(cc, tz)
    name = gen_name()
    category_ids = ["2700"]

    if thread_idx:
        _dash_update(thread_idx, status="Mở trang landing")
    fr_landing = f"FbBloksAppRootQuery-{APP_ID_UNIFIED_LANDING}"
    inner_landing = {
        "params": {
            "params": json.dumps({
                "server_params": {
                    "design_variant": "audience_selection",
                    "source": "PAGES_TAB_LAUNCH_POINT",
                    "tracking_id": str(uuid.uuid4()),
                },
            }, separators=(",", ":")),
            "bloks_versioning_id": BLOKS_VERSION_ANDROID,
            "app_id": APP_ID_UNIFIED_LANDING,
        },
    }
    js, err = _post_graphql_android(session, token, device, fr_landing,
                                     APP_ID_UNIFIED_LANDING, inner_landing,
                                     doc_id=DOC_ID_APPROOT, purpose="fetch")
    if err:
        return False, f"Landing: {err}", False, session, device
    if is_die(json.dumps(js)):
        return False, "TOKEN DIE (Landing)", True, session, device

    if thread_idx:
        _dash_update(thread_idx, status="Tải form tạo Page")
    fr_form = f"FbBloksAppRootQuery-{APP_ID_LANDING_ANDROID}"
    inner_form = {
        "params": {
            "params": json.dumps({
                "server_params": {
                    "source": "PAGES_TAB_LAUNCH_POINT",
                    "tracking_id": str(uuid.uuid4()),
                },
            }, separators=(",", ":")),
            "bloks_versioning_id": BLOKS_VERSION_ANDROID,
            "app_id": APP_ID_LANDING_ANDROID,
        },
    }
    js, err = _post_graphql_android(session, token, device, fr_form,
                                     APP_ID_LANDING_ANDROID, inner_form,
                                     doc_id=DOC_ID_APPROOT, purpose="fetch")
    if err:
        return False, f"LoadForm: {err}", False, session, device
    if is_die(json.dumps(js)):
        return False, "TOKEN DIE (LoadForm)", True, session, device
    _sleep_interruptible(random.uniform(0.8, 1.5))

    if thread_idx:
        _dash_update(thread_idx, status="Gửi tên Page")
    ok, err, die = _step_name_submit(session, token, device, name, thread_idx)
    if not ok:
        return False, err, die, session, device
    _sleep_interruptible(random.uniform(0.5, 1.2))

    if thread_idx:
        _dash_update(thread_idx, status="Gửi category")
    ok, pp_id, err, die = _step_category_submit(
        session, token, device, name, category_ids, thread_idx)
    if not ok:
        return False, err, die, session, device
    _sleep_interruptible(random.uniform(0.8, 1.5))

    if thread_idx:
        _dash_update(thread_idx, status="Tìm địa chỉ")
    ok, city_id, err, die = _step_address_search(
        session, token, device, "s", thread_idx)
    if die:
        return False, err, True, session, device
    if not ok:
        city_id = None
    _sleep_interruptible(random.uniform(0.5, 1.0))

    if thread_idx:
        _dash_update(thread_idx, status="Gửi yêu cầu tạo Page")
    ok, err, die = _step_details_submit(
        session, token, device, pp_id, name, city_id, thread_idx)
    if not ok:
        return False, err, die, session, device
    _sleep_interruptible(random.uniform(0.5, 1.2))

    if thread_idx:
        _dash_update(thread_idx, status="Gửi ảnh & CTA")
    ok, err, die = _step_photo_cta_submit(
        session, token, device, pp_id, thread_idx)
    if not ok:
        return False, err, die, session, device
    _sleep_interruptible(random.uniform(0.5, 1.2))

    if thread_idx:
        _dash_update(thread_idx, status="Gửi thông báo cuối")
    ok, err, die = _step_notifications_submit(
        session, token, device, pp_id, thread_idx)
    if not ok:
        return False, err, die, session, device

    return True, {
        "id": pp_id,
        "name": name,
        "token": token,
        "brand": device["brand"],
        "device": device["market_name"],
        "device_id": device["device_id"],
    }, False, session, device


def _attempt_create_page(token, proxy, cc, tz, device, thread_idx):
    """Bọc create_pro5_android với xử lý ngoại lệ.
    Trả về (ok, res, die, device)."""
    try:
        ok, res, die, _session, device = create_pro5_android(
            token, proxy, cc=cc, tz=tz, device=device, thread_idx=thread_idx)
        return ok, res, die, device
    except Exception as e:
        return False, f"Exception: {str(e)[:100]}", False, device


def _wait_with_dash(tk_idx, seconds, label_prefix, current_proxy=None):
    """Chờ với progress bar. Trả về True nếu bị dừng giữa chừng."""
    start = time.time()
    while time.time() - start < seconds:
        if _stop_flag:
            return True
        elapsed = time.time() - start
        _dash_update(tk_idx, status=f"{label_prefix} {int(seconds - elapsed)}s",
                     bar=(elapsed, seconds, "delay"))
        time.sleep(0.5)
    return False


def _switch_proxy(proxy_pool, current_proxy):
    """Chọn proxy khác từ pool."""
    if not proxy_pool:
        return current_proxy
    if len(proxy_pool) == 1:
        return proxy_pool[0]
    candidates = [p for p in proxy_pool if p != current_proxy]
    if not candidates:
        candidates = proxy_pool
    return random.choice(candidates)


def run_token(tk_idx, acc, limit, country_choice="VN", cc="VN", tz="Asia/Ho_Chi_Minh",
              proxy_pool=None):
    success = 0
    fail = 0
    fail_streak = 0
    MAX_FAIL_STREAK = 5
    status = "unknown"
    reason = ""
    existing = None
    target_total = None

    token = acc.get("token", "") or ""
    current_proxy = acc.get("proxy") or (random.choice(proxy_pool) if proxy_pool else None)

    if not token:
        _dash_update(tk_idx, status="Thiếu token", done=True, flag="die")
        _update_stat(tk_idx, "", current_proxy, "die", 0, 0, "Không có token")
        return 0

    _dash_update(tk_idx, status="Tạo device Android")
    device = gen_android_device(cc, tz)

    # ==== Xác thực proxy ban đầu (thử vài proxy từ pool nếu có) ====
    if current_proxy:
        _dash_update(tk_idx, status="Kiểm tra proxy")
        pv = verify_proxy(current_proxy, timeout=12)
        if not pv["alive"] and proxy_pool and len(proxy_pool) > 1:
            tried = {current_proxy}
            for _ in range(min(4, len(proxy_pool))):
                alt = random.choice(proxy_pool)
                if alt in tried:
                    continue
                tried.add(alt)
                pv2 = verify_proxy(alt, timeout=8)
                if pv2["alive"]:
                    current_proxy = alt
                    pv = pv2
                    _push_log(tk_idx, "[dim cyan]Đã đổi proxy ban đầu vì proxy cũ die[/]")
                    break
        if not pv["alive"]:
            _dash_update(tk_idx, status="Proxy die",
                         reason=f"Proxy: {pv['reason'][:40]}", done=True, flag="die")
            _update_stat(tk_idx, token, current_proxy, "proxy_die", 0, 0,
                         f"Proxy die: {pv['reason'][:80]}")
            return 0
        if country_choice == "AUTO":
            new_cc = pv.get("countryCode") or cc
            new_tz = pv.get("timezone") or tz
            if new_cc != device.get("country_code"):
                device["country_code"] = new_cc
                device["timezone"] = new_tz
                loc = ANDROID_LOCALE_MAP.get(new_cc)
                if loc:
                    device["locale"] = loc[0]
                    device["accept_lang"] = loc[2]
                cc, tz = new_cc, new_tz

    _update_stat(tk_idx, token, current_proxy, "running", 0, 0)

    _dash_update(tk_idx, status="Lấy UID token")
    uid_token, _, err_uid = check_user(token, current_proxy)
    if uid_token:
        _dash_update(tk_idx, uid=uid_token)

    _dash_update(tk_idx, status="Kiểm tra token")
    need, existing, chk, _ = calc_needed(token, current_proxy, limit, thread_idx=tk_idx)

    if chk == "token_die":
        if not dashboard_lines.get(tk_idx, {}).get("uid"):
            uid_try, _, _ = check_user(token, None)
            if uid_try:
                _dash_update(tk_idx, uid=uid_try)
        _dash_update(tk_idx, status="Token die", reason="token die",
                     done=True, flag="die")
        _update_stat(tk_idx, token, current_proxy, "die", 0, 0, "Token die")
        return 0
    if chk == "proxy_die":
        _dash_update(tk_idx, status="Proxy die", reason="proxy die",
                     done=True, flag="die")
        _update_stat(tk_idx, token, current_proxy, "proxy_die", 0, 0, "Proxy die")
        return 0
    if chk == "unknown_soft":
        _dash_update(tk_idx, status="Không check được page",
                     reason="Không kiểm tra được số page", done=True, flag="die")
        _update_stat(tk_idx, token, current_proxy, "die", 0, 0,
                     "Không kiểm tra được page - dừng an toàn")
        _push_log(tk_idx, "[bold red]Không check được page - dừng luồng để an toàn[/]")
        return 0
    if chk == "already_enough":
        _dash_update(tk_idx, status=f"Đã có {existing} page", done=True)
        _update_stat(tk_idx, token, current_proxy, "already_enough", 0, 0,
                     f"Đã có {existing} page", existing)
        return 0
    if chk == "ok":
        _dash_update(tk_idx, status=f"Có {existing}, cần +{need}")
        target_total = existing + need
        limit = need

    _update_stat(tk_idx, token, current_proxy, "running", 0, 0, existing=existing)

    # ==================== VÒNG LẶP TẠO PAGE ====================
    while success < limit:
        if _stop_flag:
            reason = "Người dùng dừng"
            _dash_update(tk_idx, status="Dừng", done=True, flag="stop")
            break

        # ---- Lần thử 1 ----
        _dash_update(tk_idx, status=f"Đang tạo ({success}/{limit})",
                     bar=(success, limit, "reg"))
        ok, res, die, device = _attempt_create_page(
            token, current_proxy, cc, tz, device, tk_idx)

        # ---- Xử lý lỗi lần 1: chờ 30s + đổi proxy + thử lại ----
        if not ok and not die:
            res_str = str(res)

            # Nếu là block/rate_limit thì dừng luôn (không retry vô ích)
            if "Block Limit" in res_str or "Bị chặn" in res_str:
                fail += 1
                _dash_bump_fail(1)
                status = "blocked"; reason = res_str[:200]
                _dash_update(tk_idx, status="BỊ BLOCK", fail=fail,
                             reason=reason[:60], done=True, flag="block")
                _update_stat(tk_idx, token, current_proxy, "blocked",
                             success, fail, reason, existing)
                _push_log(tk_idx, "[bold magenta]DỪNG LUỒNG - Token bị block[/]")
                break
            if is_rate_limit(res_str):
                fail += 1
                _dash_bump_fail(1)
                status = "rate_limit"; reason = res_str[:200]
                _dash_update(tk_idx, status="RATE LIMIT", fail=fail,
                             reason=reason[:60], done=True, flag="rate_limit")
                _update_stat(tk_idx, token, current_proxy, "rate_limit",
                             success, fail, reason, existing)
                _push_log(tk_idx, "[bold magenta]DỪNG LUỒNG - Gần đây đã tạo quá nhiều trang[/]")
                break

            fail += 1
            _dash_bump_fail(1)
            _update_stat(tk_idx, token, current_proxy, "error",
                         success, fail, res_str[:120], existing=existing)
            _push_log(tk_idx, f"[bold red]Lỗi tạo page:[/] {res_str[:80]}")
            _push_log(tk_idx, "[bold yellow]Chờ 30s và đổi proxy để thử lại...[/]")
            _dash_update(tk_idx, last_was_fail=True)

            if _wait_with_dash(tk_idx, 30, "Chờ đổi proxy"):
                break

            # Đổi proxy mới
            old_proxy = current_proxy
            current_proxy = _switch_proxy(proxy_pool, current_proxy)
            if current_proxy != old_proxy:
                _push_log(tk_idx, "[bold cyan]Đã đổi proxy mới, thử lại page...[/]")
            else:
                _push_log(tk_idx, "[bold cyan]Thử lại với proxy hiện tại...[/]")

            # ---- Lần thử 2 (retry) ----
            _dash_update(tk_idx, status=f"Thử lại ({success}/{limit})",
                         bar=(success, limit, "reg"))
            ok, res, die, device = _attempt_create_page(
                token, current_proxy, cc, tz, device, tk_idx)

        # ---- Token die ----
        if die:
            fail += 1
            fail_streak += 1
            _dash_bump_fail(1)
            status = "die"; reason = "Token die"
            _dash_update(tk_idx, status="Token die", fail=fail,
                         reason=reason, done=True, flag="die")
            _update_stat(tk_idx, token, current_proxy, "die",
                         success, fail, reason, existing)
            _push_log(tk_idx, "[bold red]Token die - dừng luồng[/]")
            break

        # ---- Thành công ----
        if ok:
            success += 1
            fail_streak = 0
            _dash_bump_ok(1)
            _dash_update(tk_idx, status=f"+1 ({success}/{limit})",
                         success=success, bar=(success, limit, "reg"),
                         last_was_fail=False)
            _update_stat(tk_idx, token, current_proxy, "running",
                         success, fail, existing=existing)

            cur_pages_str = ""
            broke = False

            if success < limit and target_total is not None:
                _dash_update(tk_idx, status="Kiểm tra lại Page")
                try:
                    cur_pages, st2, _ = check_pages(token, current_proxy, thread_idx=tk_idx)
                    if st2 == "ok" and cur_pages is not None:
                        cur_pages_str = f" [dim]→ Có {cur_pages}/{target_total} page[/]"
                        _dash_update(tk_idx, status=f"Đã check: {cur_pages}/{target_total}")
                        if cur_pages >= target_total:
                            _push_log(tk_idx, f"[bold green]Page #{success}[/] [white]{res['name']}[/] [dim](ID {res['id']})[/]{cur_pages_str} [bold cyan]→ ĐỦ, dừng luồng[/]")
                            limit = success
                            broke = True
                    elif st2 == "token_die":
                        _push_log(tk_idx, f"[bold green]Page #{success}[/] [white]{res['name']}[/] [dim](ID {res['id']})[/] [bold red]→ Token die khi check lại[/]")
                        status = "die"
                        reason = "Token die khi check lại"
                        _dash_update(tk_idx, status="Token die", done=True, flag="die")
                        broke = True
                    elif st2 == "proxy_die":
                        _push_log(tk_idx, f"[bold green]Page #{success}[/] [white]{res['name']}[/] [dim](ID {res['id']})[/] [bold red]→ Proxy die khi check lại[/]")
                        status = "proxy_die"
                        reason = "Proxy die khi check lại"
                        _dash_update(tk_idx, status="Proxy die", done=True, flag="die")
                        broke = True
                    else:
                        cur_pages_str = f" [dim]→ check lỗi ({st2})[/]"
                except Exception as e:
                    cur_pages_str = f" [dim]→ check lỗi: {str(e)[:30]}[/]"

            if broke:
                break

            if success < limit:
                dsec = random.randint(INTERACT_MIN, INTERACT_MAX)
                _push_log(tk_idx, f"[bold green]Page #{success}[/] [white]{res['name']}[/] [dim](ID {res['id']})[/]{cur_pages_str} [bold yellow]→ Nghỉ {dsec}s[/]")
                if _wait_with_dash(tk_idx, dsec, "Nghỉ"):
                    break
            else:
                if target_total is not None:
                    done_str = f" [dim]→ Có {target_total}/{target_total} page[/] [bold cyan]→ Hoàn tất[/]"
                else:
                    done_str = " [bold cyan]→ Hoàn tất[/]"
                _push_log(tk_idx, f"[bold green]Page #{success}[/] [white]{res['name']}[/] [dim](ID {res['id']})[/]{cur_pages_str}{done_str}")
            continue

        # ---- Thất bại lần 2 (retry cũng fail) ----
        res_str = str(res)
        fail += 1
        fail_streak += 1
        _dash_bump_fail(1)
        _update_stat(tk_idx, token, current_proxy, "error",
                     success, fail, res_str[:120], existing=existing)
        _push_log(tk_idx, f"[bold red]Thử lại thất bại ({fail_streak}/{MAX_FAIL_STREAK}):[/] {res_str[:80]}")
        _dash_update(tk_idx, last_was_fail=True)

        if "Block Limit" in res_str or "Bị chặn" in res_str:
            status = "blocked"; reason = res_str[:200]
            _dash_update(tk_idx, status="BỊ BLOCK", fail=fail,
                         reason=reason[:60], done=True, flag="block")
            _update_stat(tk_idx, token, current_proxy, "blocked",
                         success, fail, reason, existing)
            _push_log(tk_idx, "[bold magenta]DỪNG LUỒNG - Token bị block[/]")
            break
        if is_rate_limit(res_str):
            status = "rate_limit"; reason = res_str[:200]
            _dash_update(tk_idx, status="RATE LIMIT", fail=fail,
                         reason=reason[:60], done=True, flag="rate_limit")
            _update_stat(tk_idx, token, current_proxy, "rate_limit",
                         success, fail, reason, existing)
            _push_log(tk_idx, "[bold magenta]DỪNG LUỒNG - Gần đây đã tạo quá nhiều trang[/]")
            break
        if fail_streak >= MAX_FAIL_STREAK:
            status = "error"
            reason = f"Thất bại {MAX_FAIL_STREAK} lần liên tiếp: {res_str[:150]}"
            _dash_update(tk_idx, status=f"DỪNG - thất bại {MAX_FAIL_STREAK} lần",
                         fail=fail, reason=reason[:60], done=True, flag="stop")
            _update_stat(tk_idx, token, current_proxy, "error",
                         success, fail, reason, existing)
            _push_log(tk_idx, f"[bold red]DỪNG LUỒNG - Thất bại {MAX_FAIL_STREAK} lần liên tiếp[/]")
            break

        # Nghỉ delay bình thường, chờ đợt sau
        _dash_update(tk_idx, status=f"Lỗi ({fail_streak}/{MAX_FAIL_STREAK})",
                     fail=fail)
        if success < limit:
            dsec = random.randint(INTERACT_MIN, INTERACT_MAX)
            _push_log(tk_idx, f"[bold yellow]Nghỉ {dsec}s trước khi thử lại đợt sau[/]")
            if _wait_with_dash(tk_idx, dsec, "Nghỉ"):
                break

    # ==== Tổng kết ====
    if status == "unknown":
        if success >= limit: status = "Hoàn tất"
        elif success > 0: status = "Một phần"
        else:
            status = "Không tạo được"
            if not reason: reason = "Không tạo được page nào"

    flag = None
    if status == "die": flag = "die"
    elif status == "blocked": flag = "block"
    elif status == "rate_limit": flag = "rate_limit"
    elif status == "error": flag = "stop"

    _dash_update(tk_idx, status=f"{status}", success=success, fail=fail,
                 reason=reason[:40] if reason else "", done=True, flag=flag)
    _update_stat(tk_idx, token, current_proxy, status, success, fail, reason, existing)
    return success


def print_final_report(total_success, elapsed):
    if not _HAS_RICH: return
    console.print()
    console.rule(f"[bold gold1]BÁO CÁO TỔNG KẾT TẠO PAGE PRO5 (ANDROID) - v{VERSION} by {AUTHOR}[/]")
    if not TOKEN_STATS:
        console.print("[bold red]Không có dữ liệu![/]"); return

    alive, die_l, block_l, np_l, px_l, err_l, already_l, rl_l = [], [], [], [], [], [], [], []
    for idx in sorted(TOKEN_STATS.keys()):
        st = TOKEN_STATS[idx]; s = st["status"]
        if s in ("Hoàn tất", "Một phần"): alive.append((idx, st))
        elif s == "already_enough": already_l.append((idx, st))
        elif s == "die": die_l.append((idx, st))
        elif s == "blocked": block_l.append((idx, st))
        elif s == "rate_limit": rl_l.append((idx, st))
        elif s == "Không tạo được": np_l.append((idx, st))
        elif s == "proxy_die": px_l.append((idx, st))
        else: err_l.append((idx, st))

    ov = Table(show_header=False, box=box.ROUNDED, border_style="cyan", padding=(0, 1))
    ov.add_column("K", style="bold white"); ov.add_column("V", justify="right")
    ov.add_row("Hoạt động", f"[bold green]{len(alive)}[/]")
    ov.add_row("DIE / BLOCK / RATE LIMIT / LỖI", f"[bold red]{len(die_l) + len(block_l) + len(rl_l) + len(err_l)}[/]")
    ov.add_row("Không tạo được page", f"[yellow]{len(np_l)}[/]")
    ov.add_row("Proxy die", f"[bold red]{len(px_l)}[/]")
    ov.add_row("Đã có page sẵn", f"[bold cyan]{len(already_l)}[/]")
    ov.add_row("TỔNG PAGE", f"[bold gold1]{total_success}[/]")
    ov.add_row("Thời gian", f"[bold magenta]{int(elapsed)}s[/]")
    ov.add_row("Tác giả", f"[bold gold1]{AUTHOR}[/]")
    ov.add_row("Phiên bản", f"[bold gold1]v{VERSION}[/]")
    console.print(Panel(ov, title="[bold gold1]TỔNG QUAN[/]",
                        border_style="gold1", box=box.ROUNDED))

    def grp(title, items, color):
        if not items: return
        t = Table(show_header=True, box=box.ROUNDED, border_style=color,
                  header_style=f"bold {color}", padding=(0, 1))
        t.add_column("STT", justify="center", width=5)
        t.add_column("Token", style="dim white")
        t.add_column("Ghi chú", style="white")
        for idx, st in items:
            tok = st['token'][:32] + "..." if len(st['token']) > 32 else st['token']
            t.add_row(f"[bold]{idx}[/]", tok, st['reason'][:80])
        console.print(Panel(t, title=f"[bold {color}]{title} ({len(items)})[/]",
                            border_style=color, box=box.ROUNDED))

    if alive:
        t = Table(show_header=True, box=box.ROUNDED, border_style="green",
                  header_style="bold green", padding=(0, 1))
        t.add_column("STT", justify="center", width=5)
        t.add_column("Token", style="dim white")
        t.add_column("Page reg được", justify="right", style="bold green")
        t.add_column("Tổng Page hiện có", justify="right", style="bold cyan")
        for idx, st in alive:
            tok = st['token'][:32] + "..." if len(st['token']) > 32 else st['token']
            existing = st.get('existing') or 0
            total_now = existing + st['success']
            t.add_row(f"[bold]{idx}[/]", tok,
                      str(st['success']), str(total_now))
        console.print(Panel(t, title=f"[bold green]HOẠT ĐỘNG ({len(alive)})[/]",
                            border_style="green", box=box.ROUNDED))

    if already_l:
        t = Table(show_header=True, box=box.ROUNDED, border_style="cyan",
                  header_style="bold cyan", padding=(0, 1))
        t.add_column("STT", justify="center", width=5)
        t.add_column("Token", style="dim white")
        t.add_column("Page reg được", justify="right", style="bold green")
        t.add_column("Tổng Page hiện có", justify="right", style="bold cyan")
        for idx, st in already_l:
            tok = st['token'][:32] + "..." if len(st['token']) > 32 else st['token']
            existing = st.get('existing') or 0
            t.add_row(f"[bold]{idx}[/]", tok, "0", str(existing))
        console.print(Panel(t, title=f"[bold cyan]ĐÃ CÓ PAGE SẴN ({len(already_l)})[/]",
                            border_style="cyan", box=box.ROUNDED))

    grp("DIE", die_l, "red")
    grp("BỊ BLOCK", block_l, "magenta")
    grp("RATE LIMIT (tạo quá nhiều trang)", rl_l, "magenta")
    grp("PROXY DIE", px_l, "red")
    grp("KHÔNG TẠO ĐƯỢC", np_l, "yellow")
    grp("LỖI KHÁC (đã dừng luồng)", err_l, "red")
    console.print()


async def run_farm(accounts, limit, country_choice, cc, tz, proxy_pool=None):
    global _stop_flag
    _stop_flag = False

    dashboard_stats["start_ts"] = time.time()
    dashboard_stats["total_tokens"] = len(accounts)
    dashboard_stats["total_ok"] = 0
    dashboard_stats["total_fail"] = 0
    dashboard_lines.clear()
    log_buffer.clear()

    ui_task = asyncio.create_task(ui_render_loop())
    await asyncio.sleep(2.0)

    try:
        loop = asyncio.get_event_loop()

        def submit_all():
            from concurrent.futures import ThreadPoolExecutor, as_completed
            results = []
            with ThreadPoolExecutor(max_workers=MAX_THREADS) as ex:
                futs = []
                for idx, acc in enumerate(accounts, start=1):
                    f = ex.submit(run_token, idx, acc, limit, country_choice, cc, tz, proxy_pool)
                    futs.append(f)
                for f in as_completed(futs):
                    try: results.append(f.result())
                    except: results.append(0)
            return results

        total_ok = await loop.run_in_executor(None, submit_all)
        total_success = sum(total_ok)
    except asyncio.CancelledError:
        _stop_flag = True
        raise
    finally:
        ui_task.cancel()
        try: await ui_task
        except: pass

    return total_success


async def input_tokens_with_uid_check():
    """Nhập token, check UID ngay, token lỗi yêu cầu nhập lại.
    Enter 2 lần liên tiếp để kết thúc."""
    console.print()
    print_info(
        "Mỗi dòng một token Facebook (access token).\n"
        "Có thể thêm proxy phía sau dạng [bold yellow]token|proxy[/] (tùy chọn).\n\n"
        "Token sẽ được [bold green]kiểm tra UID ngay khi nhập[/].\n"
        "Token lỗi sẽ yêu cầu nhập lại.\n\n"
        "Nhập xong bấm [bold green]Enter 2 lần liên tiếp[/] để kết thúc.",
        "NHẬP TOKEN")

    valid_lines = []
    empty_streak = 0
    while True:
        try:
            line = console.input("[bold grey70]| [/]").rstrip()
        except EOFError:
            break

        if not line.strip():
            empty_streak += 1
            if empty_streak >= 2:
                break
            continue

        empty_streak = 0
        acc = parse_token_line(line)
        token = acc.get("token", "") or ""
        inline_proxy = acc.get("proxy")

        if not token or not _is_token(token):
            console.print("[bold red]Token không hợp lệ (phải bắt đầu bằng EAAAA...). Nhập lại.[/]")
            continue

        console.print("[dim]→ Đang kiểm tra token...[/]")
        uid, name, err = check_user(token, inline_proxy)

        if uid:
            console.print(
                f"[bold green]✓ OK[/]  UID=[bold cyan]{uid}[/]  "
                f"Tên=[white]{name or '?'}[/]"
                + (f"  [dim]proxy: {inline_proxy}[/]" if inline_proxy else "")
            )
            valid_lines.append(line.strip())
        else:
            if err == "token_die":
                console.print("[bold red]✗ Token die / hết hạn. Nhập lại token khác.[/]")
            elif err and err.startswith("proxy_error"):
                console.print(f"[bold red]✗ Lỗi proxy: {err}. Nhập lại.[/]")
            elif err == "timeout":
                console.print("[bold yellow]⚠ Timeout khi check token. Thử lại sau.[/]")
            else:
                console.print(f"[bold red]✗ Token lỗi ({err}). Nhập lại.[/]")

    return valid_lines


async def main():
    global TOTAL_TOKENS, MAX_THREADS, NAME_TYPE, INTERACT_MIN, INTERACT_MAX

    try: os.system('cls' if os.name == 'nt' else 'clear')
    except: pass

    if not _HAS_RICH:
        print("Vui lòng cài đặt: pip install rich")
        return

    print_banner()
    print_welcome()

    # ================== NHẬP PROXY TỪ FILE TRƯỚC ==================
    print_section("PROXY TỪ FILE", color="cyan")
    print_info(
        "Nhập đường dẫn tới file proxy (mỗi dòng 1 proxy).\n"
        "Định dạng hỗ trợ:\n"
        "  [dim]http://user:pass@host:port[/]\n"
        "  [dim]host:port[/]\n"
        "  [dim]user:pass:host:port[/]\n"
        "  [dim]host:port:user:pass[/]\n\n"
        "Enter để bỏ qua (không dùng proxy).",
        "FILE PROXY")
    console.print()
    proxy_file = ask_prompt("Đường dẫn file proxy (Enter bỏ qua):", "")
    proxy_pool = []
    if proxy_file:
        if os.path.isfile(proxy_file):
            proxy_pool = load_proxies_from_file(proxy_file)
            if proxy_pool:
                console.print(f"[bold green]✓ Đã nạp {len(proxy_pool)} proxy từ file[/]")
            else:
                console.print("[bold yellow]⚠ File rỗng hoặc không có proxy hợp lệ![/]")
        else:
            console.print(f"[bold red]✗ File không tồn tại: {proxy_file}[/]")

    # ================== NHẬP TOKEN VỚI CHECK UID ==================
    print_section("NHẬP DANH SÁCH TOKEN", color="cyan")
    lines = await input_tokens_with_uid_check()

    if not lines:
        console.print("[bold red]Không có token hợp lệ![/]")
        return

    # ================== LOẠI TÊN ==================
    print_section("LOẠI TÊN", color="cyan")
    show_menu("CHỌN LOẠI TÊN", [("1", "Tên Việt Nam", ""), ("2", "Tên US", "")])
    console.print()
    nc = ask_menu("Lựa chọn", ["1", "2"], "1")
    NAME_TYPE = "us" if nc == "2" else "vn"
    console.print(f"[bold green]{'US' if NAME_TYPE == 'us' else 'Việt Nam'}[/]")

    # ================== QUỐC GIA ==================
    print_section("QUỐC GIA", color="cyan")
    cc_menu = [("1","VN","Việt Nam"),("2","US","Hoa Kỳ"),("3","GB","Anh"),
               ("4","DE","Đức"),("5","FR","Pháp"),("6","JP","Nhật"),("7","KR","Hàn Quốc"),
               ("8","CA","Canada"),("9","AU","Úc"),("10","IT","Ý"),
               ("11","ES","Tây Ban Nha"),("12","NL","Hà Lan"),("13","SE","Thụy Điển"),("14","CH","Thụy Sĩ"),
               ("15","AT","Áo"),("16","BE","Bỉ"),("17","PT","Bồ Đào Nha"),("18","IE","Ireland"),
               ("19","PL","Ba Lan"),("20","CZ","Séc"),("21","NO","Na Uy"),("22","DK","Đan Mạch"),
               ("23","FI","Phần Lan"),("24","NZ","New Zealand"),("25","SG","Singapore"),("26","HK","Hong Kong"),
               ("27","TW","Đài Loan"),("28","MY","Malaysia"),("29","TH","Thái Lan"),("30","AE","UAE"),
               ("31","IL","Israel"),("32","PH","Philippines")]
    t = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    t.add_column("L", style="yellow"); t.add_column("LN", style="bold white")
    t.add_column("R", style="yellow"); t.add_column("RN", style="bold white")
    half = (len(cc_menu) + 1) // 2
    for i in range(half):
        l = cc_menu[i]
        r = cc_menu[i + half] if i + half < len(cc_menu) else None
        t.add_row(f"[{l[0]:>2}]", f"{l[2]} ({l[1]})",
                  f"[{r[0]:>2}]" if r else "", f"{r[2]} ({r[1]})" if r else "")
    console.print(Panel(t, title="[bold cyan]CHỌN QUỐC GIA[/]",
                        border_style="cyan", box=box.ROUNDED, padding=(0, 1)))
    console.print()
    console.print("[dim]Chọn [0] để AUTO theo proxy (mặc định)[/]")
    console.print()
    cc_ch = ask_prompt("Lựa chọn (0-32, mặc định 0 - AUTO)", "0")
    cc_map = {n: c for n, c, _ in cc_menu}
    country_choice = cc_map.get(cc_ch, "AUTO") if cc_ch != "0" else "AUTO"
    console.print(f"[bold green]{country_choice}[/]")

    # ================== SỐ PAGE / TOKEN ==================
    print_section("SỐ PAGE MỖI TOKEN", color="cyan")
    try:
        lp = int(ask_prompt("Số page tối đa/token", "15") or "15")
        if lp < 1: lp = 1
    except: lp = 15
    console.print(f"[bold green]{lp} page/token[/]")

    # ================== THỜI GIAN NGHỈ ==================
    print_section("THỜI GIAN NGHỈ GIỮA CÁC PAGE", color="cyan")
    show_menu("THỜI GIAN NGHỈ", [
        ("1", "Ngắn",  "300-480s (5-8 phút)"),
        ("2", "Vừa",     "600-900s (10-15 phút)"),
        ("3", "Dài",     "900-1800s (15-30 phút)"),
        ("4", "Rất dài", "1800-3600s (30-60 phút)"),
        ("5", "Tùy chỉnh", ""),
    ])
    console.print()
    dc = ask_menu("Lựa chọn", ["1","2","3","4","5"], "1")
    if dc == "1": INTERACT_MIN, INTERACT_MAX = 300, 480
    elif dc == "2": INTERACT_MIN, INTERACT_MAX = 600, 900
    elif dc == "3": INTERACT_MIN, INTERACT_MAX = 900, 1800
    elif dc == "4": INTERACT_MIN, INTERACT_MAX = 1800, 3600
    elif dc == "5":
        try:
            INTERACT_MIN = int(ask_prompt("Từ (giây)", "300") or "300")
            INTERACT_MAX = int(ask_prompt("Đến (giây)", "300") or "1800")
            if INTERACT_MAX < INTERACT_MIN:
                INTERACT_MIN, INTERACT_MAX = INTERACT_MAX, INTERACT_MIN
        except: INTERACT_MIN, INTERACT_MAX = 300, 600
    console.print(f"[bold green]{INTERACT_MIN}-{INTERACT_MAX}s[/]")

    # ================== GÁN PROXY CHO TỪNG TOKEN ==================
    account_list = []
    for line in lines:
        acc = parse_token_line(line)
        if not acc.get("token"):
            console.print(f"[bold yellow]Bỏ qua:[/] {line[:60]}")
            continue
        account_list.append(acc)

    if not account_list:
        console.print("[bold red]Không có token hợp lệ![/]")
        return

    if proxy_pool:
        # Gán round-robin proxy cho các token chưa có proxy trong dòng
        assigned = 0
        for i, acc in enumerate(account_list):
            if not acc.get("proxy"):
                acc["proxy"] = proxy_pool[i % len(proxy_pool)]
                assigned += 1
        console.print(f"[bold cyan]Đã gán proxy từ file cho {assigned} token[/]")

    TOTAL_TOKENS = len(account_list)
    MAX_THREADS = TOTAL_TOKENS

    # ================== XÁC NHẬN ==================
    console.print()
    s = Table(show_header=False, box=box.ROUNDED, border_style="gold1",
              padding=(0, 2), title=f"[bold gold1]XÁC NHẬN - v{VERSION} by {AUTHOR}[/]")
    s.add_column("K", style="bold cyan"); s.add_column("V", style="bold white")
    s.add_row("Số token", str(TOTAL_TOKENS))
    s.add_row("Số luồng", str(MAX_THREADS))
    s.add_row("Loại tên", "US" if NAME_TYPE == "us" else "Việt Nam")
    s.add_row("Quốc gia", country_choice)
    s.add_row("Proxy pool", f"{len(proxy_pool)} proxy" if proxy_pool else "Không dùng")
    s.add_row("Page/token", str(lp))
    s.add_row("Nghỉ", f"{INTERACT_MIN}-{INTERACT_MAX}s")
    s.add_row("Nền tảng", "Android")
    console.print(s)
    console.print()

    ok = ask_menu("Bắt đầu? (y/n)", ["y", "n", "Y", "N"], "y").lower()
    if ok != "y":
        console.print("[bold yellow]Đã hủy.[/]")
        return

    start = time.time()
    total = await run_farm(account_list, lp, country_choice,
                           "VN" if country_choice == "AUTO" else country_choice,
                           "Asia/Ho_Chi_Minh",
                           proxy_pool=proxy_pool)
    elapsed = time.time() - start

    await asyncio.sleep(0.5)

    try:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
    except Exception:
        pass
    try:
        console.clear()
    except Exception:
        pass

    await asyncio.sleep(0.3)

    print_final_report(total, elapsed)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _stop_flag = True
        try:
            if _HAS_RICH: console.print("\n[bold yellow][!] Đã dừng.[/]")
        except: pass
