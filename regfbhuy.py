import base64
import datetime
import email.utils
import io
import json
import os
import random
import re
import struct
import sys
import threading
import time
import unicodedata
import uuid
from dataclasses import dataclass
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from curl_cffi import requests as curl_requests
    from curl_cffi.requests import Session as CurlSession
    try:
        from curl_cffi import CurlMime
        HAS_CURL_MIME = True
    except Exception:
        try:
            from curl_cffi.requests import CurlMime
            HAS_CURL_MIME = True
        except Exception:
            HAS_CURL_MIME = False
    HAS_CURL_CFFI = True
except Exception:
    HAS_CURL_CFFI = False
    HAS_CURL_MIME = False


def _probe_impersonates():
    names = []
    if HAS_CURL_CFFI:
        try:
            from curl_cffi.requests import BrowserType
            try:
                names = [b.name for b in BrowserType]
            except Exception:
                names = [str(b) for b in BrowserType]
        except Exception:
            names = []
    names = list(dict.fromkeys([n for n in names if isinstance(n, str)]))
    if not names:
        names = ["chrome120"]
    return names


AVAILABLE_IMPERSONATES = _probe_impersonates()


def _classify_impersonate(name):
    s = (name or "").lower()
    if s.startswith("chrome") and "android" in s:
        return "chrome_android"
    if s.startswith("chrome"):
        return "chrome"
    if s.startswith("edge"):
        return "edge"
    if s.startswith("safari") and "ios" in s:
        return "safari_ios"
    if s.startswith("safari"):
        return "safari"
    if s.startswith("firefox"):
        return "firefox"
    if s.startswith("tor"):
        return "tor"
    return "chrome"


def _extract_version(name):
    m = re.search(r"(\d{2,3})", name or "")
    if m:
        return int(m.group(1))
    return 120


def _build_weighted_pool():
    pool = []
    for name in AVAILABLE_IMPERSONATES:
        kind = _classify_impersonate(name)
        ver = _extract_version(name)

        if kind == "chrome":
            if ver >= 145:
                weight = 8
            elif ver >= 136:
                weight = 6
            elif ver >= 131:
                weight = 4
            elif ver >= 124:
                weight = 2
            else:
                weight = 1
        elif kind == "chrome_android":
            weight = 3
        elif kind == "edge":
            weight = 3 if ver >= 101 else 1
        elif kind == "safari":
            weight = 6 if ver >= 180 else (4 if ver >= 170 else 2)
        elif kind == "safari_ios":
            weight = 4 if ver >= 180 else 2
        elif kind == "firefox":
            weight = 5 if ver >= 144 else 3
        elif kind == "tor":
            weight = 1
        else:
            weight = 1

        pool.extend([name] * weight)

    if not pool:
        pool = list(AVAILABLE_IMPERSONATES)
    return pool


IMPERSONATE_POOL = _build_weighted_pool()


def term_width(default: int = 78) -> int:
    try:
        return min(max(os.get_terminal_size().columns, 60), 100)
    except Exception:
        return default


def _char_width(ch: str) -> int:
    if not ch:
        return 0
    cp = ord(ch)
    if cp == 0x200D or cp == 0xFE0F or unicodedata.combining(ch):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    if (0x1F300 <= cp <= 0x1FAFF) or (0x2600 <= cp <= 0x27BF) or (0x1F000 <= cp <= 0x1F2FF):
        return 2
    return 1


def display_width(s: str) -> int:
    return sum(_char_width(ch) for ch in s)


DEBUG = False


def debug_log(tag: str, data: Any, limit: int = 3000):
    if not DEBUG:
        return
    try:
        if isinstance(data, (dict, list)):
            text = json.dumps(data, ensure_ascii=False)
        else:
            text = str(data)
    except Exception:
        text = repr(data)
    if len(text) > limit:
        text = text[:limit] + f"... [+{len(text) - limit}]"
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    try:
        print(f"\033[38;5;240m{ts} | DBG | {text}\033[0m")
    except Exception:
        pass


try:
    from Cryptodome.Cipher import AES, PKCS1_v1_5
    from Cryptodome.PublicKey import RSA
    from Cryptodome.Random import get_random_bytes
    HAS_CRYPTODOME = True
except Exception:
    HAS_CRYPTODOME = False

try:
    import nacl.utils
    from nacl.public import PublicKey, SealedBox
    HAS_NACL = True
except Exception:
    HAS_NACL = False

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    HAS_CRYPTOGRAPHY = True
except Exception:
    HAS_CRYPTOGRAPHY = False


class C:
    RESET = "\033[0m"; BOLD = "\033[1m"; DIM = "\033[2m"
    BLACK = "\033[30m"; RED = "\033[31m"; GREEN = "\033[32m"; YELLOW = "\033[33m"
    BLUE = "\033[34m"; MAGENTA = "\033[35m"; CYAN = "\033[36m"; WHITE = "\033[37m"
    BRED = "\033[91m"; BGREEN = "\033[92m"; BYELLOW = "\033[93m"; BBLUE = "\033[94m"
    BMAGENTA = "\033[95m"; BCYAN = "\033[96m"; BWHITE = "\033[97m"
    BG_RED = "\033[41m"; BG_GREEN = "\033[42m"; BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"; BG_MAG = "\033[45m"; BG_CYAN = "\033[46m"
    PINK = "\033[38;5;213m"; TEAL = "\033[38;5;80m"; LIME = "\033[38;5;154m"
    LAV = "\033[38;5;141m"; GRAY = "\033[38;5;245m"; DGRAY = "\033[38;5;240m"
    GOLD = "\033[38;5;220m"


def color(text, code):
    return f"{code}{text}{C.RESET}"


class AppLogger:
    TAGS = {
        "INFO":  (C.BG_BLUE + C.BWHITE + C.BOLD, " INFO "),
        "STEP":  (C.BG_CYAN + C.BLACK + C.BOLD, " STEP "),
        "OK":    (C.BG_GREEN + C.BLACK + C.BOLD, " OK "),
        "WARN":  (C.BG_YELLOW + C.BLACK + C.BOLD, " WARN "),
        "ERR":   (C.BG_RED + C.BWHITE + C.BOLD, " ERR "),
        "CHKPT": (C.BG_MAG + C.BWHITE + C.BOLD, " CHKPT "),
        "TOKN":  (C.BG_CYAN + C.BLACK + C.BOLD, " TOKN "),
        "MEDIA": (C.BG_MAG + C.BWHITE + C.BOLD, " MEDIA "),
        "PROXY": (C.BG_BLUE + C.BWHITE + C.BOLD, " PROXY "),
        "MAIL":  (C.BG_MAG + C.BWHITE + C.BOLD, " MAIL "),
        "WAIT":  (C.BG_YELLOW + C.BLACK + C.BOLD, " WAIT "),
        "LIVE":  (C.BG_GREEN + C.BLACK + C.BOLD, " LIVE "),
        "POLL":  (C.BG_CYAN + C.BLACK + C.BOLD, " POLL "),
        "CHECK": (C.BG_CYAN + C.BLACK + C.BOLD, " CHECK "),
        "FP":    (C.BG_MAG + C.BWHITE + C.BOLD, " FP "),
        "DIALOG":(C.BG_MAG + C.BWHITE + C.BOLD, " DIALOG "),
        "OTPAPI":(C.BG_MAG + C.BWHITE + C.BOLD, " OTPAPI "),
    }

    @staticmethod
    def _now():
        return datetime.datetime.now().strftime("%H:%M:%S")

    @classmethod
    def _p(cls, text):
        try:
            print(text)
        except Exception:
            try:
                print(text.encode("ascii", "replace").decode("ascii"))
            except Exception:
                pass

    @classmethod
    def _emit(cls, key, msg, msg_color=""):
        ts = color(cls._now(), C.DGRAY)
        sep = color("|", C.DGRAY)
        style, label = cls.TAGS[key]
        tag = color(label, style)
        body = color(msg, msg_color) if msg_color else msg
        cls._p(f" {ts} {sep} {tag} {sep} {body}")

    @classmethod
    def info(cls, msg): cls._emit("INFO", msg, C.BWHITE)

    @classmethod
    def step(cls, n, name, detail=""):
        tag = color(f" STEP {str(n):<3}", cls.TAGS["STEP"][0])
        ts = color(cls._now(), C.DGRAY)
        sep = color("|", C.DGRAY)
        dt = f"  {color('->', C.DGRAY)} {color(detail, C.BYELLOW)}" if detail else ""
        cls._p(f" {ts} {sep} {tag} {sep} {color(name, C.BOLD + C.BWHITE)}{dt}")

    @classmethod
    def success(cls, msg): cls._emit("OK", msg, C.LIME)
    @classmethod
    def warn(cls, msg): cls._emit("WARN", msg, C.GOLD)
    @classmethod
    def error(cls, msg): cls._emit("ERR", msg, C.BRED)
    @classmethod
    def checkpoint(cls, msg): cls._emit("CHKPT", msg, C.PINK)
    @classmethod
    def live(cls, msg): cls._emit("LIVE", msg, C.LIME)
    @classmethod
    def poll(cls, msg): cls._emit("POLL", msg, C.BCYAN)
    @classmethod
    def check(cls, msg): cls._emit("CHECK", msg, C.BCYAN)
    @classmethod
    def media(cls, msg): cls._emit("MEDIA", msg, C.LAV)
    @classmethod
    def fp(cls, msg): cls._emit("FP", msg, C.LAV)
    @classmethod
    def dialog(cls, msg): cls._emit("DIALOG", msg, C.LAV)
    @classmethod
    def otpapi(cls, msg): cls._emit("OTPAPI", msg, C.LAV)

    @classmethod
    def token(cls, name, value, extra=""):
        ts = color(cls._now(), C.DGRAY)
        sep = color("|", C.DGRAY)
        tag = color(cls.TAGS["TOKN"][1], cls.TAGS["TOKN"][0])
        v = color((value or "-")[:24], C.BWHITE)
        ex = f" {color('*', C.DGRAY)} {color(extra, C.DGRAY)}" if extra else ""
        cls._p(f" {ts} {sep} {tag} {sep} {color(name.ljust(10), C.BCYAN)} {color('=', C.DGRAY)} {v}{ex}")

    @classmethod
    def proxy(cls, msg): cls._emit("PROXY", msg, C.TEAL)
    @classmethod
    def mail(cls, msg): cls._emit("MAIL", msg, C.PINK)
    @classmethod
    def wait(cls, msg): cls._emit("WAIT", msg, C.GOLD)

    @classmethod
    def section(cls, title, icon="*"):
        w = term_width()
        line = "-" * (w - 2)
        print()
        print(color(line, C.DGRAY))
        print(f"  {color(icon, C.BCYAN)} {color(title, C.BOLD + C.BWHITE)}")
        print(color(line, C.DGRAY))

    @classmethod
    def kv(cls, key, value, vcolor=C.BWHITE):
        print(f"  {color('*', C.DGRAY)} {color(key.ljust(16), C.GRAY)} {color(str(value), vcolor)}")

    @classmethod
    def account_header(cls, idx, total, proxy, mail):
        w = term_width()
        line = "=" * (w - 2)
        text = f"ATTEMPT {idx} | Live {total}"
        tw = display_width(text)
        pad = max(0, (w - 2 - tw) // 2)
        right = max(0, (w - 2 - tw) - pad)
        print()
        print(color(f"+{line}+", C.BMAGENTA))
        print(color("|", C.BMAGENTA) + " " * pad +
              color(text, C.BOLD + C.BWHITE) + " " * right +
              color("|", C.BMAGENTA))
        print(color(f"+{line}+", C.BMAGENTA))
        cls.kv("Proxy", proxy or "none", C.TEAL if proxy else C.DGRAY)
        cls.kv("Mail", mail or "-", C.PINK)
        print()

    @classmethod
    def result_box(cls, result):
        st = (result.status or "").upper()
        if st in ("SUCCESS", "LIVE"):
            bg, tag, line_color = C.BG_GREEN + C.BLACK, "  SUCCESS  ", C.LIME
        elif st in ("SUCCESS_STEP_1", "PENDING_OTP"):
            bg, tag, line_color = C.BG_YELLOW + C.BLACK, "  PENDING  ", C.GOLD
        elif "CHECKPOINT" in st:
            bg, tag, line_color = C.BG_YELLOW + C.BLACK, " CHECKPOINT ", C.GOLD
        else:
            bg, tag, line_color = C.BG_RED + C.BWHITE, "  FAILED   ", C.BRED
        line = result.to_success_line() if st in ("SUCCESS", "LIVE", "SUCCESS_STEP_1", "PENDING_OTP") \
               else result.to_checkpoint_line()
        w = term_width()
        sep = "-" * (w - 4)
        print()
        print(f"  {color(tag, C.BOLD + bg)}")
        print(f"  {color(sep, C.DGRAY)}")
        for chunk in _wrap(line, w - 6):
            print(f"  {color(chunk, line_color)}")
        print(f"  {color(sep, C.DGRAY)}")
        print()

    @classmethod
    def menu_item(cls, idx, label, note="", default=False):
        marker = color("*", C.BCYAN) if default else color("o", C.DGRAY)
        idx_s = color(f"[{idx}]", C.BOLD + C.TEAL)
        label_s = color(label, C.BWHITE)
        note_s = f"  {color(note, C.DGRAY)}" if note else ""
        dft = color("  (default)", C.GOLD) if default else ""
        print(f"   {marker} {idx_s} {label_s}{note_s}{dft}")


def _wrap(text, width):
    if display_width(text) <= width:
        return [text]
    lines = []
    cur = ""
    cur_w = 0
    for ch in text:
        cw = _char_width(ch)
        if cur_w + cw > width:
            lines.append(cur)
            cur = ch
            cur_w = cw
        else:
            cur += ch
            cur_w += cw
    if cur:
        lines.append(cur)
    return lines


FB_WWW_URL = "https://www.facebook.com"
CHECKPOINT_282_ID = "1501092823525282"

DOC_CHECK_VALID = "26387190147557007"
FRIENDLY_CHECK_VALID = "useCAARegistrationFieldValidationQuery"
DOC_REGISTER = "27029416779977343"
FRIENDLY_REGISTER = "useCAARegistrationFormSubmitMutation"
DOC_OPTIONS_DIALOG = "10033443530048902"
FRIENDLY_OPTIONS_DIALOG = "CAAConfirmationOptionsDialogQuery"
DOC_UPDATE_CP_DIALOG = "26687407570897492"
FRIENDLY_UPDATE_CP_DIALOG = "CAAFBConfirmationUpdateCPDialogQuery"
DOC_ADD_CONTACT = "25556223974027527"
FRIENDLY_ADD_CONTACT = "useCAAFBConfirmationAddContactPointMutation"
DOC_RESEND = "9554972464608847"
FRIENDLY_RESEND = "useCAAConfirmationResendConfCodeMutation"
DOC_VERIFY = "24050931851170558"
FRIENDLY_VERIFY = "useCAAFBConfirmationFormSubmitMutation"
DOC_SET_AVATAR = "27326177573748994"
FRIENDLY_AVATAR = "ProfileCometProfilePictureSetMutation"
DOC_SET_COVER = "26648951184714383"
FRIENDLY_COVER = "ProfileCometCoverPhotoUpdateMutation"

ZY_BASE_URL = "https://zy.io.vn"
ZY_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
ZY_DEFAULT_USER = ""
ZY_DEFAULT_PASS = ""
ZY_PRODUCT_ID = "916"

HOMEPROXY_ENDPOINT = "https://app.homeproxy.vn/api/v3/users/rotatev2"

USER_AGENT_DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"

SEC_CH_UA_FULL = '"Chromium";v="154", "Google Chrome";v="154", "Not A(Brand";v="99"'
SEC_CH_UA_FULL_VERSION_LIST = '"Chromium";v="154.0.8037.57", "Google Chrome";v="154.0.8037.57", "Not A(Brand";v="99.0.0.0"'

ZYMAIL_BASE = "http://103.28.35.20:3443"
ZYMAIL_DEFAULT_KEY = "RTFKNy0zRjZJLThHMkgtNUowRS1PM1I2"

MAIL1S_BASE = "https://mail1s.net/api/v1"
MAIL1S_DEFAULT_TOKEN = "m1s_IYX6nVHjT5NPyynHnC9LuG-wBUYcBvSJkN3ozOGrSYWj0USS"
MAIL1S_DOMAINS = ["1gmail.net", "1smail.net", "smax.com", "mail1s.net",
                  "mail2s.com", "mailao.net", "maxvm.net"]

DROPMAIL_BASE = "https://dropmail.me/api/graphql"

OTPTRUST_BASE = "https://otptrust.com"


AVATAR_GIRL_IMAGES = [
    "https://anhtomau.com/wp-content/uploads/2026/01/Anh-gai-xinh-VN-phong-cach-noi-bat.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Anh-gai-xinh-VN-phong-cach-sexy.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Anh-gai-xinh-VN-than-thai-tu-tin.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Gai-xinh-mac-vay-ngan-Viet-Nam-cuon-mat.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Gai-xinh-mac-vay-ngan-Viet-Nam-goi-cam.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Gai-xinh-nhat-Viet-Nam-phong-cach-hien-dai.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Gai-xinh-nhat-Viet-Nam-vibe-cuon-cam.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Gai-xinh-nhay-TikTok-Viet-Nam-cuon-hut.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Gai-xinh-nhay-TikTok-Viet-Nam-day-nang-luong.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Gai-xinh-nhay-TikTok-Viet-Nam-sexy-tinh-te.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Gai-xinh-Viet-Nam-bikini-dang-dep.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Gai-xinh-Viet-Nam-bikini-di-bien-cuon-hut.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Gai-xinh-Viet-Nam-bikini-phong-cach-bien.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Gai-xinh-Viet-Nam-cosplay-ca-tinh.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Gai-xinh-Viet-Nam-cosplay-phong-cach-rieng.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Gai-xinh-Viet-Nam-cosplay-quyen-ru.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Gai-xinh-Viet-Nam-cute-phong-cach-tre-trung.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Gai-xinh-Viet-Nam-cute-phong-thai-nhe-nhang.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Gai-xinh-Viet-Nam-de-thuong-cuon-hut.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Gai-xinh-Viet-Nam-de-thuong-tu-nhien.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Gai-xinh-Viet-Nam-phong-cach-thoi-trang.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Gai-xinh-Viet-Nam-phong-thai-cuon-nhin.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Hinh-anh-gai-xinh-cute-Viet-Nam-de-thuong.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Hinh-anh-gai-xinh-cute-Viet-Nam-hien-dai.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Hinh-anh-gai-xinh-Viet-Nam-phong-cach-goi-cam.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Hinh-anh-gai-xinh-Viet-Nam-phong-cach-sexy.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Hinh-anh-gai-xinh-Viet-Nam-tre-trung.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Hinh-anh-gai-xinh-Viet-Nam-vibe-hien-dai.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Hinh-nen-gai-xinh-Viet-Nam-chat-luong-cao.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Hinh-nen-gai-xinh-Viet-Nam-cuon-mat.webp",
    "https://anhtomau.com/wp-content/uploads/2026/01/Hinh-nen-gai-xinh-Viet-Nam-phong-cach-sexy.webp",
]

COVER_IMAGES = [f"https://picsum.photos/1200/628?random={i}" for i in range(1, 11)]


class AntiDetectSession:
    SCREEN_POOL = [
        (1920, 1080), (1536, 864), (1440, 900), (1366, 768),
        (1600, 900), (2560, 1440), (1280, 720), (1920, 1200),
        (2560, 1600), (3440, 1440), (2880, 1800), (1680, 1050),
        (3840, 2160), (2736, 1824), (2256, 1504), (2160, 1440),
    ]

    TZ_LOCALE_MAP = {
        "vi-VN": ["Asia/Ho_Chi_Minh"],
        "th-TH": ["Asia/Bangkok"],
        "id-ID": ["Asia/Jakarta"],
        "en-SG": ["Asia/Singapore"],
        "en-MY": ["Asia/Kuala_Lumpur"],
        "ja-JP": ["Asia/Tokyo"],
        "ko-KR": ["Asia/Seoul"],
        "zh-TW": ["Asia/Taipei"],
        "en-HK": ["Asia/Hong_Kong"],
        "en-PH": ["Asia/Manila"],
        "en-US": [
            "America/New_York", "America/Los_Angeles", "America/Chicago",
            "America/Denver", "America/Phoenix", "America/Detroit",
        ],
        "en-GB": ["Europe/London"],
        "en-IE": ["Europe/Dublin"],
        "en-AU": ["Australia/Sydney", "Australia/Melbourne"],
        "en-NZ": ["Pacific/Auckland"],
        "en-CA": [
            "America/Toronto", "America/Vancouver", "America/Edmonton",
        ],
        "fr-FR": ["Europe/Paris"],
        "de-DE": ["Europe/Berlin"],
        "es-ES": ["Europe/Madrid"],
        "it-IT": ["Europe/Rome"],
        "pt-BR": ["America/Sao_Paulo"],
        "es-MX": ["America/Mexico_City"],
        "pl-PL": ["Europe/Warsaw"],
        "nl-NL": ["Europe/Amsterdam"],
    }

    LOCALE_WEIGHTS = [
        ("en-US", 40),
        ("en-GB", 12),
        ("en-AU", 6),
        ("en-CA", 6),
        ("en-SG", 3),
        ("en-MY", 3),
        ("en-PH", 3),
        ("en-NZ", 2),
        ("en-IE", 2),
        ("vi-VN", 8),
        ("th-TH", 3),
        ("id-ID", 3),
        ("ja-JP", 3),
        ("ko-KR", 3),
        ("zh-TW", 2),
        ("fr-FR", 4),
        ("de-DE", 4),
        ("es-ES", 3),
        ("it-IT", 2),
        ("pt-BR", 3),
        ("es-MX", 3),
        ("pl-PL", 2),
        ("nl-NL", 2),
    ]

    CHROME_BUILD_MAP = {
        99: "99.0.4844.51",
        100: "100.0.4896.60",
        101: "101.0.4951.41",
        104: "104.0.5112.79",
        107: "107.0.5304.62",
        110: "110.0.5481.77",
        116: "116.0.5845.96",
        119: "119.0.6045.105",
        120: "120.0.6099.109",
        123: "123.0.6312.58",
        124: "124.0.6367.60",
        126: "126.0.6478.61",
        127: "127.0.6533.89",
        128: "128.0.6613.120",
        129: "129.0.6668.71",
        130: "130.0.6723.117",
        131: "131.0.6778.86",
        132: "132.0.6834.84",
        133: "133.0.6943.98",
        134: "134.0.6998.44",
        135: "135.0.7049.52",
        136: "136.0.7103.48",
        142: "142.0.7444.175",
        145: "145.0.7536.98",
        146: "146.0.7600.85",
        150: "150.0.7865.42",
        152: "152.0.7957.42",
        154: "154.0.8037.57",
    }

    EDGE_BUILD_MAP = {
        99: "99.0.1150.55",
        101: "101.0.1210.53",
    }

    FIREFOX_BUILD_MAP = {
        133: "133.0",
        135: "135.0",
        144: "144.0",
        147: "147.0",
    }

    SAFARI_BUILD_MAP = {
        153: "15.3",
        155: "15.5",
        170: "17.0",
        172: "17.2.1",
        180: "18.0",
        184: "18.4",
        260: "26.0",
    }

    WEBGL_RENDERERS = [
        "ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 2060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 4070 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 3070 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce RTX 4060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce GTX 1050 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 SUPER Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (Intel, Intel(R) HD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (AMD, AMD Radeon RX 6600 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (AMD, AMD Radeon RX 5700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "ANGLE (AMD, AMD Radeon RX 6700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)",
    ]

    WEBGL_VENDORS = [
        "Google Inc. (NVIDIA)",
        "Google Inc. (Intel)",
        "Google Inc. (AMD)",
        "Google Inc. (Microsoft)",
    ]

    def __init__(self, proxy=None, impersonate=None, timeout=45):
        if not HAS_CURL_CFFI:
            raise RuntimeError("curl_cffi not installed")

        self.proxy = proxy
        self.timeout = timeout

        if impersonate and impersonate in AVAILABLE_IMPERSONATES:
            self.impersonate = impersonate
        else:
            self.impersonate = random.choice(IMPERSONATE_POOL)

        self.kind = _classify_impersonate(self.impersonate)
        self.fp = self._gen_fingerprint()

        self.session = CurlSession(
            impersonate=self.impersonate,
            timeout=timeout,
            verify=False,
        )

        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

        self._apply_fingerprint_headers()

    def _pick_locale(self):
        weighted = []
        for loc, w in self.LOCALE_WEIGHTS:
            weighted.extend([loc] * w)
        return random.choice(weighted) if weighted else "en-US"

    def _locale_to_accept_lang(self, locale):
        parts = locale.split("-")
        if len(parts) == 2:
            return f"{locale},{parts[0]};q=0.9"
        return f"{locale},en;q=0.8"

    def _extract_version(self):
        return _extract_version(self.impersonate)

    def _gen_fingerprint(self):
        version = self._extract_version()
        kind = self.kind

        locale = self._pick_locale()
        tz_candidates = self.TZ_LOCALE_MAP.get(locale, ["America/New_York"])
        tz = random.choice(tz_candidates)

        if kind == "chrome":
            build = self.CHROME_BUILD_MAP.get(version, f"{version}.0.0.0")
            platform = "Windows"
            ua = (
                f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{build} Safari/537.36"
            )
            vendor = "Google Inc."
        elif kind == "chrome_android":
            build = self.CHROME_BUILD_MAP.get(version, f"{version}.0.0.0")
            platform = "Android"
            ua = (
                f"Mozilla/5.0 (Linux; Android 14; Pixel 8) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{build} Mobile Safari/537.36"
            )
            vendor = "Google Inc."
        elif kind == "edge":
            build = self.EDGE_BUILD_MAP.get(version, f"{version}.0.0.0")
            platform = "Windows"
            chrome_equiv = {"99": "99.0.4844.51", "101": "101.0.4951.41"}.get(str(version), f"{version}.0.0.0")
            ua = (
                f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{chrome_equiv} Safari/537.36 "
                f"Edg/{build}"
            )
            vendor = "Google Inc."
        elif kind == "safari":
            build = self.SAFARI_BUILD_MAP.get(version, f"{version // 10}.{version % 10}")
            platform = "macOS"
            ua = (
                f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                f"AppleWebKit/605.1.15 (KHTML, like Gecko) "
                f"Version/{build} Safari/605.1.15"
            )
            vendor = "Apple Computer, Inc."
        elif kind == "safari_ios":
            build = self.SAFARI_BUILD_MAP.get(version, "18.0")
            platform = "iPhone"
            ua = (
                f"Mozilla/5.0 (iPhone; CPU iPhone OS {build.replace('.', '_')} like Mac OS X) "
                f"AppleWebKit/605.1.15 (KHTML, like Gecko) "
                f"Version/{build} Mobile/15E148 Safari/604.1"
            )
            vendor = "Apple Computer, Inc."
        elif kind == "firefox":
            build = self.FIREFOX_BUILD_MAP.get(version, f"{version}.0")
            platform = "Windows"
            ua = (
                f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{version}.0) "
                f"Gecko/20100101 Firefox/{build}"
            )
            vendor = ""
        elif kind == "tor":
            platform = "Windows"
            ua = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
                "Gecko/20100101 Firefox/128.0"
            )
            vendor = ""
        else:
            build = self.CHROME_BUILD_MAP.get(version, f"{version}.0.0.0")
            platform = "Windows"
            ua = (
                f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{build} Safari/537.36"
            )
            vendor = "Google Inc."

        if kind == "chrome_android":
            sw, sh = random.choice([(393, 851), (412, 915), (360, 800), (384, 854)])
        else:
            sw, sh = random.choice(self.SCREEN_POOL)

        vp_w = sw - random.randint(0, 150)
        vp_h = sh - random.randint(80, 260)

        accept_lang = self._locale_to_accept_lang(locale)

        return {
            "kind": kind,
            "version": version,
            "build": build,
            "ua": ua,
            "vendor": vendor,
            "platform": platform,
            "locale": locale,
            "accept_language": accept_lang,
            "timezone": tz,
            "screen_w": sw,
            "screen_h": sh,
            "screen_depth": 24,
            "viewport_w": vp_w,
            "viewport_h": vp_h,
            "hardware_concurrency": random.choice([4, 6, 8, 12, 16]),
            "device_memory": random.choice([4, 8, 16, 32]),
            "color_depth": 24,
            "pixel_ratio": random.choice([1, 1.25, 1.5, 2]),
            "webgl_vendor": random.choice(self.WEBGL_VENDORS),
            "webgl_renderer": random.choice(self.WEBGL_RENDERERS),
            "canvas_noise": random.random(),
            "audio_noise": random.random() * 1e-5,
            "session_id": str(uuid.uuid4()),
            "impersonate": self.impersonate,
            "platform_windows": "Windows",
            "platform_version": "19.0.0",
            "arch": "x86",
            "bitness": "64",
            "model": "",
        }

    def _is_chromium_family(self):
        return self.kind in ("chrome", "edge", "chrome_android")

    def _apply_fingerprint_headers(self):
        self.session.headers.clear()
        self.session.headers["user-agent"] = self.fp["ua"]
        if self.fp.get("accept_language"):
            self.session.headers["accept-language"] = self.fp["accept_language"]

    def _sec_ch_ua(self):
        if not self._is_chromium_family():
            return None
        v = self.fp["version"]
        if v >= 131:
            return f'"Chromium";v="{v}", "Google Chrome";v="{v}", "Not A(Brand";v="99"'
        return f'"Google Chrome";v="{v}", "Chromium";v="{v}", "Not_A Brand";v="24"'

    def _sec_ch_ua_full(self):
        if not self._is_chromium_family():
            return None
        build = self.fp["build"]
        v = self.fp["version"]
        if v >= 131:
            return f'"Chromium";v="{build}", "Google Chrome";v="{build}", "Not A(Brand";v="99.0.0.0"'
        return f'"Google Chrome";v="{build}", "Chromium";v="{build}", "Not_A Brand";v="24.0.0.0"'

    def _accept_document(self):
        if self.kind == "firefox":
            return (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8"
            )
        if self.kind in ("safari", "safari_ios"):
            return (
                "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            )
        return (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8,"
            "application/signed-exchange;v=b3;q=0.7"
        )

    def _accept_encoding(self):
        if self.kind in ("safari", "safari_ios"):
            return "gzip, deflate, br"
        return "gzip, deflate, br, zstd"

    def _build_headers(self, extra=None, referer=None, document=False,
                       origin="https://www.facebook.com"):
        fp = self.fp
        h = {}
        is_chromium = self._is_chromium_family()

        if document:
            if is_chromium:
                sua = self._sec_ch_ua()
                if sua:
                    h["sec-ch-ua"] = sua
                h["sec-ch-ua-mobile"] = "?1" if self.kind == "chrome_android" else "?0"
                h["sec-ch-ua-platform"] = f'"{fp["platform"]}"'
            h["upgrade-insecure-requests"] = "1"
            h["user-agent"] = fp["ua"]
            h["accept"] = self._accept_document()
            if referer:
                h["referer"] = referer
                h["sec-fetch-site"] = "same-origin"
            else:
                h["sec-fetch-site"] = "none"
            h["sec-fetch-mode"] = "navigate"
            if self.kind != "firefox":
                h["sec-fetch-user"] = "?1"
            h["sec-fetch-dest"] = "document"
            h["accept-encoding"] = self._accept_encoding()
            h["accept-language"] = fp["accept_language"]
            if is_chromium:
                h["priority"] = "u=0, i"
        else:
            h["accept"] = "*/*"
            h["accept-language"] = fp["accept_language"]
            h["content-type"] = "application/x-www-form-urlencoded"
            h["origin"] = origin
            h["referer"] = referer or "https://www.facebook.com/"
            h["user-agent"] = fp["ua"]
            if is_chromium:
                h["priority"] = "u=1, i"
                sua = self._sec_ch_ua()
                suaf = self._sec_ch_ua_full()
                if sua:
                    h["sec-ch-ua"] = sua
                h["sec-ch-ua-mobile"] = "?1" if self.kind == "chrome_android" else "?0"
                h["sec-ch-ua-platform"] = f'"{fp["platform"]}"'
                if suaf:
                    h["sec-ch-ua-full-version-list"] = suaf
                    h["sec-ch-ua-full-version"] = f'"{fp["build"]}"'
                if self.kind != "chrome_android":
                    h["sec-ch-ua-platform-version"] = f'"{fp["platform_version"]}"'
                    h["sec-ch-ua-arch"] = f'"{fp["arch"]}"'
                    h["sec-ch-ua-bitness"] = f'"{fp["bitness"]}"'
                h["sec-ch-ua-model"] = '""'
            h["sec-fetch-dest"] = "empty"
            h["sec-fetch-mode"] = "cors"
            h["sec-fetch-site"] = "same-origin"
            h["accept-encoding"] = self._accept_encoding()

        if extra:
            h.update(extra)
        return h

    def _human_delay(self, base_min=0.15, base_max=0.45):
        try:
            d = random.uniform(base_min, base_max)
            if random.random() < 0.08:
                d += random.uniform(0.8, 2.2)
            time.sleep(d)
        except Exception:
            pass

    def get(self, url, headers=None, follow_redirects=True, document=False,
            referer=None, **kw):
        h = self._build_headers(extra=headers, document=document, referer=referer)
        last_err = None
        for i in range(3):
            try:
                self._human_delay(0.1, 0.3)
                return self.session.get(
                    url, headers=h, timeout=self.timeout,
                    allow_redirects=follow_redirects, **kw
                )
            except Exception as e:
                last_err = e
                AppLogger.warn(f"GET retry {i+1}: {str(e)[:120]}")
                time.sleep(1.5 + i)
        raise Exception(f"AntiDetect GET failed: {last_err}")

    def post(self, url, data=None, headers=None, follow_redirects=True,
             referer=None, document=False, **kw):
        h = self._build_headers(extra=headers, referer=referer, document=document)
        last_err = None
        for i in range(3):
            try:
                self._human_delay(0.15, 0.4)
                return self.session.post(
                    url, data=data, headers=h, timeout=self.timeout,
                    allow_redirects=follow_redirects, **kw
                )
            except Exception as e:
                last_err = e
                AppLogger.warn(f"POST retry {i+1}: {str(e)[:120]}")
                time.sleep(1.5 + i)
        raise Exception(f"AntiDetect POST failed: {last_err}")

    def post_multipart(self, url, params=None, files=None, headers=None,
                       referer=None, **kw):
        h = self._build_headers(extra=headers, referer=referer, document=False)
        h.pop("content-type", None)
        last_err = None
        for i in range(3):
            try:
                if HAS_CURL_MIME and files:
                    mp = CurlMime()
                    for field, val in (files or {}).items():
                        if isinstance(val, tuple) and len(val) == 3:
                            fname, content, mime = val
                            mp.addpart(
                                name=field,
                                data=content,
                                filename=fname,
                                content_type=mime,
                            )
                        elif isinstance(val, tuple) and len(val) == 2:
                            fname, content = val
                            mp.addpart(name=field, data=content, filename=fname)
                    try:
                        return self.session.post(
                            url, params=params, multipart=mp,
                            headers=h, timeout=self.timeout,
                            allow_redirects=True, **kw
                        )
                    finally:
                        try:
                            mp.close()
                        except Exception:
                            pass
                else:
                    return self.session.post(
                        url, params=params, files=files,
                        headers=h, timeout=self.timeout,
                        allow_redirects=True, **kw
                    )
            except Exception as e:
                last_err = e
                AppLogger.warn(f"UPLOAD retry {i+1}: {str(e)[:160]}")
                time.sleep(1.5 + i)
        raise Exception(f"AntiDetect UPLOAD failed: {last_err}")

    def get_cookies_dict(self):
        try:
            return dict(self.session.cookies)
        except Exception:
            return {}

    def get_cookie_string(self):
        try:
            return "; ".join(f"{k}={v}" for k, v in self.session.cookies.items())
        except Exception:
            return ""

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass


class ZYProxyBuyer:
    def __init__(self, username=ZY_DEFAULT_USER, password=ZY_DEFAULT_PASS, product_id=ZY_PRODUCT_ID):
        self.base_url = ZY_BASE_URL
        self.username = username
        self.password = password
        self.product_id = product_id
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            "User-Agent": ZY_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.6,en;q=0.5",
        })
        self.balance = ""
        self._logged_in = False

    def login(self):
        if self._logged_in:
            return True
        try:
            r = self.session.post(f"{self.base_url}/login",
                                  data={"username": self.username, "password": self.password},
                                  allow_redirects=True, timeout=30)
            if self.username.lower() in r.text.lower() and "logout" in r.text.lower():
                m = re.search(r'([\d.,]+)d', r.text)
                self.balance = m.group(1) if m else ""
                self._logged_in = True
                AppLogger.proxy(f"ZY login OK - balance {self.balance or '?'}")
                return True
            AppLogger.error("ZY login failed")
            return False
        except Exception as e:
            AppLogger.error(f"ZY login error: {e}")
            return False

    def _buy_proxy(self, qty=1):
        try:
            r = self.session.post(f"{self.base_url}/mua_proxy",
                                  data={"product_id": self.product_id, "qty": str(qty), "buy_proxy": ""},
                                  allow_redirects=True, timeout=30)
            keys = re.findall(r'([A-Z0-9]{20})', r.text)
            if keys:
                uniq = list(dict.fromkeys(keys))
                return uniq[-1] if uniq else None
            return None
        except Exception as e:
            AppLogger.error(f"ZY buy error: {e}")
            return None

    def _get_proxy_by_key(self, key):
        try:
            r = self.session.post(f"{self.base_url}/get_proxy",
                                  data={"key": key, "get_proxy": ""},
                                  allow_redirects=True, timeout=30)
            pattern = rf'([\d.]+:\d+:user\d+:[A-Za-z0-9]+).*?Key:\s*{re.escape(key)}'
            m = re.search(pattern, r.text, re.DOTALL)
            if m:
                return m.group(1)
            all_proxies = re.findall(r'([\d.]+:\d+:user\d+:[A-Za-z0-9]+)', r.text)
            all_keys = re.findall(r'Key:\s*([A-Z0-9]{20})', r.text)
            for i, k in enumerate(all_keys):
                if k == key and i < len(all_proxies):
                    return all_proxies[i]
            if all_proxies:
                return all_proxies[-1]
            return None
        except Exception as e:
            AppLogger.error(f"ZY get proxy error: {e}")
            return None

    def buy_and_get(self, qty=1):
        if not self.login():
            return None
        key = self._buy_proxy(qty=qty)
        if not key:
            AppLogger.error("ZY cannot buy proxy")
            return None
        time.sleep(1)
        proxy_str = self._get_proxy_by_key(key)
        if not proxy_str:
            AppLogger.error(f"ZY key {key} but no proxy")
            return None
        AppLogger.proxy(f"Bought - {proxy_str}  {C.DGRAY}(key {key}){C.RESET}")
        return proxy_str


class ProxyManager:
    @staticmethod
    def format_proxy_string(proxy_str):
        if not proxy_str:
            return None
        p = str(proxy_str).strip()
        if p.startswith(("http://", "https://", "socks5://", "socks5h://")):
            return p
        if "@" in p:
            return f"http://{p}"
        parts = p.split(":")
        if len(parts) == 4:
            ip, port, user, pwd = parts
            if not ip or not port.isdigit():
                return None
            return f"http://{user}:{pwd}@{ip}:{port}"
        if len(parts) == 2:
            ip, port = parts
            if not port.isdigit():
                return None
            return f"http://{ip}:{port}"
        return f"http://{p}"

    @staticmethod
    def get_tmproxy(api_key, id_location=0):
        try:
            url = "https://api.tmproxy.com/api/proxy/get-new-proxy"
            res = requests.post(url, json={"api_key": api_key, "id_location": id_location}, timeout=10).json()
            if res.get("code") == 0 and "data" in res:
                d = res["data"]
                https_proxy = d.get("https") or f"{d.get('ip')}:{d.get('port')}"
                return f"http://{https_proxy}"
        except Exception:
            pass
        return None

    @staticmethod
    def get_androidmodvip_proxy(api_key):
        try:
            r = requests.get("https://proxy.androidmodvip.io.vn/api/v3/users/rotatev2",
                             params={"token": api_key}, timeout=20)
            if r.status_code != 200:
                return None
            d = r.json()
            proxy = d.get("proxy") if isinstance(d, dict) else None
            if proxy:
                return ProxyManager.format_proxy_string(str(proxy).strip())
        except Exception:
            return None
        return None

    @staticmethod
    def list_androidmodvip_rotating_proxies(access_token, merchant_id):
        try:
            url = "https://proxy.androidmodvip.io.vn/api/v2/users/proxies"
            params = {
                "sort": '[{"orderBy":"createdAt","order":"desc"}]',
                "filters": '{"proxy":{"ipaddress":{"categorytype":{"id":2}}}}'
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
                "x-merchant-id": merchant_id
            }
            response = requests.get(url, params=params, headers=headers, timeout=20)
            if response.status_code == 401:
                AppLogger.error("AndroidModVip: Invalid or expired token (401)")
                return None
            if response.status_code != 200:
                return None
            data = response.json()
            if not isinstance(data, dict) or "data" not in data:
                return None

            proxies = []
            for item in data["data"]:
                proxy_info = item.get("proxy", {})
                ip_info = proxy_info.get("ipaddress", {})
                status_info = item.get("status", {})
                proxies.append({
                    "id": item.get("id"),
                    "code": item.get("code", ""),
                    "protocol": item.get("protocol", "HTTP"),
                    "domain": ip_info.get("domain", ""),
                    "location": ip_info.get("location", ""),
                    "provider": ip_info.get("provider", ""),
                    "ip": ip_info.get("ip", ""),
                    "username": proxy_info.get("username", ""),
                    "password": proxy_info.get("password", ""),
                    "port": proxy_info.get("port", 0),
                    "rotateInterval": proxy_info.get("rotateInterval", 0),
                    "status": status_info.get("name", ""),
                    "expiredAt": item.get("expiredAt", 0),
                })
            return proxies
        except Exception:
            return None

    @staticmethod
    def rotate_androidmodvip_proxy(access_token, proxy_id, wait_for_rotate=True):
        try:
            url = f"https://proxy.androidmodvip.io.vn/api/v2/proxies/{proxy_id}/rotate"
            headers = {"Authorization": f"Bearer {access_token}"}
            while True:
                response = requests.get(url, headers=headers, timeout=20)
                if response.status_code == 401:
                    AppLogger.error("[AndroidModVip] Token expired/invalid (401)")
                    return None
                if response.status_code == 404:
                    AppLogger.error(f"[AndroidModVip] Proxy id {proxy_id} not found (404)")
                    return None
                if response.status_code != 200:
                    AppLogger.warn(f"[AndroidModVip] HTTP {response.status_code}")
                    return None
                data = response.json()
                if not isinstance(data, dict):
                    return None

                status = str(data.get("status", "")).lower()
                time_remaining = int(data.get("timeRemaining", 0) or 0)

                if wait_for_rotate and status != "success" and time_remaining > 0:
                    AppLogger.info(f"[AndroidModVip] Cooldown active ({time_remaining}s). Waiting...")
                    time.sleep(time_remaining + 2)
                    continue

                proxy_raw = data.get("proxy", "")
                if status != "success" or not proxy_raw:
                    AppLogger.warn(f"[AndroidModVip] Rotate fail - status={status} proxy={bool(proxy_raw)}")
                    return None
                return ProxyManager.format_proxy_string(str(proxy_raw).strip())
        except Exception as e:
            AppLogger.warn(f"[AndroidModVip] rotate exception: {e}")
            return None

    @staticmethod
    def get_proxy5stars_proxy(api_key):
        try:
            r = requests.get("https://api.proxyxoay.org/api/key_xoay.php",
                             params={"key": api_key, "live": 5}, timeout=20)
            if r.status_code != 200:
                return None
            d = r.json()
            if not isinstance(d, dict):
                return None
            proxy_raw = d.get("proxyhttp") or d.get("proxysocks5")
            if proxy_raw:
                return ProxyManager.format_proxy_string(str(proxy_raw).strip())
        except Exception:
            return None
        return None

    @staticmethod
    def get_homeproxy(api_key):
        try:
            r = requests.get(HOMEPROXY_ENDPOINT,
                             params={"token": api_key}, timeout=25)
            if r.status_code != 200:
                AppLogger.warn(f"HomeProxy HTTP {r.status_code}")
                return None
            d = r.json()
            if not isinstance(d, dict):
                return None

            proxy_raw = d.get("proxy")
            status = d.get("status")
            msg = str(d.get("message", ""))[:80]

            if not proxy_raw:
                AppLogger.warn(f"HomeProxy no proxy - status={status} - {msg}")
                return None

            ip = d.get("ip", "?")
            tr = d.get("timeRemaining", "?")
            if status == "success":
                AppLogger.proxy(f"HomeProxy rotated - {proxy_raw}  {C.DGRAY}[ip={ip} / wait={tr}s]{C.RESET}")
            else:
                AppLogger.proxy(f"HomeProxy reuse - {proxy_raw}  {C.DGRAY}[{msg} / wait={tr}s]{C.RESET}")

            return ProxyManager.format_proxy_string(str(proxy_raw).strip())
        except Exception as e:
            AppLogger.warn(f"HomeProxy error: {e}")
            return None
        return None

    @staticmethod
    def check_homeproxy(api_key):
        try:
            r = requests.get(HOMEPROXY_ENDPOINT,
                             params={"token": api_key, "checkOnly": "true"}, timeout=25)
            if r.status_code != 200:
                AppLogger.warn(f"HomeProxy HTTP {r.status_code}")
                return None
            d = r.json()
            if isinstance(d, dict) and d.get("proxy"):
                return d
        except Exception as e:
            AppLogger.warn(f"HomeProxy check error: {e}")
        return None


SURNAMES_VN = ["Nguyễn","Trần","Lê","Phạm","Hoàng","Huỳnh","Phan","Vũ","Võ","Đặng","Bùi","Đỗ","Ngô","Đinh","Dương"]
MALE_VN = ["Anh","Bảo","Cường","Dũng","Đức","Hải","Hiếu","Hoàng","Hùng","Khánh","Long","Minh","Nam","Phong","Quang"]
FEMALE_VN = ["Anh","Chi","Dung","Hà","Hằng","Hương","Lan","Linh","Mai","My","Ngọc","Nhung","Phương","Quỳnh","Thu"]

SURNAMES_US = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Rodriguez","Martinez","Hernandez","Lopez","Gonzalez","Wilson","Anderson"]
MALE_US = ["James","John","Robert","Michael","William","David","Richard","Joseph","Thomas","Charles","Christopher","Daniel","Matthew","Anthony","Donald"]
FEMALE_US = ["Mary","Patricia","Jennifer","Linda","Barbara","Elizabeth","Susan","Jessica","Sarah","Karen","Lisa","Nancy","Betty","Margaret","Sandra"]

SURNAMES_DE = ["Müller","Schmidt","Schneider","Fischer","Weber","Meyer","Wagner","Becker","Schulz","Hoffmann","Schäfer","Koch","Bauer","Richter","Klein"]
MALE_DE = ["Hans","Peter","Klaus","Jürgen","Karl","Heinz","Horst","Walter","Günter","Friedrich","Erich","Albert","Werner","Gerhard","Wolfgang"]
FEMALE_DE = ["Anna","Maria","Margarete","Gertrud","Ursula","Elisabeth","Helga","Hildegard","Ingrid","Karin","Monika","Christine","Petra","Sabine","Susanne"]

SURNAMES_FR = ["Martin","Bernard","Dubois","Thomas","Robert","Richard","Petit","Durand","Leroy","Moreau","Simon","Laurent","Lefebvre","Michel","García"]
MALE_FR = ["Jean","Pierre","Michel","André","Louis","Charles","François","Paul","Henri","Maurice","Philippe","Jacques","René","Émile","Gustave"]
FEMALE_FR = ["Marie","Jeanne","Anne","Catherine","Marguerite","Françoise","Élisabeth","Louise","Jacqueline","Simone","Suzanne","Monique","Nicole","Christine","Camille"]

SURNAMES_TH = ["สมศักดิ์","วิชัย","ประเสริฐ","ชัย","สุชาติ","วิเชียร","สมชาย","ไพโรจน์","ทวี","สง่า","ชูศักดิ์","สวัสดิ์","อุดม","บุญมา","พงษ์","ศิริ","จันทร์","ทอง","เพชร","รัตนา"]
MALE_TH = ["ใจดี","รักไทย","ศรีสุข","ทองดี","พรไทย","แสงทอง","บุญมี","สุขใจ","เมืองไทย","เพชรดี","ดวงแก้ว","พร้อมมา","วัฒนา","สมบูรณ์","เจริญ"]
FEMALE_TH = ["ใจดี","รักไทย","ศรีสุข","ทองดี","พรไทย","แสงทอง","บุญมี","สุขใจ","เมืองไทย","เพชรดี","ดวงแก้ว","พร้อมมา","วัฒนา","สมบูรณ์","เจริญ"]

SURNAMES_JP = ["佐藤","鈴木","高橋","田中","伊藤","渡辺","山本","中村","小林","加藤","吉田","山田","佐々木","山口","松本"]
MALE_JP = ["大輔","翔太","健太","拓也","悠斗","大和","陽翔","湊","蓮","悠真","颯太","樹","大輝","陸","蒼"]
FEMALE_JP = ["さくら","陽菜","美咲","葵","結衣","愛","凛","美羽","桜","楓","芽依","美月","小春","莉子","花"]

SURNAMES_KR = ["김","이","박","최","정","강","조","윤","장","임","한","오","서","신","권"]
MALE_KR = ["민준","서준","도윤","예준","시우","하준","주원","지호","지후","준서","준우","현우","도현","지훈","건우"]
FEMALE_KR = ["서연","서윤","지우","서현","민서","하은","하윤","윤서","지민","채원","지윤","은서","다은","예은","수아"]

SURNAMES_CN = ["王","李","张","刘","陈","杨","黄","赵","周","吴","徐","孙","马","朱","胡","郭","何","林","罗","郑"]
MALE_CN = ["伟","强","磊","军","洋","勇","杰","涛","超","明","鹏","辉","斌","波","亮","浩宇","俊杰","子轩","浩然","宇航"]
FEMALE_CN = ["芳","娜","敏","静","丽","艳","娟","霞","秀英","秀兰","玲","燕","梅","雪","婷","颖","琳","倩","雨欣","佳怡"]

COUNTRY_META = {
    "vn": {"flag": "VN", "label": "Vietnam", "locale": "vi_VN",
           "surnames": SURNAMES_VN, "male": MALE_VN, "female": FEMALE_VN,
           "name_order": "last_first"},
    "us": {"flag": "US", "label": "United States", "locale": "en_US",
           "surnames": SURNAMES_US, "male": MALE_US, "female": FEMALE_US,
           "name_order": "first_last"},
    "de": {"flag": "DE", "label": "Germany", "locale": "de_DE",
           "surnames": SURNAMES_DE, "male": MALE_DE, "female": FEMALE_DE,
           "name_order": "first_last"},
    "fr": {"flag": "FR", "label": "France", "locale": "fr_FR",
           "surnames": SURNAMES_FR, "male": MALE_FR, "female": FEMALE_FR,
           "name_order": "first_last"},
    "th": {"flag": "TH", "label": "Thailand", "locale": "th_TH",
           "surnames": SURNAMES_TH, "male": MALE_TH, "female": FEMALE_TH,
           "name_order": "first_last"},
    "jp": {"flag": "JP", "label": "Japan", "locale": "ja_JP",
           "surnames": SURNAMES_JP, "male": MALE_JP, "female": FEMALE_JP,
           "name_order": "last_first"},
    "kr": {"flag": "KR", "label": "Korea", "locale": "ko_KR",
           "surnames": SURNAMES_KR, "male": MALE_KR, "female": FEMALE_KR,
           "name_order": "last_first"},
    "cn": {"flag": "CN", "label": "China", "locale": "zh_CN",
           "surnames": SURNAMES_CN, "male": MALE_CN, "female": FEMALE_CN,
           "name_order": "last_first"},
}
ALL_COUNTRIES = list(COUNTRY_META.keys())


US_AREA_CODES = [
    "205","251","256","334","938",
    "907",
    "480","520","602","623","928",
    "479","501","870",
    "209","213","310","323","408","415","424","442","510","530","559","562","619","626","650","657","661","669","707","714","747","760","805","818","831","858","909","916","925","949","951",
    "303","719","720","970",
    "203","475","860","959",
    "302",
    "239","305","321","352","386","407","561","727","754","772","786","813","850","863","904","941","954",
    "229","404","470","478","678","706","762","770","912",
    "808",
    "208","986",
    "217","224","309","312","331","618","630","708","773","779","815","847","872",
    "219","260","317","463","574","765","812","930",
    "319","515","563","641","712",
    "316","620","785","913",
    "270","364","502","606","859",
    "225","318","337","504","985",
    "207",
    "227","240","301","410","443","667",
    "339","351","413","508","617","774","781","857","978",
    "231","248","269","313","517","586","616","734","810","906","947","989",
    "218","320","507","612","651","763","952",
    "228","601","662","769",
    "314","417","557","573","636","660","816",
    "406",
    "308","402","531",
    "702","725","775",
    "603",
    "201","551","609","640","732","848","856","862","908","973",
    "505","575",
    "212","315","332","347","516","518","585","607","631","646","680","716","718","838","845","914","917","929","934",
    "252","336","704","743","828","910","919","980","984",
    "701",
    "216","220","234","330","380","419","440","513","567","614","740","937",
    "405","539","572","580","918",
    "458","503","541","971",
    "215","223","267","272","412","445","484","570","610","717","724","814","878",
    "401",
    "803","839","843","854","864",
    "605",
    "423","615","629","731","865","901","931",
    "210","214","254","281","325","346","361","409","430","432","469","512","682","713","726","737","806","817","830","832","903","915","936","940","945","956","972","979",
    "385","435","801",
    "802",
    "276","434","540","571","703","757","804",
    "206","253","360","425","509","564",
    "304","681",
    "262","414","534","608","715","920",
    "307",
    "202",
]

US_INVALID_AREA_CODES = {
    "800","833","844","855","866","877","888","889","900","911","411",
    "500","522","533","544","555","566","577","588",
}

VALID_US_AREA_CODES = [c for c in US_AREA_CODES if c not in US_INVALID_AREA_CODES]


def _gen_us_line_number():
    n1 = random.randint(2, 9)
    x1 = random.randint(0, 9)
    x2 = random.randint(0, 9)
    n2 = random.randint(2, 9)
    x3 = random.randint(0, 9)
    x4 = random.randint(0, 9)
    x5 = random.randint(0, 9)
    return f"{n1}{x1}{x2}{n2}{x3}{x4}{x5}"


def generate_fake_phone(area_code=None):
    if area_code:
        area = area_code
    else:
        area = random.choice(VALID_US_AREA_CODES)
    line = _gen_us_line_number()
    return f"+1{area}{line}"


def validate_us_phone(phone):
    if not phone:
        return False
    p = re.sub(r"[\s\-\(\)]+", "", str(phone))
    if p.startswith("+1"):
        p = p[2:]
    elif p.startswith("1") and len(p) == 11:
        p = p[1:]
    if not p.isdigit() or len(p) != 10:
        return False
    area = p[:3]
    exchange = p[3:6]
    if area in US_INVALID_AREA_CODES:
        return False
    if area not in US_AREA_CODES:
        return False
    if area[0] in ("0", "1"):
        return False
    if exchange[0] in ("0", "1"):
        return False
    return True


def generate_valid_us_phone(max_attempts=20):
    for _ in range(max_attempts):
        p = generate_fake_phone()
        if validate_us_phone(p):
            return p
    return generate_fake_phone()


def generate_random_name(countries=None):
    pool = countries or ALL_COUNTRIES
    country = random.choice(pool)
    gender_int = random.choice([1, 2])
    meta = COUNTRY_META[country]
    last_name = random.choice(meta["surnames"])
    first_name = random.choice(meta["male"] if gender_int == 2 else meta["female"])
    return last_name, first_name, country, gender_int, meta["locale"]


def format_full_name(last_name, first_name, country):
    meta = COUNTRY_META.get(country, {})
    order = meta.get("name_order", "first_last")
    if order == "last_first":
        return f"{last_name} {first_name}"
    return f"{first_name} {last_name}"


def generate_fake_email():
    providers = ["gmail.com", "icloud.com"]
    provider = random.choice(providers)

    first_parts = ["john", "jane", "mike", "sarah", "david", "emma", "alex", "lisa",
                   "kevin", "anna", "ryan", "mia", "tom", "lily", "jack", "rose",
                   "ben", "chloe", "sam", "zoe", "max", "ella", "leo", "ivy",
                   "noah", "ava", "liam", "sophia", "oliver", "isabella",
                   "lucas", "mia", "henry", "amelia", "jack", "harper"]
    last_parts = ["smith", "johnson", "williams", "brown", "jones", "garcia",
                  "miller", "davis", "wilson", "moore", "taylor", "anderson",
                  "thomas", "jackson", "white", "harris", "martin", "thompson",
                  "lee", "walker", "hall", "allen", "young", "king",
                  "wright", "scott", "green", "baker", "adams", "nelson"]

    style = random.randint(1, 3)
    if style == 1:
        local = f"{random.choice(first_parts)}{random.choice(last_parts)}"
    elif style == 2:
        local = f"{random.choice(first_parts)}{random.randint(100, 9999)}"
    else:
        local = f"{random.choice(first_parts)}{random.choice(last_parts)}{random.randint(10, 999)}"

    local = f"{local}{random.randint(10, 999)}"
    return f"{local}@{provider}"


def generate_secure_password():
    prefixes = ["Thanh", "Minh", "Ngoc", "Phuong", "Tuan", "Hoang", "Khanh", "Quang", "Bao", "Anh"]
    suffixes = ["Pass", "Sec", "Net", "Key", "Acc", "Vn"]
    specials = ["@", "#", "$", "!"]
    return f"{random.choice(prefixes)}{random.choice(suffixes)}{random.choice(specials)}{random.randint(1996, 2026)}{random.randint(10, 99)}"


def build_adult_birth_year(min_age=18, max_age=40):
    cur = time.localtime().tm_year
    lo, hi = cur - max_age, cur - min_age
    if lo > hi:
        lo, hi = hi, lo
    return random.randint(lo, hi)


@dataclass
class AccountProfile:
    first_name: str
    last_name: str
    gender: str = "MALE"
    birthday_day: int = 12
    birthday_month: int = 5
    birthday_year: int = 2000
    email: Optional[str] = None
    phone: Optional[str] = None
    password: str = "FacebookPass123!"
    country: str = "us"


@dataclass
class RegistrationResult:
    status: str = "INIT"
    uid: Optional[str] = None
    password: Optional[str] = None
    twofa_secret: Optional[str] = None
    cookie_str: Optional[str] = None
    token_eaaau: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None
    country: Optional[str] = None
    error_message: Optional[str] = None
    fake_email: Optional[str] = None

    def to_success_line(self):
        uid = self.uid or "N/A"
        pwd = self.password or "N/A"
        cookie = self.cookie_str or "N/A"
        token = self.token_eaaau or "N/A"
        mail = self.email or self.phone or "N/A"
        name = self.name or "N/A"
        if self.twofa_secret:
            return f"{uid}|{pwd}|{self.twofa_secret}|{cookie}|{token}|{mail}|{name}"
        return f"{uid}|{pwd}|{cookie}|{token}|{mail}|{name}"

    def to_checkpoint_line(self):
        return f"{self.uid or 'N/A'}|{self.password or 'N/A'}|{self.cookie_str or 'N/A'}|{self.email or 'N/A'} | {self.error_message or 'Unknown'}"


class ResultWriter:
    OUTPUT_DIR = "output"
    SUCCESS_FILE = os.path.join(OUTPUT_DIR, "success.txt")
    CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, "checkpoint.txt")
    FAILED_FILE = os.path.join(OUTPUT_DIR, "failed.txt")

    @classmethod
    def _ensure_dir(cls):
        try:
            os.makedirs(cls.OUTPUT_DIR, exist_ok=True)
        except Exception:
            pass

    @classmethod
    def _append_line(cls, filepath, line):
        cls._ensure_dir()
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(line.rstrip("\n") + "\n")
            f.flush()

    @classmethod
    def save_success(cls, result):
        cls._append_line(cls.SUCCESS_FILE, result.to_success_line())
        AppLogger.success(f"Saved -> {cls.SUCCESS_FILE}")

    @classmethod
    def save_checkpoint(cls, result):
        cls._append_line(cls.CHECKPOINT_FILE, result.to_checkpoint_line())

    @classmethod
    def save_failed(cls, result):
        cls._append_line(cls.FAILED_FILE, result.to_checkpoint_line())

    @classmethod
    def route(cls, result):
        st = (result.status or "").upper()
        try:
            if st in ("SUCCESS", "LIVE"):
                cls.save_success(result)
            elif "CHECKPOINT" in st:
                cls.save_checkpoint(result)
            else:
                cls.save_failed(result)
        except Exception as e:
            AppLogger.warn(f"ResultWriter error: {e}")


class WWWClient:
    def __init__(self, proxy=None, timeout=45):
        self.proxy = ProxyManager.format_proxy_string(proxy) if proxy else None
        self.timeout = timeout
        self._anti = False
        self.session = None
        self.ua = USER_AGENT_DESKTOP

        if HAS_CURL_CFFI:
            try:
                self.session = AntiDetectSession(
                    proxy=self.proxy,
                    impersonate=None,
                    timeout=timeout,
                )
                self.ua = self.session.fp["ua"]
                self._anti = True
            except Exception as e:
                AppLogger.warn(f"AntiDetect init fail: {str(e)[:140]} - fallback requests")
                self.session = None

        if not self._anti:
            self.session = requests.Session()
            self.session.verify = False
            if self.proxy:
                self.session.proxies = {"http": self.proxy, "https": self.proxy}
            self.ua = USER_AGENT_DESKTOP

    def _fallback_headers(self, extra=None, referer=None, document=False):
        h = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "origin": "https://www.facebook.com",
            "user-agent": self.ua,
            "sec-fetch-dest": "document" if document else "empty",
            "sec-fetch-mode": "navigate" if document else "cors",
            "sec-fetch-site": "none" if document else "same-origin",
            "x-asbd-id": "359341",
            "sec-ch-ua": SEC_CH_UA_FULL,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua-platform-version": '"19.0.0"',
            "sec-ch-ua-arch": '"x86"',
            "sec-ch-ua-bitness": '"64"',
            "sec-ch-ua-model": '""',
            "sec-ch-ua-full-version-list": SEC_CH_UA_FULL_VERSION_LIST,
            "sec-ch-ua-full-version": '"154.0.8037.57"',
        }
        if referer:
            h["referer"] = referer
        if extra:
            h.update(extra)
        return h

    def get(self, url, headers=None, follow_redirects=True, document=False, **kw):
        referer = kw.pop("referer", None)
        if self._anti:
            return self.session.get(
                url, headers=headers, follow_redirects=follow_redirects,
                document=document, referer=referer, **kw
            )
        h = self._fallback_headers(extra=headers, referer=referer, document=document)
        for i in range(3):
            try:
                return self.session.get(url, headers=h, timeout=self.timeout,
                                        allow_redirects=follow_redirects, **kw)
            except Exception as e:
                AppLogger.warn(f"GET retry {i+1}: {str(e)[:120]}")
                time.sleep(1.5)
        raise Exception("WWW GET failed")

    def post(self, url, data=None, headers=None, follow_redirects=True, **kw):
        referer = kw.pop("referer", None)
        if self._anti:
            return self.session.post(
                url, data=data, headers=headers,
                follow_redirects=follow_redirects, referer=referer, **kw
            )
        h = self._fallback_headers(extra=headers)
        for i in range(3):
            try:
                return self.session.post(url, data=data, headers=h, timeout=self.timeout,
                                         allow_redirects=follow_redirects, **kw)
            except Exception as e:
                AppLogger.warn(f"POST retry {i+1}: {str(e)[:120]}")
                time.sleep(1.5)
        raise Exception("WWW POST failed")

    def post_multipart(self, url, params=None, files=None, headers=None, **kw):
        referer = kw.pop("referer", None)
        if self._anti:
            return self.session.post_multipart(
                url, params=params, files=files, headers=headers,
                referer=referer, **kw
            )
        h = self._fallback_headers(extra=headers)
        h.pop("content-type", None)
        return self.session.post(url, params=params, files=files,
                                 headers=h, timeout=self.timeout,
                                 allow_redirects=True, **kw)

    def get_cookies_dict(self):
        if self._anti:
            return self.session.get_cookies_dict()
        return dict(self.session.cookies)

    def get_cookie_string(self):
        if self._anti:
            return self.session.get_cookie_string()
        return "; ".join(f"{k}={v}" for k, v in self.session.cookies.items())


class WWWRegEngine:
    REG_PAGE = "https://www.facebook.com/reg/?entry_point=login"
    HOMEPAGE = "https://www.facebook.com/"
    CONFIRM_PAGE = "https://www.facebook.com/confirmemail.php?next=undefined"
    GRAPHQL_URL = "https://www.facebook.com/api/graphql/"

    def __init__(self, client: WWWClient):
        self.client = client
        self.pub_key_data = None
        self.lsd = ""
        self.jazoest = ""
        self.fb_dtsg = ""
        self.rev = "1048468692"
        self.hsi = "7689480470427579624"
        self.spin_r = "1048468692"
        self.spin_t = ""
        self.s = ""
        self.hs = "20721.HYP:comet_plat_default_pkg.2.1...0"
        self.dyn = ""
        self.csr = ""
        self.hsdp = ""
        self.hblp = ""
        self.sjsp = ""
        self._req_counter = 0

    def _next_req(self):
        self._req_counter += 1
        n = self._req_counter
        if n < 10:
            return str(n)
        return chr(ord('a') + (n - 10))

    @staticmethod
    def _search(html, pat, default=""):
        m = re.search(pat, html)
        return m.group(1) if m else default

    def warmup_homepage(self):
        AppLogger.step(1, "Warmup", "GET homepage")
        try:
            r = self.client.get(
                self.HOMEPAGE,
                headers={
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "upgrade-insecure-requests": "1",
                },
                follow_redirects=True,
                document=True,
            )
            html = r.text or ""
            AppLogger.info(f"Homepage loaded - HTTP {r.status_code}, {len(html)} bytes")

            if len(html) < 2000:
                AppLogger.warn(f"Homepage returned short ({len(html)} bytes)")

            hs_val = self._search(html, r'"haste_session"\s*:\s*"([^"]+)"')
            if hs_val:
                self.hs = hs_val

            return True
        except Exception as e:
            AppLogger.warn(f"Homepage warmup error: {e}")
            return False

    def load_www_tokens(self):
        AppLogger.step(2, "Load tokens", "GET /reg/")
        try:
            r = self.client.get(
                self.REG_PAGE,
                headers={
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "upgrade-insecure-requests": "1",
                },
                follow_redirects=True,
                document=True,
            )
            html = r.text or ""

            m = re.search(
                r'"caa_password_encryption_data"\s*:\s*\{\s*'
                r'"encryption_data"\s*:\s*\{\s*'
                r'"key_id"\s*:\s*(\d+)\s*,\s*'
                r'"public_key"\s*:\s*"([a-fA-F0-9]+)"',
                html
            )
            if m:
                self.pub_key_data = {"keyId": int(m.group(1)), "publicKey": m.group(2)}
            else:
                kid = self._search(html, r'"key_id"\s*:\s*(\d+)')
                pk = self._search(html, r'"public_key"\s*:\s*"([a-fA-F0-9]+)"')
                if kid and pk:
                    self.pub_key_data = {"keyId": int(kid), "publicKey": pk}

            self.lsd = (
                self._search(html, r'name="lsd"\s+value="([^"]+)"') or
                self._search(html, r'"LSD"\s*,\s*\[\s*\]\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"')
            )
            if self.lsd:
                self.jazoest = f"2{sum(ord(c) for c in self.lsd)}"

            self.fb_dtsg = (
                self._search(html, r'name="fb_dtsg"\s+value="([^"]+)"') or
                self._search(html, r'"DTSGInitialData"\s*,\s*\[\s*\]\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"') or
                self._search(html, r'"fbdtsg"\s*,\s*\[\s*\]\s*,\s*\{[^}]*"token"\s*:\s*"([^"]+)"')
            )

            rev = self._search(html, r'"server_revision"\s*:\s*(\d+)')
            if rev:
                self.rev = rev
            else:
                self.rev = self._search(html, r'"__spin_r"\s*:\s*(\d+)', self.rev)

            self.hsi = self._search(html, r'"hsi"\s*:\s*"(\d+)"', self.hsi)
            self.spin_r = self._search(html, r'"__spin_r"\s*:\s*(\d+)', self.spin_r)
            self.spin_t = self._search(html, r'"__spin_t"\s*:\s*(\d+)') or str(int(time.time()))

            hs_val = self._search(html, r'"haste_session"\s*:\s*"([^"]+)"')
            if hs_val:
                self.hs = hs_val

            self.s = self._search(html, r'"__s"\s*:\s*"([^"]+)"', self.s)
            self.dyn = self._search(html, r'"__dyn"\s*:\s*"([^"]+)"', self.dyn)
            self.csr = self._search(html, r'"__csr"\s*:\s*"([^"]+)"', self.csr)
            self.hsdp = self._search(html, r'"__hsdp"\s*:\s*"([^"]+)"', self.hsdp)
            self.hblp = self._search(html, r'"__hblp"\s*:\s*"([^"]+)"', self.hblp)
            self.sjsp = self._search(html, r'"__sjsp"\s*:\s*"([^"]+)"', self.sjsp)

            if self.lsd:
                AppLogger.token("lsd", self.lsd)
                AppLogger.token("jazoest", self.jazoest)
            if self.pub_key_data:
                AppLogger.token("pubkey", f"keyId={self.pub_key_data['keyId']}")
            else:
                AppLogger.warn("No pubkey found - register will send plaintext")

            return bool(self.lsd)
        except Exception as e:
            AppLogger.error(f"load_www_tokens: {e}")
            return False

    def encrypt_password(self, password):
        if not self.pub_key_data:
            return None
        if not HAS_NACL or not HAS_CRYPTOGRAPHY:
            AppLogger.warn("Missing pynacl/cryptography - cannot encrypt")
            return None
        try:
            ts = str(int(time.time()))
            key_id = int(self.pub_key_data["keyId"])
            pub = bytes.fromhex(self.pub_key_data["publicKey"])
            if len(pub) != 32:
                AppLogger.warn(f"Invalid pubkey length: {len(pub)}")
                return None

            key = nacl.utils.random(32)
            aes = AESGCM(key)
            enc = aes.encrypt(bytes(12), password.encode(), ts.encode())
            sealed = SealedBox(PublicKey(pub)).encrypt(key)

            buf = bytearray(4 + len(sealed) + len(enc))
            buf[0] = 1
            buf[1] = key_id
            buf[2:4] = len(sealed).to_bytes(2, "little")
            buf[4:4 + len(sealed)] = sealed
            buf[4 + len(sealed):4 + len(sealed) + 16] = enc[-16:]
            buf[4 + len(sealed) + 16:] = enc[:-16]

            return f"#PWD_BROWSER:5:{ts}:{base64.b64encode(bytes(buf)).decode()}"
        except Exception as e:
            AppLogger.warn(f"Encrypt error: {e}")
            return None

    def refresh_from_confirm(self):
        try:
            r = self.client.get(
                self.CONFIRM_PAGE,
                headers={
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "upgrade-insecure-requests": "1",
                },
                follow_redirects=True,
                document=True,
            )
            html = r.text or ""
            if len(html) < 2000:
                return False

            if not self.pub_key_data:
                m_pk = re.search(
                    r'"caa_password_encryption_data"\s*:\s*\{\s*'
                    r'"encryption_data"\s*:\s*\{\s*'
                    r'"key_id"\s*:\s*(\d+)\s*,\s*'
                    r'"public_key"\s*:\s*"([a-fA-F0-9]+)"',
                    html
                )
                if m_pk:
                    self.pub_key_data = {"keyId": int(m_pk.group(1)), "publicKey": m_pk.group(2)}

            m = re.search(r'name="lsd"\s+value="([^"]+)"', html) or \
                re.search(r'"LSD"\s*,\s*\[\s*\]\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"', html)
            if m:
                self.lsd = m.group(1)
                self.jazoest = f"2{sum(ord(c) for c in self.lsd)}"

            m = (re.search(r'name="fb_dtsg"\s+value="([^"]+)"', html) or
                 re.search(r'"DTSGInitialData"\s*,\s*\[\s*\]\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"', html) or
                 re.search(r'"fbdtsg"\s*,\s*\[\s*\]\s*,\s*\{[^}]*"token"\s*:\s*"([^"]+)"', html))
            if m:
                self.fb_dtsg = m.group(1)

            rev = self._search(html, r'"server_revision"\s*:\s*(\d+)')
            if rev:
                self.rev = rev
            self.hsi = self._search(html, r'"hsi"\s*:\s*"(\d+)"', self.hsi)
            self.spin_r = self._search(html, r'"__spin_r"\s*:\s*(\d+)', self.spin_r)
            self.spin_t = self._search(html, r'"__spin_t"\s*:\s*(\d+)') or str(int(time.time()))
            hs_val = self._search(html, r'"haste_session"\s*:\s*"([^"]+)"')
            if hs_val:
                self.hs = hs_val
            self.s = self._search(html, r'"__s"\s*:\s*"([^"]+)"', self.s)
            self.dyn = self._search(html, r'"__dyn"\s*:\s*"([^"]+)"', self.dyn)
            self.csr = self._search(html, r'"__csr"\s*:\s*"([^"]+)"', self.csr)
            self.hsdp = self._search(html, r'"__hsdp"\s*:\s*"([^"]+)"', self.hsdp)
            self.hblp = self._search(html, r'"__hblp"\s*:\s*"([^"]+)"', self.hblp)
            self.sjsp = self._search(html, r'"__sjsp"\s*:\s*"([^"]+)"', self.sjsp)
            return bool(self.lsd and self.fb_dtsg)
        except Exception as e:
            debug_log("refresh_from_confirm", str(e))
            return False

    def refresh_from_home(self):
        try:
            r = self.client.get(
                self.HOMEPAGE,
                headers={
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "upgrade-insecure-requests": "1",
                },
                follow_redirects=True, document=True,
            )
            html = r.text or ""
            if len(html) < 5000:
                return False

            m = re.search(r'name="lsd"\s+value="([^"]+)"', html) or \
                re.search(r'"LSD"\s*,\s*\[\s*\]\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"', html)
            if m:
                self.lsd = m.group(1)
                self.jazoest = f"2{sum(ord(c) for c in self.lsd)}"

            m = (re.search(r'name="fb_dtsg"\s+value="([^"]+)"', html) or
                 re.search(r'"DTSGInitialData"\s*,\s*\[\s*\]\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"', html) or
                 re.search(r'"fbdtsg"\s*,\s*\[\s*\]\s*,\s*\{[^}]*"token"\s*:\s*"([^"]+)"', html))
            if m:
                self.fb_dtsg = m.group(1)

            rev = self._search(html, r'"server_revision"\s*:\s*(\d+)')
            if rev:
                self.rev = rev
            self.hsi = self._search(html, r'"hsi"\s*:\s*"(\d+)"', self.hsi)
            self.spin_r = self._search(html, r'"__spin_r"\s*:\s*(\d+)', self.spin_r)
            self.spin_t = self._search(html, r'"__spin_t"\s*:\s*(\d+)') or str(int(time.time()))
            hs_val = self._search(html, r'"haste_session"\s*:\s*"([^"]+)"')
            if hs_val:
                self.hs = hs_val
            self.s = self._search(html, r'"__s"\s*:\s*"([^"]+)"', self.s)
            self.dyn = self._search(html, r'"__dyn"\s*:\s*"([^"]+)"', self.dyn)
            self.csr = self._search(html, r'"__csr"\s*:\s*"([^"]+)"', self.csr)
            self.hsdp = self._search(html, r'"__hsdp"\s*:\s*"([^"]+)"', self.hsdp)
            self.hblp = self._search(html, r'"__hblp"\s*:\s*"([^"]+)"', self.hblp)
            self.sjsp = self._search(html, r'"__sjsp"\s*:\s*"([^"]+)"', self.sjsp)
            return bool(self.lsd and self.fb_dtsg)
        except Exception as e:
            debug_log("refresh_from_home", str(e))
            return False

    def _gql_headers_guest(self, friendly):
        base = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://www.facebook.com",
            "referer": self.REG_PAGE,
            "x-asbd-id": "359341",
            "x-fb-friendly-name": friendly,
            "x-fb-lsd": self.lsd,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }
        if not getattr(self.client, "_anti", False):
            base.update({
                "user-agent": self.client.ua,
                "sec-ch-ua": SEC_CH_UA_FULL,
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-ch-ua-full-version-list": SEC_CH_UA_FULL_VERSION_LIST,
                "sec-ch-ua-model": '""',
                "sec-ch-ua-platform-version": '"19.0.0"',
                "accept-language": "en-US,en;q=0.9",
            })
        return base

    def _gql_body_guest(self, req, variables, friendly, doc_id, qpl="516759801"):
        return {
            "av": "0", "__user": "0", "__a": "1", "__req": req,
            "__hs": self.hs, "dpr": "1", "__ccg": "EXCELLENT", "__rev": self.rev,
            "__s": self.s, "__hsi": self.hsi, "__dyn": self.dyn, "__csr": self.csr,
            "__hsdp": self.hsdp, "__hblp": self.hblp, "__sjsp": self.sjsp,
            "__comet_req": "102",
            "lsd": self.lsd, "jazoest": self.jazoest,
            "__spin_r": self.spin_r, "__spin_b": "trunk", "__spin_t": self.spin_t,
            "qpl_active_flow_ids": qpl,
            "fb_api_caller_class": "RelayModern",
            "fb_api_req_friendly_name": friendly,
            "server_timestamps": "true",
            "variables": json.dumps(variables, separators=(",", ":")),
            "doc_id": doc_id,
            "fb_api_analytics_tags": f'["qpl_active_flow_ids={qpl}"]',
        }

    def check_submit(self, profile: AccountProfile) -> bool:
        AppLogger.step(3, "Check submit", "validate fields")
        try:
            contact = profile.email or profile.phone or ""
            cp_type = "PHONE" if contact.startswith("+") else "EMAIL"
            variables = {
                "input": {
                    "contactpoint": {"sensitive_string_value": contact},
                    "contactpoint_type": cp_type,
                    "fetch_username_suggestions": True,
                    "field_name": "CONTACTPOINT",
                    "firstname": {"sensitive_string_value": profile.first_name},
                    "fullname": {"sensitive_string_value": ""},
                    "lastname": {"sensitive_string_value": profile.last_name},
                    "machine_id": "",
                },
                "scale": 1,
            }
            body = self._gql_body_guest(
                self._next_req(), variables,
                FRIENDLY_CHECK_VALID, DOC_CHECK_VALID,
                qpl="516759801"
            )
            r = self.client.post(
                self.GRAPHQL_URL, data=body,
                headers=self._gql_headers_guest(FRIENDLY_CHECK_VALID),
                follow_redirects=False,
            )
            debug_log("CHECK-RESP", (r.text or "")[:1000])
            if r.status_code != 200:
                AppLogger.warn(f"Check HTTP {r.status_code}")
                return False
            text = r.text[9:] if r.text.startswith("for (;;);") else r.text
            try:
                resp = json.loads(text)
            except Exception:
                AppLogger.warn("Check bad json")
                return False
            node = resp.get("data", {}).get("xfb_caa_registration_field_validation", {}) or {}
            status = node.get("status", "")
            if status == "SUCCESS":
                AppLogger.check(f"Field valid - jurisdiction={node.get('regulation_jurisdiction','')}")
                return True
            err = node.get("error") or resp.get("errors") or status or "UNKNOWN"
            AppLogger.warn(f"Field invalid - {str(err)[:120]}")
            return False
        except Exception as e:
            AppLogger.warn(f"Check error: {e}")
            return False

    def submit_registration(self, profile: AccountProfile):
        AppLogger.step(4, "Register", format_full_name(profile.last_name, profile.first_name, profile.country))

        enc = self.encrypt_password(profile.password)
        if not enc:
            AppLogger.warn("Encrypt failed - fallback plaintext")
            enc = profile.password
        else:
            AppLogger.info(f"Password encrypted - {len(enc)} chars")

        contact = profile.email or profile.phone or ""
        cp_type = "PHONE" if contact.startswith("+") else "EMAIL"

        variables = {
            "input": {
                "actor_id": "0",
                "client_mutation_id": str(uuid.uuid4()),
                "machine_id": "",
                "next_uri": "undefined",
                "reg_data": {
                    "birthday_day": profile.birthday_day,
                    "birthday_month": profile.birthday_month,
                    "birthday_year": profile.birthday_year,
                    "contactpoint": {"sensitive_string_value": contact},
                    "contactpoint_type": cp_type,
                    "custom_gender": "",
                    "did_use_age": False,
                    "firstname": {"sensitive_string_value": profile.first_name},
                    "fullname": {"sensitive_string_value": ""},
                    "ig_age_block_data": None,
                    "lastname": {"sensitive_string_value": profile.last_name},
                    "preferred_pronoun": None,
                    "reg_passwd__": {"sensitive_string_value": enc},
                    "sex": "FEMALE" if profile.gender.upper() == "FEMALE" else "MALE",
                    "use_custom_gender": False,
                    "username": {"sensitive_string_value": ""},
                },
                "sk_pipa_consent_given": None,
                "waterfall_id": str(uuid.uuid4()),
            },
            "scale": 1,
        }

        try:
            body = self._gql_body_guest(
                self._next_req(), variables,
                FRIENDLY_REGISTER, DOC_REGISTER,
                qpl="250359044,516759801"
            )
            r = self.client.post(
                self.GRAPHQL_URL, data=body,
                headers=self._gql_headers_guest(FRIENDLY_REGISTER),
                follow_redirects=False,
            )
        except Exception as e:
            return False, f"POST_ERROR:{e}"

        text = r.text or ""
        debug_log("REG-RESP-1", text, limit=3000)

        if r.status_code != 200:
            return False, f"HTTP_{r.status_code}"

        try:
            resp = json.loads(text[9:] if text.startswith("for (;;);") else text)
        except Exception:
            return False, "BAD_JSON"

        node = resp.get("data", {}).get("caa_registration_homepage_submit", {}) or {}
        status = node.get("status", "")
        created_uid = node.get("created_user_id")

        if status == "SUCCESS" and created_uid:
            AppLogger.success(f"Registered - UID {created_uid}")
            return True, text

        if "checkpoint" in text.lower() and CHECKPOINT_282_ID in text:
            return False, "CHECKPOINT_282"

        errs = node.get("errors")
        if isinstance(errs, dict):
            errs = errs.get("creation_errors")
        err = errs or resp.get("errors") or status or "REG_FAILED"
        return False, f"REG_FAILED:{str(err)[:160]}"


class OTPVerifier:
    CONFIRM_URL = f"{FB_WWW_URL}/confirmemail.php?next=undefined"
    GRAPHQL_URL = f"{FB_WWW_URL}/api/graphql/"

    def __init__(self, client: WWWClient, engine: Optional[WWWRegEngine] = None):
        self.client = client
        self.engine = engine
        self._req_counter = 0

        if engine:
            self.lsd = engine.lsd
            self.jazoest = engine.jazoest
            self.rev = engine.rev
            self.hs = engine.hs
            self.hsi = engine.hsi
            self.spin_r = engine.spin_r
            self.s = engine.s
            self.dyn = engine.dyn
            self.csr = engine.csr
            self.hsdp = engine.hsdp
            self.hblp = engine.hblp
            self.sjsp = engine.sjsp
            self.fb_dtsg = getattr(engine, "fb_dtsg", "")
        else:
            self.lsd = ""
            self.jazoest = ""
            self.rev = "1048468692"
            self.hs = "20721.HYP:comet_plat_default_pkg.2.1...0"
            self.hsi = "7689480470427579624"
            self.spin_r = "1048468692"
            self.s = ""
            self.dyn = ""
            self.csr = ""
            self.hsdp = ""
            self.hblp = ""
            self.sjsp = ""
            self.fb_dtsg = ""

        self.spin_t = ""

    def _next_req(self):
        self._req_counter += 1
        n = self._req_counter
        if n < 10:
            return str(n)
        return chr(ord('a') + (n - 10))

    def _headers(self, friendly, extra=None):
        h = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded",
            "origin": "https://www.facebook.com",
            "referer": self.CONFIRM_URL,
            "x-asbd-id": "359341",
            "x-fb-friendly-name": friendly,
            "x-fb-lsd": self.lsd,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }
        if not getattr(self.client, "_anti", False):
            h["user-agent"] = self.client.ua
            h["sec-ch-ua"] = SEC_CH_UA_FULL
            h["sec-ch-ua-mobile"] = "?0"
            h["sec-ch-ua-platform"] = '"Windows"'
            h["sec-ch-ua-platform-version"] = '"19.0.0"'
            h["sec-ch-ua-full-version-list"] = SEC_CH_UA_FULL_VERSION_LIST
            h["sec-ch-ua-model"] = '""'
            h["accept-language"] = "en-US,en;q=0.9"
        if extra:
            h.update(extra)
        return h

    def refresh_fb_dtsg_only(self):
        try:
            r = self.client.get(
                self.CONFIRM_URL,
                headers={
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "upgrade-insecure-requests": "1",
                },
                follow_redirects=True, document=True,
            )
            html = r.text or ""

            m = (re.search(r'name="fb_dtsg"\s+value="([^"]+)"', html) or
                 re.search(r'"DTSGInitialData"\s*,\s*\[\s*\]\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"', html) or
                 re.search(r'"fbdtsg"\s*,\s*\[\s*\]\s*,\s*\{[^}]*"token"\s*:\s*"([^"]+)"', html))
            if m:
                self.fb_dtsg = m.group(1)
            else:
                cj = self.client.get_cookies_dict()
                self.fb_dtsg = cj.get("fb_dtsg", "")

            m_lsd = (re.search(r'name="lsd"\s+value="([^"]+)"', html) or
                     re.search(r'"LSD"\s*,\s*\[\s*\]\s*,\s*\{\s*"token"\s*:\s*"([^"]+)"', html))
            if m_lsd:
                self.lsd = m_lsd.group(1)
                self.jazoest = f"2{sum(ord(c) for c in self.lsd)}"

            m_st = re.search(r'"__spin_t"\s*:\s*(\d+)', html)
            self.spin_t = m_st.group(1) if m_st else str(int(time.time()))
            rev = re.search(r'"server_revision"\s*:\s*(\d+)', html)
            if rev:
                self.rev = rev.group(1)
            m_hsi = re.search(r'"hsi"\s*:\s*"(\d+)"', html)
            if m_hsi:
                self.hsi = m_hsi.group(1)
            m_spin = re.search(r'"__spin_r"\s*:\s*(\d+)', html)
            if m_spin:
                self.spin_r = m_spin.group(1)
            hs_val = re.search(r'"haste_session"\s*:\s*"([^"]+)"', html)
            if hs_val:
                self.hs = hs_val.group(1)
            m_s = re.search(r'"__s"\s*:\s*"([^"]+)"', html)
            if m_s:
                self.s = m_s.group(1)
            m_dyn = re.search(r'"__dyn"\s*:\s*"([^"]+)"', html)
            if m_dyn:
                self.dyn = m_dyn.group(1)
            m_csr = re.search(r'"__csr"\s*:\s*"([^"]+)"', html)
            if m_csr:
                self.csr = m_csr.group(1)
            m_hsdp = re.search(r'"__hsdp"\s*:\s*"([^"]+)"', html)
            if m_hsdp:
                self.hsdp = m_hsdp.group(1)
            m_hblp = re.search(r'"__hblp"\s*:\s*"([^"]+)"', html)
            if m_hblp:
                self.hblp = m_hblp.group(1)
            m_sjsp = re.search(r'"__sjsp"\s*:\s*"([^"]+)"', html)
            if m_sjsp:
                self.sjsp = m_sjsp.group(1)

            if self.engine:
                self.engine.lsd = self.lsd
                self.engine.jazoest = self.jazoest
                self.engine.fb_dtsg = self.fb_dtsg
                self.engine.hs = self.hs
                self.engine.hsi = self.hsi
                self.engine.spin_r = self.spin_r
                self.engine.s = self.s
                self.engine.dyn = self.dyn
                self.engine.csr = self.csr
                self.engine.hsdp = self.hsdp
                self.engine.hblp = self.hblp
                self.engine.sjsp = self.sjsp

            return bool(self.lsd and self.fb_dtsg)
        except Exception as e:
            AppLogger.warn(f"refresh_fb_dtsg_only: {e}")
            return False

    def _body_user(self, uid, req, variables, friendly, doc_id, qpl="516759801"):
        self.spin_t = str(int(time.time()))
        return {
            "av": str(uid), "__user": str(uid), "__a": "1", "__req": req,
            "__hs": self.hs, "dpr": "1", "__ccg": "EXCELLENT", "__rev": self.rev,
            "__s": self.s,
            "__hsi": self.hsi,
            "__dyn": self.dyn,
            "__csr": self.csr,
            "__hsdp": self.hsdp,
            "__hblp": self.hblp,
            "__sjsp": self.sjsp,
            "__comet_req": "102",
            "fb_dtsg": self.fb_dtsg,
            "jazoest": self.jazoest,
            "lsd": self.lsd,
            "__spin_r": self.spin_r, "__spin_b": "trunk", "__spin_t": self.spin_t,
            "qpl_active_flow_ids": qpl,
            "fb_api_caller_class": "RelayModern",
            "fb_api_req_friendly_name": friendly,
            "server_timestamps": "true",
            "variables": json.dumps(variables, separators=(",", ":")),
            "doc_id": doc_id,
            "fb_api_analytics_tags": f'["qpl_active_flow_ids={qpl}"]',
        }

    def open_options_dialog(self, uid):
        AppLogger.dialog("[DIALOG] Open CAAConfirmationOptionsDialogQuery")
        try:
            body = self._body_user(
                uid, self._next_req(),
                {"args": {}},
                FRIENDLY_OPTIONS_DIALOG, DOC_OPTIONS_DIALOG,
                qpl="516759801",
            )
            r = self.client.post(
                self.GRAPHQL_URL, data=body,
                headers=self._headers(FRIENDLY_OPTIONS_DIALOG),
                follow_redirects=False,
            )
            text = r.text[9:] if (r.text or "").startswith("for (;;);") else (r.text or "")
            resp = json.loads(text)
            ok = bool(
                resp.get("data", {})
                    .get("caa_registration", {})
                    .get("content", {})
                    .get("confirmation_page", {})
            )
            if ok:
                AppLogger.success("[DIALOG] Options dialog opened")
            return ok
        except Exception as e:
            AppLogger.warn(f"open_options_dialog error: {e}")
            return False

    def open_update_cp_dialog(self, uid):
        AppLogger.dialog("[DIALOG] Open CAAFBConfirmationUpdateCPDialogQuery")
        try:
            body = self._body_user(
                uid, self._next_req(),
                {"args": {}},
                FRIENDLY_UPDATE_CP_DIALOG, DOC_UPDATE_CP_DIALOG,
                qpl="516759801",
            )
            r = self.client.post(
                self.GRAPHQL_URL, data=body,
                headers=self._headers(FRIENDLY_UPDATE_CP_DIALOG),
                follow_redirects=False,
            )
            text = r.text[9:] if (r.text or "").startswith("for (;;);") else (r.text or "")
            resp = json.loads(text)
            ok = bool(
                resp.get("data", {})
                    .get("caa_registration", {})
                    .get("content", {})
                    .get("confirmation_page", {})
            )
            if ok:
                AppLogger.success("[DIALOG] Update CP dialog opened")
            return ok
        except Exception as e:
            AppLogger.warn(f"open_update_cp_dialog error: {e}")
            return False

    def add_contact_point(self, uid, new_contact):
        if not self.fb_dtsg or not self.lsd:
            AppLogger.info("[ADD-CP] Missing tokens - refresh first")
            self.refresh_fb_dtsg_only()
            time.sleep(random.uniform(0.5, 1.0))

        AppLogger.step(6, "Add contact point", f"{new_contact}")

        def _do_add():
            self.open_options_dialog(uid)
            time.sleep(random.uniform(1.2, 2.4))
            self.open_update_cp_dialog(uid)
            time.sleep(random.uniform(1.8, 3.2))

            variables = {
                "input": {
                    "actor_id": str(uid),
                    "client_mutation_id": str(uuid.uuid4()),
                    "contact_point": new_contact,
                    "machine_id": "",
                },
                "scale": 1,
            }
            body = self._body_user(
                uid, self._next_req(),
                variables,
                FRIENDLY_ADD_CONTACT, DOC_ADD_CONTACT,
                qpl="516759801",
            )
            return self.client.post(
                self.GRAPHQL_URL, data=body,
                headers=self._headers(FRIENDLY_ADD_CONTACT),
                follow_redirects=False,
            )

        try:
            r = _do_add()
            if r.status_code != 200:
                AppLogger.warn(f"Add contact HTTP {r.status_code}")
                return False
            text = r.text[9:] if r.text.startswith("for (;;);") else r.text
            resp = json.loads(text)

            errors = resp.get("errors")
            if errors:
                msg = errors[0].get("message", "") if isinstance(errors, list) else str(errors)
                msg_lower = str(msg).lower()
                is_token_error = any(k in msg_lower for k in (
                    "field_exception", "server error", "csrf",
                    "invalid lsd", "invalid token", "unauthorized",
                    "not logged in", "session",
                ))
                if is_token_error:
                    AppLogger.warn("[ADD-CP] Token error detected - refreshing & retrying once")
                    time.sleep(random.uniform(1.5, 2.5))
                    if not self.refresh_fb_dtsg_only():
                        return False
                    time.sleep(random.uniform(0.5, 1.0))
                    try:
                        r2 = _do_add()
                        if r2.status_code == 200:
                            text2 = r2.text[9:] if r2.text.startswith("for (;;);") else r2.text
                            resp2 = json.loads(text2)
                            node2 = resp2.get("data", {}).get("xfb_caa_registration_add_contactpoint") or {}
                            cp2 = node2.get("contact_point")
                            if cp2:
                                cp_clean = str(cp2).replace("\\u0040", "@")
                                AppLogger.success(f"Add contact OK - {cp_clean} (after refresh)")
                                time.sleep(random.uniform(1.0, 2.0))
                                return True
                    except Exception as _e:
                        AppLogger.warn(f"[ADD-CP] retry error: {_e}")
                AppLogger.warn(f"Add contact fail: {text[:200]}")
                return False

            node = resp.get("data", {}).get("xfb_caa_registration_add_contactpoint") or {}
            cp = node.get("contact_point")
            if cp:
                cp_clean = str(cp).replace("\\u0040", "@")
                AppLogger.success(f"Add contact OK - {cp_clean}")
                time.sleep(random.uniform(1.0, 2.0))
                return True
            AppLogger.warn(f"Add contact fail: {text[:200]}")
            return False
        except Exception as e:
            AppLogger.warn(f"add_contact_point error: {e}")
            return False

    def verify_otp(self, otp: str, uid: str) -> Tuple[bool, str]:
        if not self.fb_dtsg or not self.lsd:
            AppLogger.info("[OTP] Missing tokens - refresh first")
            self.refresh_fb_dtsg_only()
            time.sleep(random.uniform(0.5, 1.0))

        AppLogger.step(9, "Verify OTP", f"{otp}")

        def _do_verify():
            variables = {
                "input": {
                    "actor_id": str(uid),
                    "client_mutation_id": str(uuid.uuid4()),
                    "conf_code": {"sensitive_string_value": str(otp)},
                    "ig_reg_data": None,
                    "machine_id": None,
                }
            }
            body = self._body_user(
                uid, self._next_req(),
                variables,
                FRIENDLY_VERIFY, DOC_VERIFY,
                qpl="250360002,516759801",
            )
            return self.client.post(
                self.GRAPHQL_URL, data=body,
                headers=self._headers(FRIENDLY_VERIFY),
                follow_redirects=False,
            )

        try:
            r = _do_verify()
            debug_log("OTP-RESP", (r.text or "")[:800])
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"
            text = r.text[9:] if r.text.startswith("for (;;);") else r.text
            resp = json.loads(text)
            ext = resp.get("extensions", {}) or {}
            errors = resp.get("errors")
            txt_lower = json.dumps(resp, ensure_ascii=False).lower()

            if "3252001" in txt_lower or "temporarily blocked" in txt_lower or \
               "misused this feature" in txt_lower:
                return True, "soft_block_success"

            if errors:
                msg = errors[0].get("message", "") if isinstance(errors, list) else str(errors)
                msg_lower = str(msg).lower()

                token_error_keywords = (
                    "field_exception",
                    "server error",
                    "csrf",
                    "invalid lsd",
                    "invalid token",
                    "unauthorized",
                    "not logged in",
                    "session",
                )
                is_token_error = any(k in msg_lower for k in token_error_keywords)

                if is_token_error:
                    AppLogger.warn("[OTP] Token error detected - refreshing & retrying once")
                    time.sleep(random.uniform(1.5, 2.5))

                    if not self.refresh_fb_dtsg_only():
                        return False, f"graphql_error:{str(msg)[:120]} (refresh failed)"

                    time.sleep(random.uniform(0.5, 1.0))

                    try:
                        r2 = _do_verify()
                        if r2.status_code == 200:
                            text2 = r2.text[9:] if r2.text.startswith("for (;;);") else r2.text
                            resp2 = json.loads(text2)
                            ext2 = resp2.get("extensions", {}) or {}
                            errs2 = resp2.get("errors")
                            txt2_lower = json.dumps(resp2, ensure_ascii=False).lower()

                            if "3252001" in txt2_lower or "temporarily blocked" in txt2_lower or \
                               "misused this feature" in txt2_lower:
                                return True, "soft_block_success_after_retry"

                            if not errs2:
                                if ext2.get("is_final") is True:
                                    return True, "success_after_retry"
                                node2 = resp2.get("data", {}).get("xfb_caa_registration_confirmation_submit", {}) or {}
                                if node2.get("user_id") or node2.get("created_user_id") or \
                                   "xfb_caa_registration_confirmation_submit" in resp2.get("data", {}):
                                    return True, "success_after_retry"
                            else:
                                msg2 = errs2[0].get("message", "") if isinstance(errs2, list) else str(errs2)
                                return False, f"graphql_error_retry:{str(msg2)[:120]}"
                    except Exception as _e:
                        AppLogger.warn(f"[OTP] retry error: {_e}")

                return False, f"graphql_error:{str(msg)[:120]}"

            if ext.get("is_final") is True:
                return True, "success"

            node = resp.get("data", {}).get("xfb_caa_registration_confirmation_submit", {}) or {}
            if node.get("user_id") or node.get("created_user_id"):
                return True, "success"
            if "xfb_caa_registration_confirmation_submit" in resp.get("data", {}):
                return True, "success"
            return False, "otp_rejected"
        except Exception as e:
            return False, f"exception:{e}"

    def resend_otp(self, uid: str) -> bool:
        if not self.fb_dtsg or not self.lsd:
            AppLogger.info("[RESEND] Missing tokens - refresh first")
            self.refresh_fb_dtsg_only()
            time.sleep(random.uniform(0.5, 1.0))

        def _do_resend():
            self.open_options_dialog(uid)
            time.sleep(random.uniform(1.2, 2.4))

            variables = {
                "input": {
                    "actor_id": str(uid),
                    "client_mutation_id": str(uuid.uuid4()),
                    "machine_id": "",
                }
            }
            body = self._body_user(
                uid, self._next_req(),
                variables,
                FRIENDLY_RESEND, DOC_RESEND,
                qpl="516759801",
            )
            return self.client.post(
                self.GRAPHQL_URL, data=body,
                headers=self._headers(FRIENDLY_RESEND),
                follow_redirects=False,
            )

        try:
            r = _do_resend()
            debug_log("RESEND-RESP", (r.text or "")[:600])
            if r.status_code != 200:
                return False
            text = r.text[9:] if r.text.startswith("for (;;);") else r.text
            resp = json.loads(text)

            errors = resp.get("errors")
            if errors:
                msg = errors[0].get("message", "") if isinstance(errors, list) else str(errors)
                msg_lower = str(msg).lower()
                is_token_error = any(k in msg_lower for k in (
                    "field_exception", "server error", "csrf",
                    "invalid lsd", "invalid token", "unauthorized",
                    "not logged in", "session",
                ))
                if is_token_error:
                    AppLogger.warn("[RESEND] Token error detected - refreshing & retrying once")
                    time.sleep(random.uniform(1.5, 2.5))
                    if not self.refresh_fb_dtsg_only():
                        return False
                    time.sleep(random.uniform(0.5, 1.0))
                    try:
                        r2 = _do_resend()
                        if r2.status_code == 200:
                            text2 = r2.text[9:] if r2.text.startswith("for (;;);") else r2.text
                            resp2 = json.loads(text2)
                            ok2 = resp2.get("data", {}).get("caa_registration_resend_conf_code", {}).get("success") is True
                            if ok2:
                                AppLogger.success("[RESEND] OK (after refresh)")
                                time.sleep(random.uniform(0.8, 1.6))
                            return ok2
                    except Exception as _e:
                        AppLogger.warn(f"[RESEND] retry error: {_e}")
                return False

            ok = resp.get("data", {}).get("caa_registration_resend_conf_code", {}).get("success") is True
            if ok:
                AppLogger.success("[RESEND] OK")
                time.sleep(random.uniform(0.8, 1.6))
            return ok
        except Exception as e:
            AppLogger.warn(f"resend error: {e}")
            return False


class LiveChecker:
    @staticmethod
    def is_live(uid, proxy=None) -> bool:
        uid = str(uid or "").strip()
        if not uid:
            return False
        try:
            url = f"https://graph.facebook.com/{uid}/picture"
            params = {"redirect": "false"}
            headers = {"user-agent": USER_AGENT_DESKTOP}
            px = {"http": proxy, "https": proxy} if proxy else None

            if HAS_CURL_CFFI:
                imp = random.choice(IMPERSONATE_POOL) if IMPERSONATE_POOL else "chrome120"
                r = curl_requests.get(url, params=params, headers=headers,
                                      proxies=px, timeout=20, verify=False,
                                      impersonate=imp)
            else:
                r = requests.get(url, params=params, headers=headers,
                                 proxies=px, timeout=20, verify=False)
            debug_log("LIVE-CHECK", (r.text or "")[:400])

            if r.status_code != 200:
                return False

            try:
                resp = r.json()
            except Exception:
                return False

            if "error" in resp:
                return False

            data = resp.get("data", {}) or {}
            has_size = ("height" in data) and ("width" in data)
            return bool(has_size)
        except Exception as e:
            debug_log("LIVE-CHECK-ERR", str(e))
            return False


class BackgroundLiveMonitor:
    def __init__(self, uid, proxy=None, interval=3):
        self.uid = str(uid or "0")
        self.proxy = proxy
        self.interval = interval
        self._stop = threading.Event()
        self._thread = None
        self.last_result = None
        self.dead = False

    def _loop(self):
        first = True
        while not self._stop.is_set():
            try:
                live = LiveChecker.is_live(uid=self.uid, proxy=self.proxy)
                self.last_result = live
                if not live:
                    self.dead = True
                    AppLogger.warn(f"[LIVE-MONITOR] UID {self.uid} appears DEAD")
                    return
            except Exception as e:
                debug_log("LIVE-MONITOR-ERR", str(e))
            self._stop.wait(1.0 if first else self.interval)
            first = False

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.dead = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread.is_alive():
            try:
                self._thread.join(timeout=2)
            except Exception:
                pass

    def is_dead(self):
        return self.dead


def _parse_proxy_fb4a(p):
    if not p:
        return None
    p = str(p).strip()
    if p.startswith(("http://", "https://", "socks5://")):
        return {"http": p, "https": p}
    if "@" in p:
        return {"http": f"http://{p}", "https": f"http://{p}"}
    parts = p.split(":")
    if len(parts) == 4:
        ip, port, user, pwd = parts
        fmt = f"http://{user}:{pwd}@{ip}:{port}"
        return {"http": fmt, "https": fmt}
    if len(parts) == 2:
        return {"http": f"http://{p}", "https": f"http://{p}"}
    return {"http": f"http://{p}", "https": f"http://{p}"}


class FacebookPasswordEncryptor:
    @staticmethod
    def get_public_key(proxy=None):
        url = "https://b-graph.facebook.com/pwd_key_fetch"
        params = {
            "version": "2", "flow": "CONTROLLER_INITIALIZATION", "method": "GET",
            "fb_api_req_friendly_name": "pwdKeyFetch",
            "fb_api_caller_class": "com.facebook.auth.login.AuthOperations",
            "access_token": "350685531728|62f8ce9f74b12f84c123cc23437a4a32",
        }
        headers = {"User-Agent": "okhttp/5.1.0", "Accept": "application/json",
                   "Accept-Encoding": "gzip", "content-length": "0"}
        r = requests.post(url, params=params, headers=headers,
                          proxies=_parse_proxy_fb4a(proxy), timeout=15, verify=False)
        resp = r.json()
        pub_key = resp.get("public_key")
        key_id = str(resp.get("key_id", "25"))
        server_ts = time.time()
        try:
            dh = r.headers.get("Date")
            if dh:
                server_ts = email.utils.parsedate_to_datetime(dh).timestamp()
        except Exception:
            pass
        if not pub_key:
            raise Exception(f"No public key: {resp}")
        return pub_key, key_id, server_ts

    @staticmethod
    def encrypt(password, proxy=None):
        if not HAS_CRYPTODOME:
            raise Exception("pycryptodome not installed")
        public_key, key_id, server_ts = FacebookPasswordEncryptor.get_public_key(proxy)
        rand_key = get_random_bytes(32)
        iv = get_random_bytes(12)
        pubkey = RSA.import_key(public_key)
        encrypted_rand_key = PKCS1_v1_5.new(pubkey).encrypt(rand_key)
        cipher_aes = AES.new(rand_key, AES.MODE_GCM, nonce=iv)
        current_time = int(server_ts)
        cipher_aes.update(str(current_time).encode())
        (enc_passwd, auth_tag) = cipher_aes.encrypt_and_digest(password.encode())
        buf = io.BytesIO()
        buf.write(bytes([1, int(key_id)]))
        buf.write(iv)
        buf.write(struct.pack("<h", len(encrypted_rand_key)))
        buf.write(encrypted_rand_key)
        buf.write(auth_tag)
        buf.write(enc_passwd)
        return f"#PWD_FB4A:2:{current_time}:{base64.b64encode(buf.getvalue()).decode()}", server_ts


class FacebookLogin:
    GQL_URL = "https://b-graph.facebook.com/graphql"
    ACCESS_TOKEN = "350685531728|62f8ce9f74b12f84c123cc23437a4a32"
    BLOKS_VERSION = "3469837656910fc29c9aa968ab33845cd52eb5253ae110610b944c8e9028d8f6"
    CLIENT_DOC_ID = "119940804214876861379510865434"
    ATTESTATION_SIG = "MEQCIDHrmQ86yvC7yeVBi0eYpIr2cnhtaSWxYm8I ZcZ081fAiBLzhHez6CMvaQqaFrCvfCMYker7WNLiQ4L99JpVR9K Q=="
    ATTESTATION_KEY = "9c620c1c59a053c07d9ce2f1166b1385e359254b6c461b3b55ca256d75e0976e"
    FB4A_UA = "[FBAN/FB4A;FBAV/542.0.0.46.151;FBBV/840338789;FBDM/{density=0.75,width=300,height=540};FBLC/vi_VN;FBRV/0;FBCR/MobiFone;FBMF/MTool-Max;FBBD/MTool-Max;FBPN/com.facebook.katana;FBDV/MTool-Max;FBSV/9;FBOP/1;FBCA/x86_64:arm64-v8a;]"

    def __init__(self, uid_phone_mail, password, twofa_secret=None, machine_id=None, proxy=None):
        self.uid = str(uid_phone_mail).strip()
        self.twofa_secret = re.sub(r"[\s\-]+", "", str(twofa_secret or "")).upper()
        self.proxy = proxy
        self.px = _parse_proxy_fb4a(proxy)
        self.server_time_offset = 0.0
        if password.startswith("#PWD_FB4A"):
            self.password = password
        else:
            self.password, ts = FacebookPasswordEncryptor.encrypt(password, proxy=proxy)
            self.server_time_offset = ts - time.time()
        self.session = requests.Session()
        self.session.verify = False
        self.device_id = str(uuid.uuid4())
        self.secure_family_device_id = str(uuid.uuid4())
        self.waterfall_id = str(uuid.uuid4())
        self.infra_flow_id = str(uuid.uuid4())
        self.client_trace_id = str(uuid.uuid4())
        self.machine_id = machine_id or ""

    def _gql_headers(self):
        return {
            "User-Agent": self.FB4A_UA,
            "Accept": "application/json, text/json, text/x-json, text/javascript, application/xml, text/xml",
            "Accept-Encoding": "gzip",
            "x-fb-connection-type": "WIFI",
            "x-fb-http-engine": "Tigon/Liger",
            "x-fb-client-ip": "True",
            "x-fb-server-cluster": "True",
            "x-tigon-is-retry": "False",
            "x-fb-device-group": "5427",
            "x-graphql-request-purpose": "fetch",
            "x-fb-privacy-context": "3643298472347298",
            "x-graphql-client-library": "graphservice",
            "x-fb-net-hni": "45201",
            "x-fb-sim-hni": "45201",
            "authorization": f"OAuth {self.ACCESS_TOKEN}",
        }

    def _attest(self):
        nonce = base64.b64encode(get_random_bytes(32)).decode()
        dj = json.dumps({"challenge_nonce": nonce, "username": self.uid})
        return {"data": base64.b64encode(dj.encode()).decode(),
                "signature": self.ATTESTATION_SIG, "keyHash": self.ATTESTATION_KEY}

    def _client_params(self):
        return {
            "password": self.password,
            "device_id": self.device_id, "family_device_id": self.device_id,
            "contact_point": self.uid, "login_attempt_count": 1,
            "event_flow": "login_manual",
            "sim_phones": [], "secure_family_device_id": self.secure_family_device_id,
            "attestation_result": self._attest(),
            "auth_secure_device_id": "",
            "has_whatsapp_installed": 0, "sso_token_map_json_string": "",
            "password_contains_non_ascii": "false",
            "sim_serials": [], "client_known_key_hash": "",
            "encrypted_msisdn": "", "should_show_nested_nta_from_aymh": 0,
            "machine_id": self.machine_id,
            "flash_call_permission_status": {"READ_PHONE_STATE": "DENIED",
                                             "READ_CALL_LOG": "DENIED",
                                             "ANSWER_PHONE_CALLS": "DENIED"},
            "accounts_list": [], "fb_ig_device_id": [], "device_emails": [],
            "try_num": 1,
            "lois_settings": {"lois_token": "", "lara_override": ""},
            "event_step": "home_page", "headers_infra_flow_id": self.infra_flow_id,
            "openid_tokens": {},
        }

    def _server_params(self):
        return {
            "should_trigger_override_login_2fa_action": 0,
            "is_from_logged_out": 0,
            "should_trigger_override_login_success_action": 0,
            "login_credential_type": "none",
            "server_login_source": "login",
            "waterfall_id": self.waterfall_id, "login_source": "Login",
            "is_platform_login": 0, "pw_encryption_try_count": 1,
            "INTERNAL__latency_qpl_marker_id": 36707139,
            "offline_experiment_group": "caa_iteration_v6_perf_fb_2",
            "is_from_landing_page": 0, "password_text_input_id": "nmi7ws:95",
            "is_from_empty_password": 0, "ar_event_source": "login_home_page",
            "username_text_input_id": "nmi7ws:94",
            "layered_homepage_experiment_group": None,
            "device_id": self.device_id,
            "INTERNAL__latency_qpl_instance_id": random.randint(100000000000000, 999999999999999),
            "reg_flow_source": "login_home_native_integration_point",
            "is_caa_perf_enabled": 1, "credential_type": "password",
            "is_from_password_entry_page": 0, "caller": "gslr",
            "family_device_id": self.device_id, "INTERNAL_INFRA_THEME": "harm_f",
            "is_from_assistive_id": 0, "access_flow_version": "F2_FLOW",
            "is_from_logged_in_switcher": 0,
        }

    def _payload(self):
        inner = json.dumps({"client_input_params": self._client_params(),
                            "server_params": self._server_params()})
        variables = json.dumps({
            "params": {"params": inner, "bloks_versioning_id": self.BLOKS_VERSION,
                       "app_id": "com.bloks.www.bloks.caa.login.async.send_login_request"},
            "scale": "2",
            "nt_context": {"using_white_navbar": True,
                           "styles_id": "964d559c1e2aa0142b5069bc8cb1adea",
                           "pixel_ratio": 2, "is_push_on": True,
                           "debug_tooling_metadata_token": None,
                           "is_flipper_enabled": False, "theme_params": [],
                           "bloks_version": self.BLOKS_VERSION},
        })
        return {
            "method": "post", "pretty": "false", "format": "json",
            "server_timestamps": "true", "locale": "en_US", "purpose": "fetch",
            "fb_api_req_friendly_name": "FbBloksActionRootQuery-com.bloks.www.bloks.caa.login.async.send_login_request",
            "fb_api_caller_class": "graphservice",
            "client_doc_id": self.CLIENT_DOC_ID,
            "variables": variables,
            "fb_api_analytics_tags": '["GraphServices"]',
            "client_trace_id": self.client_trace_id,
            "generate_session_cookies": "1",
        }

    def _extract_token(self, text):
        m = re.search(r'"access_token"\s*:\s*"([^"]+)"', text)
        if not m:
            m = re.search(r"access_token=([^&\"\s]+)", text)
        if not m:
            m = re.search(r"access_token.*?([A-Za-z0-9:_-]{20,})", text)
        return m.group(1) if m else None

    def _cookies_from_token(self, token):
        try:
            r = self.session.post("https://api.facebook.com/method/auth.getSessionforApp",
                                  data={"access_token": token, "format": "json",
                                        "new_app_id": "350685531728",
                                        "generate_session_cookies": "1"},
                                  proxies=self.px, timeout=30, verify=False)
            d = r.json()
            if "error" in d:
                return ""
            cookies = d.get("session_cookies", [])
            if cookies:
                return "; ".join(f"{c['name']}={c['value']}" for c in cookies)
        except Exception:
            pass
        return ""

    def _success(self, token, response_text=""):
        cookies = self._cookies_from_token(token)
        if not cookies:
            cj = self.session.cookies
            if cj:
                cookies = "; ".join([f"{c.name}={c.value}" for c in cj])
        return {"success": True, "access_token": token, "cookies": cookies}

    def login(self):
        try:
            headers = self._gql_headers()
            payload = self._payload()
            r = self.session.post(self.GQL_URL, data=payload, headers=headers,
                                  proxies=self.px, timeout=30, verify=False)
            text = r.text
            debug_log("FB4A-RAW", text, limit=2000)
            token = self._extract_token(text)
            if token:
                return self._success(token, text)
            try:
                d = r.json()
                errs = d.get("errors", [])
                if errs:
                    return {"success": False, "error": errs[0].get("message", "Unknown")}
            except Exception:
                pass
            m = re.search(r'"error_message":"([^"]*)"', text)
            if m:
                return {"success": False, "error": m.group(1)}
            return {"success": False, "error": "No token"}
        except Exception as e:
            return {"success": False, "error": f"Exception: {e}"}


class TokenFetcher:
    @staticmethod
    def fetch(uid, password, twofa_secret=None, proxy=None, max_retry=3):
        if not uid or not password or password.startswith("#PWD_"):
            return None, None
        if not HAS_CRYPTODOME:
            AppLogger.warn("pycryptodome missing")
            return None, None
        for attempt in range(1, max_retry + 1):
            try:
                fb = FacebookLogin(uid_phone_mail=uid, password=password,
                                   twofa_secret=twofa_secret or "", proxy=proxy)
                res = fb.login()
                if res.get("success"):
                    token = res.get("access_token")
                    cookies = res.get("cookies", "")
                    if token:
                        AppLogger.success(f"Token OK - {token[:28]}...")
                        return token, cookies
                else:
                    err = res.get("error", "unknown")
                    AppLogger.warn(f"Token attempt {attempt}: {str(err)[:140]}")
                    if any(k in str(err).lower() for k in ("password", "2fa", "two_step", "incorrect")):
                        break
            except Exception as e:
                AppLogger.warn(f"Token attempt {attempt} exception: {e}")
            time.sleep(random.uniform(2.0, 3.5))
        return None, None


class CookieMediaUploader:
    def __init__(self, uid, cookies, fb_dtsg="", lsd="", jazoest="", proxy=None,
                 avt_source="local", cov_source="local", engine=None, monitor=None):
        self.uid = str(uid or "0")
        self.cookies = cookies if isinstance(cookies, str) else "; ".join(f"{k}={v}" for k, v in cookies.items())
        self.fb_dtsg = fb_dtsg
        self.lsd = lsd
        self.jazoest = jazoest
        self.proxy = proxy
        self.avt_source = avt_source
        self.cov_source = cov_source
        self.engine = engine
        self.monitor = monitor

        self.rev = "1048468692"
        self.hs = "20721.HYP:comet_pkg.2.1...0"
        self.hsi = "7689480470427579624"
        self.spin_r = "1048468692"
        self.spin_b = "trunk"
        self.s = ""
        self.dyn = ""
        self.csr = ""
        self.hsdp = ""
        self.hblp = ""
        self.sjsp = ""

        self._anti_client = None
        if HAS_CURL_CFFI:
            try:
                self._anti_client = WWWClient(proxy=proxy)
            except Exception as e:
                AppLogger.warn(f"AntiDetect upload init fail: {e}")
                self._anti_client = None

    def _is_dead(self):
        try:
            return bool(self.monitor and self.monitor.is_dead())
        except Exception:
            return False

    def _px(self):
        return {"http": self.proxy, "https": self.proxy} if self.proxy else None

    def load_tokens_from_home(self):
        AppLogger.info(f"Load tokens from home page for UID {self.uid}")
        try:
            headers = {
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "accept-language": "en-US,en;q=0.9",
                "referer": "https://www.facebook.com/",
                "cookie": self.cookies,
                "user-agent": USER_AGENT_DESKTOP,
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "none",
                "upgrade-insecure-requests": "1",
                "sec-ch-ua": SEC_CH_UA_FULL,
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-ch-ua-full-version-list": SEC_CH_UA_FULL_VERSION_LIST,
                "sec-ch-ua-model": '""',
                "sec-ch-ua-platform-version": '"19.0.0"',
            }
            if self._anti_client and self._anti_client._anti:
                r = self._anti_client.get(
                    "https://www.facebook.com/",
                    headers=headers, document=True,
                )
            else:
                r = requests.get(
                    "https://www.facebook.com/",
                    headers=headers, proxies=self._px(), timeout=30, verify=False,
                )
            html = r.text or ""
            if len(html) < 5000:
                AppLogger.warn(f"Home page returned short ({len(html)} bytes) - cookie invalid or checkpoint")
                return False

            def _s(pat, default=""):
                m = re.search(pat, html)
                return m.group(1) if m else default

            self.lsd = _s(r'name="lsd"\s+value="([^"]+)"') or _s(r'"LSD",\[\],\{"token":"([^"]+)"\}')
            if self.lsd:
                self.jazoest = f"2{sum(ord(c) for c in self.lsd)}"

            self.fb_dtsg = (
                _s(r'name="fb_dtsg"\s+value="([^"]+)"') or
                _s(r'"DTSGInitialData",\[\],\{"token":"([^"]+)"\}') or
                _s(r'"fbdtsg"\s*,\s*\[\s*\]\s*,\s*\{[^}]*"token"\s*:\s*"([^"]+)"')
            )
            self.rev = _s(r'"(?:__)?rev":(\d+)', self.rev)
            self.hsi = _s(r'"hsi":"(\d+)"', self.hsi)
            self.spin_r = _s(r'"__spin_r":(\d+)', self.spin_r)
            self.s = _s(r'"(?:__)?s":"([^"]+)"')
            self.hs = _s(r'"(?:__)?hs":"([^"]+)"', self.hs)
            self.dyn = _s(r'"(?:__)?dyn":"([^"]+)"')
            self.csr = _s(r'"(?:__)?csr":"([^"]+)"')
            self.hsdp = _s(r'"(?:__)?hsdp":"([^"]+)"')
            self.hblp = _s(r'"(?:__)?hblp":"([^"]+)"')
            self.sjsp = _s(r'"(?:__)?sjsp":"([^"]+)"')

            if not self.lsd or not self.fb_dtsg:
                AppLogger.warn(f"Missing tokens - lsd={bool(self.lsd)} dtsg={bool(self.fb_dtsg)}")
                return False

            AppLogger.token("home-lsd", self.lsd)
            AppLogger.token("home-dtsg", self.fb_dtsg)
            return True
        except Exception as e:
            AppLogger.warn(f"load_tokens_from_home error: {e}")
            return False

    def _headers(self, multipart=False, friendly=None):
        h = {
            "accept": "*/*",
            "accept-language": "en-US,en;q=0.9",
            "origin": "https://www.facebook.com",
            "referer": f"https://www.facebook.com/profile.php?id={self.uid}",
            "user-agent": USER_AGENT_DESKTOP,
            "cookie": self.cookies,
            "x-asbd-id": "359341",
            "x-fb-lsd": self.lsd,
            "sec-ch-ua": SEC_CH_UA_FULL,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua-platform-version": '"19.0.0"',
            "sec-ch-ua-full-version-list": SEC_CH_UA_FULL_VERSION_LIST,
            "sec-ch-ua-model": '""',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
        }
        if not multipart:
            h["content-type"] = "application/x-www-form-urlencoded"
        if friendly:
            h["x-fb-friendly-name"] = friendly
        return h

    @staticmethod
    def _mime(filename):
        ext = filename.rsplit(".", 1)[-1].lower().split("?")[0]
        return {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                "png": "image/png", "gif": "image/gif",
                "webp": "image/webp"}.get(ext, "application/octet-stream")

    @staticmethod
    def _download_url(url, timeout=30):
        try:
            if HAS_CURL_CFFI and IMPERSONATE_POOL:
                imp = random.choice(IMPERSONATE_POOL)
                r = curl_requests.get(url, timeout=timeout, verify=False,
                                      impersonate=imp)
            else:
                r = requests.get(url, timeout=timeout, verify=False)
            if r.status_code == 200 and len(r.content) > 1000:
                return r.content
        except Exception:
            pass
        return None

    def _upload_request(self, url, params, files):
        if self._anti_client and self._anti_client._anti:
            try:
                return self._anti_client.post_multipart(
                    url, params=params, files=files,
                    headers=self._headers(multipart=True),
                )
            except Exception as e:
                AppLogger.warn(f"[UPLOAD] anti fail: {str(e)[:140]} - fallback")
        return requests.post(
            url, params=params, files=files,
            headers=self._headers(multipart=True),
            proxies=self._px(), timeout=60, verify=False,
        )

    def _gql_post(self, url, body, friendly):
        h = self._headers(friendly=friendly)
        if self._anti_client and self._anti_client._anti:
            try:
                h2 = dict(h)
                h2.pop("content-type", None)
                h2["content-type"] = "application/x-www-form-urlencoded"
                return self._anti_client.post(
                    url, data=body, headers=h2, follow_redirects=False,
                )
            except Exception as e:
                AppLogger.warn(f"[GQL] anti fail: {str(e)[:140]} - fallback")
        return requests.post(url, data=body, headers=h,
                             proxies=self._px(), timeout=60, verify=False)

    def upload_avatar_photo(self, img_bytes, filename):
        AppLogger.media(f"[AVATAR] Upload {filename} ({len(img_bytes)}b)")
        params = {
            "photo_source": "57", "profile_id": self.uid, "av": self.uid,
            "__aaid": "0", "__user": self.uid, "__a": "1", "__req": "3e",
            "__hs": self.hs, "dpr": "1", "__ccg": "EXCELLENT",
            "__rev": self.rev, "__s": self.s, "__hsi": self.hsi,
            "__dyn": self.dyn, "__csr": self.csr,
            "__hsdp": self.hsdp, "__hblp": self.hblp, "__sjsp": self.sjsp,
            "__comet_req": "15",
            "fb_dtsg": self.fb_dtsg, "jazoest": self.jazoest, "lsd": self.lsd,
            "__spin_r": self.spin_r, "__spin_b": self.spin_b,
            "__spin_t": str(int(time.time())),
            "__crn": "comet.fbweb.CometProfileTimelineListViewRoute",
        }
        files = {"file": (filename, img_bytes, self._mime(filename))}
        try:
            r = self._upload_request("https://www.facebook.com/profile/picture/upload/",
                                     params, files)
            text = (r.text or "").strip()
            if text.startswith("for (;;);"):
                text = text[9:]
            try:
                j = json.loads(text)
            except Exception:
                AppLogger.warn(f"[AVATAR] bad json: {text[:150]}")
                return None
            payload = j.get("payload") or {}
            fbid = payload.get("fbid") if isinstance(payload, dict) else None
            if not fbid:
                fbid = j.get("fbid") or j.get("id")
            if not fbid:
                if isinstance(j, dict) and j.get("jsmods"):
                    AppLogger.warn("[AVATAR] no fbid - cookie invalid or account checkpointed")
                    debug_log("AVATAR-JSMODS", j.get("jsmods"), limit=800)
                else:
                    AppLogger.warn(f"[AVATAR] no fbid: {text[:250]}")
                return None
            AppLogger.media(f"[AVATAR] Uploaded fbid={fbid}")
            return str(fbid)
        except Exception as e:
            AppLogger.warn(f"[AVATAR] upload err: {e}")
            return None

    def set_avatar(self, photo_id):
        variables = {
            "input": {
                "attribution_id_v2": (
                    "ProfileCometTimelineListViewRoot.react,comet.profile.timeline.list,"
                    f"unexpected,{int(time.time()*1000)},{random.randint(10000,999999)},"
                    "190055527696468,,"
                ),
                "caption": "",
                "existing_photo_id": str(photo_id),
                "expiration_time": None,
                "profile_id": self.uid,
                "profile_pic_method": "EXISTING",
                "profile_pic_source": "TIMELINE",
                "scaled_crop_rect": {"height": 1, "width": 1, "x": 0, "y": 0},
                "skip_cropping": True,
                "actor_id": self.uid,
                "client_mutation_id": "4",
            },
            "isPage": False, "isProfile": True, "scale": 1,
            "__relay_internal__pv__ProfileGeminiIsCoinFlipEnabledrelayprovider": False,
        }
        body = {
            "av": self.uid, "__aaid": "0", "__user": self.uid, "__a": "1",
            "__req": "3g", "__hs": self.hs,
            "dpr": "1", "__ccg": "EXCELLENT", "__rev": self.rev,
            "__s": self.s, "__hsi": self.hsi, "__dyn": self.dyn,
            "__csr": self.csr, "__hsdp": self.hsdp, "__hblp": self.hblp,
            "__sjsp": self.sjsp, "__comet_req": "15",
            "fb_dtsg": self.fb_dtsg, "jazoest": self.jazoest, "lsd": self.lsd,
            "__spin_r": self.spin_r, "__spin_b": self.spin_b,
            "__spin_t": str(int(time.time())),
            "__crn": "comet.fbweb.CometProfileTimelineListViewRoute",
            "fb_api_caller_class": "RelayModern",
            "fb_api_req_friendly_name": FRIENDLY_AVATAR,
            "server_timestamps": "true",
            "variables": json.dumps(variables, separators=(",", ":")),
            "doc_id": DOC_SET_AVATAR,
        }
        try:
            r = self._gql_post("https://www.facebook.com/api/graphql/", body, FRIENDLY_AVATAR)
            text = r.text or ""
            ok = '"profile_picture_set"' in text and '"__typename":"User"' in text
            if ok:
                AppLogger.success("Avatar set OK")
            else:
                AppLogger.warn(f"Avatar set fail: {text[:200]}")
            return ok
        except Exception as e:
            AppLogger.warn(f"Avatar set err: {e}")
            return False

    def upload_cover_photo(self, img_bytes, filename):
        AppLogger.media(f"[COVER] Upload {filename} ({len(img_bytes)}b)")
        params = {
            "profile_id": self.uid, "av": self.uid,
            "__aaid": "0", "__user": self.uid, "__a": "1", "__req": "3p",
            "__hs": self.hs, "dpr": "1", "__ccg": "EXCELLENT",
            "__rev": self.rev, "__s": self.s, "__hsi": self.hsi,
            "__dyn": self.dyn, "__csr": self.csr,
            "__hsdp": self.hsdp, "__hblp": self.hblp, "__sjsp": self.sjsp,
            "__comet_req": "15",
            "fb_dtsg": self.fb_dtsg, "jazoest": self.jazoest, "lsd": self.lsd,
            "__spin_r": self.spin_r, "__spin_b": self.spin_b,
            "__spin_t": str(int(time.time())),
            "__crn": "comet.fbweb.CometProfileTimelineListViewRoute",
        }
        files = {"file": (filename, img_bytes, self._mime(filename))}
        try:
            r = self._upload_request("https://www.facebook.com/profile/cover/comet_upload/",
                                     params, files)
            text = (r.text or "").strip()
            if text.startswith("for (;;);"):
                text = text[9:]
            try:
                j = json.loads(text)
            except Exception:
                AppLogger.warn(f"[COVER] bad json: {text[:150]}")
                return None
            payload = j.get("payload") or {}
            fbid = payload.get("fbid") if isinstance(payload, dict) else None
            if not fbid:
                fbid = j.get("fbid") or j.get("id") or j.get("photo_id")
            if not fbid:
                if isinstance(j, dict) and j.get("jsmods"):
                    AppLogger.warn("[COVER] no fbid - cookie invalid or account checkpointed")
                else:
                    AppLogger.warn(f"[COVER] no fbid: {text[:250]}")
                return None
            AppLogger.media(f"[COVER] Uploaded fbid={fbid}")
            return str(fbid)
        except Exception as e:
            AppLogger.warn(f"[COVER] upload err: {e}")
            return None

    def set_cover(self, photo_id):
        variables = {
            "input": {
                "attribution_id_v2": (
                    "ProfileCometTimelineListViewRoot.react,comet.profile.timeline.list,"
                    f"unexpected,{int(time.time()*1000)},{random.randint(10000,999999)},"
                    "190055527696468,,"
                ),
                "cover_photo_id": str(photo_id),
                "focus": {"x": 0.5, "y": 0.5},
                "target_user_id": self.uid,
                "actor_id": self.uid,
                "client_mutation_id": "5",
            },
            "scale": 1, "contextualProfileContext": None,
        }
        body = {
            "av": self.uid, "__aaid": "0", "__user": self.uid, "__a": "1",
            "__req": "3u", "__hs": self.hs,
            "dpr": "1", "__ccg": "EXCELLENT", "__rev": self.rev,
            "__s": self.s, "__hsi": self.hsi, "__dyn": self.dyn,
            "__csr": self.csr, "__hsdp": self.hsdp, "__hblp": self.hblp,
            "__sjsp": self.sjsp, "__comet_req": "15",
            "fb_dtsg": self.fb_dtsg, "jazoest": self.jazoest, "lsd": self.lsd,
            "__spin_r": self.spin_r, "__spin_b": self.spin_b,
            "__spin_t": str(int(time.time())),
            "__crn": "comet.fbweb.CometProfileTimelineListViewRoute",
            "fb_api_caller_class": "RelayModern",
            "fb_api_req_friendly_name": FRIENDLY_COVER,
            "server_timestamps": "true",
            "variables": json.dumps(variables, separators=(",", ":")),
            "doc_id": DOC_SET_COVER,
        }
        try:
            r = self._gql_post("https://www.facebook.com/api/graphql/", body, FRIENDLY_COVER)
            text = r.text or ""
            ok = '"user_update_cover_photo"' in text and '"cover_photo"' in text
            if ok:
                AppLogger.success("Cover set OK")
            else:
                AppLogger.warn(f"Cover set fail: {text[:200]}")
            return ok
        except Exception as e:
            AppLogger.warn(f"Cover set err: {e}")
            return False

    AVT_DIR = "Avatar"
    COVER_DIR = "Cover"
    IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp")

    @classmethod
    def _pick_local(cls, folder):
        if not os.path.isdir(folder):
            return None
        files = sorted(os.path.join(folder, f) for f in os.listdir(folder)
                       if f.lower().endswith(cls.IMAGE_EXTS))
        return random.choice(files) if files else None

    @classmethod
    def _read(cls, path):
        try:
            with open(path, "rb") as fh:
                return fh.read()
        except Exception:
            return None

    def _resolve(self, kind):
        src = self.avt_source if kind == "avatar" else self.cov_source
        if src == "link":
            url = random.choice(AVATAR_GIRL_IMAGES if kind == "avatar" else COVER_IMAGES)
            AppLogger.media(f"[{kind.upper()}] link <- {url[:60]}...")
            data = self._download_url(url)
            return data, ("avatar.jpg" if kind == "avatar" else "cover.jpg")
        folder = self.AVT_DIR if kind == "avatar" else self.COVER_DIR
        path = self._pick_local(folder)
        if not path:
            AppLogger.warn(f"[{kind.upper()}] no file in {folder}/")
            return None, None
        AppLogger.media(f"[{kind.upper()}] local <- {os.path.basename(path)}")
        return self._read(path), os.path.basename(path)

    def run_avatar(self):
        if self._is_dead():
            AppLogger.warn("[AVATAR] Account DEAD - skip")
            return False
        AppLogger.step(10, "Upload avatar", f"source={self.avt_source}")
        data, name = self._resolve("avatar")
        if not data:
            AppLogger.warn("Avatar: no image")
            return False
        fbid = self.upload_avatar_photo(data, name)
        if not fbid:
            return False
        if self._is_dead():
            AppLogger.warn("[AVATAR] Account DEAD after upload - skip set")
            return False
        time.sleep(random.uniform(1.0, 2.0))
        return self.set_avatar(fbid)

    def run_cover(self):
        if self._is_dead():
            AppLogger.warn("[COVER] Account DEAD - skip")
            return False
        AppLogger.step(11, "Upload cover", f"source={self.cov_source}")
        data, name = self._resolve("cover")
        if not data:
            AppLogger.warn("Cover: no image")
            return False
        fbid = self.upload_cover_photo(data, name)
        if not fbid:
            return False
        if self._is_dead():
            AppLogger.warn("[COVER] Account DEAD after upload - skip set")
            return False
        time.sleep(random.uniform(1.0, 2.0))
        return self.set_cover(fbid)


class OTPRegexParser:
    PATTERNS = [
        r'(?:code|confirmation|is|FB-)\s*[:#\-]?\s*<b>?(\d{5,8})',
        r'\bFB-(\d{5,6})\b',
        r'\b(\d{5,6})\b',
    ]

    @classmethod
    def extract(cls, text):
        if not text:
            return None
        for p in cls.PATTERNS:
            m = re.search(p, text, re.IGNORECASE)
            if m:
                return m.group(1)
        return None


class ServerMailZy:
    def __init__(self, api_key=ZYMAIL_DEFAULT_KEY, base_url=ZYMAIL_BASE):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
        }
        self.token = None
        self.email = None
        self.name = None
        self.domain = None
        self.session = requests.Session()
        try:
            from urllib3.util import Retry
            from requests.adapters import HTTPAdapter
            retries = Retry(total=3, backoff_factor=0.5,
                            status_forcelist=[502, 503, 504],
                            raise_on_status=False)
            adapter = HTTPAdapter(max_retries=retries)
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)
        except Exception:
            pass

    def release(self):
        try:
            res = self.session.post(
                f"{self.base_url}/tra",
                headers=self.headers,
                json={},
                timeout=(5, 45),
            )
            if res.status_code == 200:
                data = res.json()
                self.token = None
                self.email = None
                return data.get("status") == "success"
            elif res.status_code in (400, 404):
                self.token = None
                self.email = None
                return True
        except Exception as e:
            AppLogger.warn(f"[ZyMail] /tra error: {e}")
        return False

    def _parse_rent_response(self, data):
        if not isinstance(data, dict):
            return None
        if data.get("status") != "success":
            return None
        d = data.get("data") or {}
        email = d.get("email")
        if not email or "@" not in email:
            return None
        return {
            "email": str(email),
            "name": d.get("name"),
            "token": str(d.get("token") or email),
            "domain": d.get("domain"),
        }

    def get_email(self):
        for attempt in range(3):
            try:
                res = self.session.post(
                    f"{self.base_url}/thue",
                    headers=self.headers,
                    json={},
                    timeout=(5, 75),
                )
                try:
                    data = res.json()
                except Exception:
                    data = {}

                parsed = self._parse_rent_response(data)
                if parsed:
                    self.email = parsed["email"]
                    self.name = parsed["name"]
                    self.token = parsed["token"]
                    self.domain = parsed["domain"]
                    if self.name:
                        AppLogger.info(f"[ZyMail] Owner: {self.name}")
                    return self.email, self.token

                msg = str(data.get("message", "")) if isinstance(data, dict) else ""
                if "đang thuê mail" in msg or "Hãy trả mail trước" in msg or \
                   "chưa trả" in msg.lower() or "mail" in msg.lower():
                    AppLogger.warn("[ZyMail] Mail locked - releasing and retrying")
                    self.release()
                    time.sleep(1)
                    continue

                AppLogger.warn(f"[ZyMail] /thue HTTP {res.status_code}: {msg[:120]}")
            except requests.exceptions.Timeout:
                AppLogger.warn("[ZyMail] /thue timeout - retry")
                self.release()
            except Exception as e:
                AppLogger.warn(f"[ZyMail] get_email error: {e}")
            time.sleep(1.5)
        return None, None

    def rent_again(self, token):
        if not token:
            return False
        try:
            res = self.session.post(
                f"{self.base_url}/thuelai",
                headers=self.headers,
                json={"token": str(token)},
                timeout=(5, 45),
            )
            try:
                data = res.json()
            except Exception:
                return False
            parsed = self._parse_rent_response(data)
            if parsed:
                self.email = parsed["email"]
                self.name = parsed["name"]
                self.token = parsed["token"]
                self.domain = parsed["domain"]
                AppLogger.info(f"[ZyMail] Re-rented: {self.email}")
                return True
            return False
        except Exception as e:
            AppLogger.warn(f"[ZyMail] thuelai error: {e}")
            return False

    def _extract_otp(self, msg):
        if not isinstance(msg, dict):
            return None
        otp = msg.get("otp")
        if otp:
            return str(otp).strip()
        combined = " ".join([
            str(msg.get("subject", "")),
            str(msg.get("snippet", "")),
            str(msg.get("body", "")),
            str(msg.get("text", "")),
            str(msg.get("html", "")),
        ])
        return OTPRegexParser.extract(combined)

    def get_otp(self, email, order_id=None, timeout=120, interval=3.0, token=None):
        token_to_use = token or order_id or self.token
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                payload = {}
                if token_to_use:
                    payload["token"] = token_to_use
                res = self.session.post(
                    f"{self.base_url}/doc",
                    headers=self.headers,
                    json=payload,
                    timeout=(5, 50),
                )
                if res.status_code == 200:
                    data = res.json()
                    if data.get("status") == "success" and "data" in data:
                        d = data["data"] or {}
                        messages = d.get("messages") or []
                        for msg in messages:
                            otp = self._extract_otp(msg)
                            if otp:
                                AppLogger.success(f"[ZyMail] OTP: {otp}")
                                return otp
            except requests.exceptions.Timeout:
                pass
            except Exception:
                pass
            time.sleep(interval)
        return None


class TempMailClient:
    _URL = "https://10minutemail.net/?lang=vi"
    _INBOX_URL = "https://10minutemail.net/mailbox.ajax.php?_="

    def __init__(self):
        self.cookies = {}
        self.email = None

    def release(self):
        self.cookies = {}
        self.email = None
        return True

    def get_email(self, max_attempts=10):
        headers = {"User-Agent": USER_AGENT_DESKTOP}
        for attempt in range(max_attempts):
            try:
                s = requests.Session()
                s.verify = False
                r = s.get(self._URL, headers=headers, timeout=15)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "html.parser")
                    inp = soup.find("input", {"id": "fe_text"})
                    if inp and inp.get("value"):
                        email = inp["value"]
                        self.email = email
                        self.cookies = s.cookies.get_dict()
                        return email, email
                else:
                    AppLogger.warn(f"[10min] HTTP {r.status_code}")
            except Exception as e:
                AppLogger.warn(f"[10min] get_email attempt {attempt + 1}: {e}")
            time.sleep(random.uniform(3, 7))
        AppLogger.error(f"[10min] Cannot get email after {max_attempts} attempts")
        return None, None

    def get_otp(self, email, order_id=None, timeout=120, interval=3.0, token=None):
        if not self.cookies:
            AppLogger.warn("[10min] No cookies - cannot poll")
            return None

        headers = {"User-Agent": USER_AGENT_DESKTOP}
        s = requests.Session()
        s.verify = False
        s.cookies.update(self.cookies)

        start = time.time()
        while time.time() - start < timeout:
            try:
                r = s.get(self._INBOX_URL, headers=headers, timeout=10)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "html.parser")
                    for mail in soup.find_all("tr", style="font-weight: bold; cursor: pointer;"):
                        sender = mail.find("a", class_="row-link")
                        if sender and "facebook" in sender.text.lower():
                            parts = mail.find_all("a", class_="row-link")
                            content = parts[1].text.strip() if len(parts) > 1 else ""
                            code = self._extract_code(content)
                            if code:
                                AppLogger.success(f"[10min] OTP: {code}")
                                return code
            except Exception as e:
                AppLogger.warn(f"[10min] poll error: {e}")
            time.sleep(interval)
        return None

    @staticmethod
    def _extract_code(content):
        patterns = [
            r"FB-(\d{5,6})",
            r"(?:code|mã|OTP)[\s:]*([A-Z0-9]{5,8})",
            r"\b([A-Z]{2}-\d{5,6})\b",
            r"(?:confirmation|verification) code[\s:]*(\d{5,6})",
            r"\b(\d{5,6})\b(?!\d)",
        ]
        for p in patterns:
            m = re.search(p, content, re.IGNORECASE)
            if m:
                code = m.group(1) if m.lastindex else m.group(0)
                if 5 <= len(code) <= 8:
                    return code.upper()
        return None


class DropMailClient:
    def __init__(self, token="af_", base_url=DROPMAIL_BASE):
        self.token = token.strip()
        self.base_url = base_url.rstrip("/")
        self.session_id = None
        self.email = None
        self.last_mail_id = None
        self.session = requests.Session()
        self.session.verify = False

    def _gql(self, query, variables=None, timeout=30):
        url = f"{self.base_url}/{self.token}"
        payload = {"query": query}
        if variables:
            payload["variables"] = json.dumps(variables)
        r = self.session.post(url, data=payload, timeout=timeout)
        try:
            return r.json()
        except Exception:
            return {}

    def release(self):
        self.session_id = None
        self.email = None
        self.last_mail_id = None
        return True

    def get_email(self):
        query = """
        mutation {
            introduceSession {
                id
                expiresAt
                addresses {
                    address
                }
            }
        }
        """
        try:
            resp = self._gql(query)
            data = (resp.get("data") or {}).get("introduceSession") or {}
            session_id = data.get("id")
            addresses = data.get("addresses") or []
            if session_id and addresses:
                email = addresses[0].get("address")
                if email and "@" in email:
                    self.session_id = str(session_id)
                    self.email = str(email)
                    self.last_mail_id = None
                    return self.email, self.session_id
            errs = resp.get("errors")
            if errs:
                AppLogger.warn(f"[DropMail] introduceSession error: {str(errs)[:150]}")
        except Exception as e:
            AppLogger.warn(f"[DropMail] get_email error: {e}")
        return None, None

    def get_otp(self, email, order_id=None, timeout=120, interval=3.0, token=None):
        if not self.session_id:
            AppLogger.warn("[DropMail] No active session")
            return None

        start = time.time()
        while time.time() - start < timeout:
            try:
                query = """
                query ($id: ID!) {
                    session(id: $id) {
                        mails {
                            id
                            rawSize
                            fromAddr
                            toAddr
                            headerSubject
                            text
                        }
                    }
                }
                """
                resp = self._gql(query, {"id": self.session_id})
                errs = resp.get("errors")
                if errs:
                    err_code = ""
                    try:
                        err_code = errs[0].get("extensions", {}).get("code", "")
                    except Exception:
                        pass
                    if err_code == "SESSION_NOT_FOUND":
                        AppLogger.warn("[DropMail] Session expired")
                        return None
                    if err_code == "RATE_LIMIT_EXCEEDED":
                        time.sleep(5)
                        continue
                data = (resp.get("data") or {}).get("session") or {}
                mails = data.get("mails") or []
                for msg in mails:
                    mid = msg.get("id")
                    if mid and mid == self.last_mail_id:
                        continue
                    text = msg.get("text", "") or ""
                    subject = msg.get("headerSubject", "") or ""
                    combined = f"{subject} {text}"
                    otp = OTPRegexParser.extract(combined)
                    if otp:
                        self.last_mail_id = mid
                        AppLogger.success(f"[DropMail] OTP: {otp}")
                        return otp
            except Exception as e:
                AppLogger.warn(f"[DropMail] poll error: {e}")
            time.sleep(interval)
        return None


class Mail1sClient:
    def __init__(self, token=MAIL1S_DEFAULT_TOKEN, base_url=MAIL1S_BASE):
        self.token = token.strip()
        self.base_url = base_url.rstrip("/")
        self.address_id = None
        self.email = None
        self.session = requests.Session()
        self.session.verify = False

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def release(self):
        self.address_id = None
        self.email = None
        return True

    def get_email(self, domain=None, local_part=None):
        domain = domain or random.choice(MAIL1S_DOMAINS)
        body = {"domain": domain}
        if local_part:
            body["localPart"] = local_part
        try:
            r = self.session.post(f"{self.base_url}/addresses",
                                  headers=self._headers(), json=body, timeout=20)
            if r.status_code in (200, 201):
                d = r.json()
                address = d.get("address")
                if address and "@" in address:
                    self.email = str(address)
                    self.address_id = d.get("id")
                    return self.email, self.address_id
            AppLogger.warn(f"[Mail1s] create HTTP {r.status_code}: {(r.text or '')[:150]}")
        except Exception as e:
            AppLogger.warn(f"[Mail1s] create error: {e}")
        return None, None

    def get_otp(self, email, order_id=None, timeout=120, interval=3.0, token=None):
        if not self.email:
            AppLogger.warn("[Mail1s] No active address")
            return None

        start = time.time()
        seen_ids = set()
        while time.time() - start < timeout:
            try:
                url = f"{self.base_url}/addresses/{self.email}/messages"
                r = self.session.get(url, headers=self._headers(),
                                     params={"limit": 20}, timeout=20)
                if r.status_code != 200:
                    time.sleep(interval)
                    continue
                d = r.json()
                messages = d.get("messages") or []
                for msg in messages:
                    mid = msg.get("id")
                    if not mid or mid in seen_ids:
                        continue
                    seen_ids.add(mid)
                    subject = msg.get("subject", "") or ""
                    snippet = msg.get("snippet", "") or ""
                    combined = f"{subject} {snippet}"
                    otp = OTPRegexParser.extract(combined)
                    if not otp:
                        try:
                            r2 = self.session.get(
                                f"{self.base_url}/addresses/{self.email}/messages/{mid}",
                                headers=self._headers(),
                                params={"markRead": 0},
                                timeout=20,
                            )
                            if r2.status_code == 200:
                                d2 = r2.json()
                                text = d2.get("text", "") or ""
                                html = d2.get("html", "") or ""
                                combined2 = f"{subject} {text} {html}"
                                otp = OTPRegexParser.extract(combined2)
                        except Exception:
                            pass
                    if otp:
                        AppLogger.success(f"[Mail1s] OTP: {otp}")
                        return otp
            except Exception as e:
                AppLogger.warn(f"[Mail1s] poll error: {e}")
            time.sleep(interval)
        return None


class OTPTrustEmailClient:
    def __init__(self, api_key, base_url=OTPTRUST_BASE):
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or OTPTRUST_BASE).rstrip("/")
        self.session = requests.Session()
        self.session.verify = False
        self.order_id = None
        self.email = None
        self.service_id = None
        self.provider = None

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _get(self, path, params=None, timeout=30):
        url = f"{self.base_url}{path}"
        try:
            r = self.session.get(url, headers=self._headers(),
                                 params=params, timeout=timeout)
            return r.status_code, r.json()
        except Exception as e:
            AppLogger.warn(f"[OTPTrust] GET {path} error: {e}")
            return 0, {}

    def _post(self, path, body=None, timeout=30):
        url = f"{self.base_url}{path}"
        try:
            r = self.session.post(url, headers=self._headers(),
                                  json=(body or {}), timeout=timeout)
            return r.status_code, r.json()
        except Exception as e:
            AppLogger.warn(f"[OTPTrust] POST {path} error: {e}")
            return 0, {}

    def list_services(self, domain=None):
        params = {}
        if domain:
            params["domain"] = domain
        code, data = self._get("/api/v1/email/services", params=params)
        if code != 200 or not data.get("success"):
            AppLogger.warn(f"[OTPTrust] list_services HTTP {code}")
            return None
        return data.get("data") or []

    def find_service_id(self, service_name="facebook", domain=None):
        services = self.list_services(domain=domain)
        if not services:
            return None, None
        target = service_name.lower().strip()
        for svc in services:
            name = str(svc.get("name", "")).lower().strip()
            code = str(svc.get("service_code", "")).lower().strip()
            if name == target or code == target:
                provider = domain or "hotmail"
                return svc.get("id"), provider
        if services:
            first = services[0]
            provider = domain or "hotmail"
            return first.get("id"), provider
        return None, None

    def rent(self, service_id, provider="hotmail"):
        AppLogger.otpapi(f"[OTPTrust] Rent service_id={service_id} provider={provider}")
        code, data = self._post("/api/v1/email/rent", {
            "service_id": int(service_id),
            "provider": str(provider),
        })
        if code != 200 or not data.get("success"):
            msg = data.get("message") or data.get("error") or f"HTTP {code}"
            AppLogger.warn(f"[OTPTrust] rent failed - {msg}")
            return None
        d = data.get("data") or {}
        self.order_id = d.get("order_id")
        self.email = d.get("email")
        self.service_id = service_id
        self.provider = provider
        if self.email:
            AppLogger.success(
                f"[OTPTrust] Rented {self.email} "
                f"(order={self.order_id} price={d.get('price_vn') or d.get('price_us')})"
            )
            return self.email
        AppLogger.warn("[OTPTrust] rent response missing email")
        return None

    def get_order(self, order_id=None):
        oid = order_id or self.order_id
        if not oid:
            return None
        code, data = self._get(f"/api/v1/email/orders/{oid}")
        if code != 200 or not data.get("success"):
            return None
        return data.get("data") or {}

    def reorder(self, order_id=None):
        oid = order_id or self.order_id
        if not oid:
            return False
        code, data = self._post(f"/api/v1/email/orders/{oid}/reorder")
        if code == 200 and data.get("success"):
            AppLogger.success("[OTPTrust] Reorder requested")
            return True
        msg = data.get("message") or f"HTTP {code}"
        AppLogger.warn(f"[OTPTrust] reorder failed - {msg}")
        return False

    def cancel(self, order_id=None):
        oid = order_id or self.order_id
        if not oid:
            return False
        code, data = self._post(f"/api/v1/email/orders/{oid}/cancel")
        if code == 200 and data.get("success"):
            AppLogger.success(f"[OTPTrust] Order {oid} cancelled")
            self.order_id = None
            self.email = None
            return True
        msg = data.get("message") or f"HTTP {code}"
        AppLogger.warn(f"[OTPTrust] cancel failed - {msg}")
        return False

    def release(self):
        self.order_id = None
        self.email = None
        self.service_id = None
        self.provider = None
        return True

    def get_email(self):
        for domain in (None, "icloud", "gmail"):
            svc_id, provider = self.find_service_id("facebook", domain=domain)
            if not svc_id:
                continue
            email = self.rent(svc_id, provider=provider)
            if email:
                return email, self.order_id
        AppLogger.error("[OTPTrust] Could not rent any Facebook email")
        return None, None

    def get_otp(self, email=None, order_id=None, timeout=120, interval=3.0, token=None):
        oid = order_id or self.order_id
        if not oid:
            AppLogger.warn("[OTPTrust] No order_id - cannot poll OTP")
            return None

        start = time.time()
        while time.time() - start < timeout:
            try:
                d = self.get_order(oid)
                if d:
                    status = str(d.get("status", "")).lower()
                    otp = d.get("otp")
                    if otp:
                        otp_str = str(otp).strip()
                        AppLogger.success(f"[OTPTrust] OTP: {otp_str}")
                        return otp_str
                    if status in ("failed", "released"):
                        AppLogger.warn(f"[OTPTrust] Order status terminal: {status}")
                        return None
            except Exception as e:
                AppLogger.warn(f"[OTPTrust] poll error: {e}")
            time.sleep(interval)
        return None


def run_single(setup):
    proxy = None
    pt = setup["proxy_type"]
    if pt == "zy":
        buyer = setup.get("zy_buyer")
        if buyer:
            raw = buyer.buy_and_get(qty=1)
            if raw:
                proxy = ProxyManager.format_proxy_string(raw)
    elif pt == "static":
        proxy = random.choice(setup["static_proxies"]) if setup["static_proxies"] else None
    elif pt == "tmproxy":
        proxy = ProxyManager.get_tmproxy(setup["tmproxy_key"])
    elif pt == "androidmodvip":
        if setup.get("androidmodvip_rotate_id") and setup.get("androidmodvip_token"):
            proxy = ProxyManager.rotate_androidmodvip_proxy(
                setup["androidmodvip_token"],
                setup["androidmodvip_rotate_id"]
            )
            if not proxy:
                AppLogger.warn("[AndroidModVip] Rotating proxy failed - retrying once...")
                time.sleep(3)
                proxy = ProxyManager.rotate_androidmodvip_proxy(
                    setup["androidmodvip_token"],
                    setup["androidmodvip_rotate_id"],
                    wait_for_rotate=False,
                )
        else:
            proxy = ProxyManager.get_androidmodvip_proxy(setup["androidmodvip_key"])
        if not proxy:
            AppLogger.error("[AndroidModVip] Cannot get proxy - abort this attempt")
            result = RegistrationResult(
                status="FAILED",
                error_message="ANDROIDMODVIP_PROXY_FAILED",
            )
            ResultWriter.route(result)
            return result
    elif pt == "proxy5stars":
        proxy = ProxyManager.get_proxy5stars_proxy(setup["proxy5stars_key"])
    elif pt == "homeproxy":
        proxy = ProxyManager.get_homeproxy(setup["homeproxy_key"])

    verify_source = setup.get("verify_source") or setup.get("mail_provider", "zymail")

    mail = None
    real_email, real_order_id = (None, None)
    prov = setup.get("mail_provider", "zymail")
    cfg = setup.get("mail_config") or {}

    if prov == "tempmail":
        mail = TempMailClient()
    elif prov == "dropmail":
        mail = DropMailClient(token=cfg.get("token", ""))
    elif prov == "mail1s":
        mail = Mail1sClient(token=cfg.get("token", MAIL1S_DEFAULT_TOKEN))
    elif prov == "zymail":
        mail = ServerMailZy(
            api_key=cfg.get("api_key", ZYMAIL_DEFAULT_KEY),
            base_url=cfg.get("base_url", ZYMAIL_BASE),
        )
    elif prov == "otptrust":
        mail = OTPTrustEmailClient(
            api_key=cfg.get("api_key", ""),
            base_url=cfg.get("base_url", OTPTRUST_BASE),
        )
    else:
        mail = ServerMailZy(
            api_key=ZYMAIL_DEFAULT_KEY,
            base_url=ZYMAIL_BASE,
        )

    if mail:
        try:
            real_email, real_order_id = mail.get_email()
            if real_email:
                AppLogger.mail(f"Rented REAL - {real_email}")
        except Exception as e:
            AppLogger.warn(f"Rent mail error: {e}")

    if not real_email:
        AppLogger.error("No real mail rented - cannot register. Abort this attempt.")
        result = RegistrationResult(
            status="FAILED",
            error_message="NO_REAL_MAIL",
        )
        ResultWriter.route(result)
        try:
            if mail and hasattr(mail, "release"):
                mail.release()
        except Exception:
            pass
        return result

    reg_mode = setup.get("reg_mode", "FULL")
    reg_mode_effective = reg_mode

    if reg_mode == "DIRECT_MAIL":
        reg_contact = real_email
        reg_contact_type = "EMAIL"
    elif reg_mode == "HYBRID":
        reg_contact = real_email
        reg_contact_type = "EMAIL"
    elif reg_mode == "FULL":
        reg_contact = generate_fake_email()
        reg_contact_type = "EMAIL"
        AppLogger.info(f"Fake mail for reg - {reg_contact}")
    else:
        reg_contact = generate_valid_us_phone()
        AppLogger.info(f"Fake US phone for reg - {reg_contact}")
        reg_contact_type = "PHONE"

    fake_phone = None
    fake_mail_mid = None
    if reg_contact_type == "PHONE":
        fake_phone = reg_contact
    if reg_mode == "FULL":
        fake_mail_mid = reg_contact

    if reg_mode_effective == "FULL":
        AppLogger.info(f"Mode FULL - register with fake mail {fake_mail_mid}, then change to REAL mail {real_email}")
    elif reg_mode_effective == "HYBRID":
        AppLogger.info(f"Mode HYBRID - register directly with REAL mail {real_email}")
    elif reg_mode_effective == "DIRECT_MAIL":
        AppLogger.info(f"Mode DIRECT_MAIL - register directly with REAL mail {real_email}")

    ho, ten, cc, sex, locale = generate_random_name(setup["country_list"])
    gender = "FEMALE" if sex == 1 else "MALE"
    flag = COUNTRY_META[cc]['flag']
    label = COUNTRY_META[cc]['label']
    full_name = format_full_name(ho, ten, cc)
    AppLogger.info(f"Persona - {full_name}  {flag} {label}  -  {gender}")

    profile = AccountProfile(
        first_name=ten, last_name=ho, gender=gender,
        birthday_day=random.randint(1, 28),
        birthday_month=random.randint(1, 12),
        birthday_year=build_adult_birth_year(),
        email=reg_contact if reg_contact_type == "EMAIL" else None,
        phone=reg_contact if reg_contact_type == "PHONE" else None,
        password=generate_secure_password(),
        country=cc,
    )

    client = WWWClient(proxy=proxy)
    engine = WWWRegEngine(client)
    result: Optional[RegistrationResult] = None
    monitor: Optional[BackgroundLiveMonitor] = None

    try:
        if not engine.warmup_homepage():
            result = RegistrationResult(status="FAILED", error_message="WARMUP_FAILED")
            ResultWriter.route(result)
            return result

        time.sleep(random.uniform(0.8, 1.8))

        if not engine.load_www_tokens():
            result = RegistrationResult(status="FAILED", error_message="LOAD_TOKENS_FAILED")
            ResultWriter.route(result)
            return result

        check_ok = engine.check_submit(profile)
        if not check_ok and reg_contact_type == "PHONE":
            AppLogger.warn("Field invalid - retry with new phone")
            profile.phone = generate_valid_us_phone()
            AppLogger.info(f"New phone - {profile.phone}")
            time.sleep(random.uniform(3, 6))
            check_ok = engine.check_submit(profile)
        if not check_ok:
            result = RegistrationResult(
                status="FAILED", phone=profile.phone or profile.email,
                name=full_name,
                country=cc,
                error_message="FIELD_INVALID",
            )
            ResultWriter.route(result)
            return result

        delay_reg = random.uniform(15, 30)
        AppLogger.wait(f"Wait {delay_reg:.1f}s after tokens before register")
        time.sleep(delay_reg)

        ok, err = engine.submit_registration(profile)
        if not ok:
            if "REG_FAILED" in err or "HTTP" in err:
                if "USER_REGISTER_MOBILE_PHONE_INVALID" in err or "CONTACTPOINT" in err:
                    if reg_contact_type == "PHONE":
                        profile.phone = generate_valid_us_phone()
                        AppLogger.warn(f"Phone invalid - retry with new phone: {profile.phone}")
                        time.sleep(random.uniform(3, 6))
                    else:
                        AppLogger.warn("Email invalid - retry reg")
                        time.sleep(random.uniform(3, 5))
                else:
                    AppLogger.warn(f"Retry reg - {err[:80]}")
                    time.sleep(random.uniform(3, 5))
                ok, err = engine.submit_registration(profile)

        if not ok:
            result = RegistrationResult(
                status="CHECKPOINT" if "CHECKPOINT" in err else "FAILED",
                password=profile.password, phone=profile.phone or profile.email,
                name=full_name,
                country=cc,
                error_message=err,
            )
            if "CHECKPOINT" in err:
                AppLogger.checkpoint(err)
            else:
                AppLogger.error(err)
            ResultWriter.route(result)
            return result

        cookies = client.get_cookies_dict()
        c_user = cookies.get("c_user", "")
        if not c_user:
            result = RegistrationResult(status="FAILED", error_message="NO_CUSER")
            ResultWriter.route(result)
            return result

        result = RegistrationResult(
            status="PENDING_OTP", uid=c_user,
            password=profile.password,
            email=real_email,
            phone=None,
            name=full_name,
            country=cc,
            cookie_str=client.get_cookie_string(),
            fake_email=fake_mail_mid,
        )

        if reg_mode_effective in ("DIRECT_MAIL", "HYBRID"):
            AppLogger.step(5, "Registered", f"UID {c_user} (real mail: {real_email})")
        else:
            AppLogger.step(5, "Registered", f"UID {c_user} (fake mail: {fake_mail_mid})")

        otp_v = None
        need_contact_change = reg_mode_effective == "FULL"

        if need_contact_change:
            change_delay = random.uniform(10, 20)
            AppLogger.wait(f"Wait {change_delay:.1f}s before changing contact point")
            time.sleep(change_delay)

            engine.refresh_from_confirm()
            otp_v = OTPVerifier(client, engine=engine)

        if reg_mode_effective == "FULL":
            AppLogger.step(7, "Change to REAL mail", f"{real_email}")
            changed = otp_v.add_contact_point(c_user, real_email)
            if not changed:
                AppLogger.warn("Change to real contact failed")
                result.status = "PENDING_OTP"
                result.error_message = "ADD_CONTACT_FAILED"
                ResultWriter.route(result)
                return result
        else:
            AppLogger.info(f"Mode {reg_mode_effective} - no contact change needed")

        AppLogger.step(8, "Poll OTP", f"from REAL {real_email}")
        otp_code = mail.get_otp(real_email, order_id=real_order_id, timeout=setup["otp_timeout"])

        if not otp_code:
            AppLogger.warn("No OTP - requesting resend")
            if otp_v is None:
                engine.refresh_from_confirm()
                otp_v = OTPVerifier(client, engine=engine)
            if otp_v.resend_otp(c_user):
                time.sleep(5)
                otp_code = mail.get_otp(real_email, order_id=real_order_id,
                                         timeout=setup["otp_timeout"])

        if not otp_code:
            result.status = "PENDING_OTP"
            result.error_message = "OTP_TIMEOUT"
            ResultWriter.route(result)
            return result

        delay_verify = random.uniform(5, 10)
        AppLogger.wait(f"Wait {delay_verify:.1f}s before verify OTP")
        time.sleep(delay_verify)

        if otp_v is None:
            engine.refresh_from_confirm()
            otp_v = OTPVerifier(client, engine=engine)

        verified, reason = otp_v.verify_otp(otp_code, c_user)
        if not verified:
            result.status = "FAILED"
            result.error_message = reason
            AppLogger.warn(f"OTP failed - {reason}")
            ResultWriter.route(result)
            return result

        result.status = "SUCCESS"
        result.cookie_str = client.get_cookie_string()
        AppLogger.success(f"OTP verified - UID {c_user}")

        monitor = BackgroundLiveMonitor(uid=c_user, proxy=proxy, interval=3)
        monitor.start()
        AppLogger.info("[LIVE-MONITOR] started right after OTP verify")

        def _abort_if_dead(stage=""):
            if monitor.is_dead():
                AppLogger.warn(f"[LIVE-MONITOR] Account DIED{' at ' + stage if stage else ''} - ABORT")
                try:
                    monitor.stop()
                except Exception:
                    pass
                return True
            return False

        time.sleep(2.0)
        if _abort_if_dead("initial check"):
            result.status = "FAILED"
            result.error_message = "ACCOUNT_DIE"
            return result

        engine.refresh_from_home()
        if _abort_if_dead("after warmup"):
            result.status = "FAILED"
            result.error_message = "ACCOUNT_DIE"
            return result

        do_avt = setup.get("upload_avatar", False)
        do_cov = setup.get("upload_cover", False)

        if do_avt or do_cov:
            try:
                uploader = CookieMediaUploader(
                    uid=c_user,
                    cookies=result.cookie_str,
                    fb_dtsg="",
                    lsd="",
                    jazoest="",
                    proxy=proxy,
                    avt_source=setup.get("avatar_source", "local"),
                    cov_source=setup.get("cover_source", "local"),
                    engine=engine,
                    monitor=monitor,
                )
                uploader.load_tokens_from_home()

                if _abort_if_dead("after load upload tokens"):
                    result.status = "FAILED"
                    result.error_message = "ACCOUNT_DIE"
                    return result

                if do_avt:
                    uploader.run_avatar()
                    if _abort_if_dead("after avatar upload"):
                        result.status = "FAILED"
                        result.error_message = "ACCOUNT_DIE"
                        return result

                if do_cov:
                    uploader.run_cover()
                    if _abort_if_dead("after cover upload"):
                        result.status = "FAILED"
                        result.error_message = "ACCOUNT_DIE"
                        return result
            except Exception as _me:
                AppLogger.warn(f"Media error: {_me}")

            if _abort_if_dead("after media"):
                result.status = "FAILED"
                result.error_message = "ACCOUNT_DIE"
                return result

        if setup.get("fetch_token", True):
            if _abort_if_dead("before token fetch"):
                result.status = "FAILED"
                result.error_message = "ACCOUNT_DIE"
                return result

            AppLogger.step(12, "Fetch token", "FB4A login")
            try:
                token, fb_cookies = TokenFetcher.fetch(
                    uid=c_user, password=profile.password, twofa_secret=None, proxy=proxy,
                )
                if token:
                    result.token_eaaau = token
                    if fb_cookies:
                        result.cookie_str = fb_cookies
            except Exception as _te:
                AppLogger.warn(f"Token error: {_te}")

            if _abort_if_dead("after token fetch"):
                result.status = "FAILED"
                result.error_message = "ACCOUNT_DIE"
                return result

        monitor.stop()
        AppLogger.info("[LIVE-MONITOR] stopped")

        ResultWriter.route(result)
        return result
    finally:
        try:
            if monitor:
                monitor.stop()
        except Exception:
            pass
        try:
            if mail and hasattr(mail, "release"):
                mail.release()
        except Exception:
            pass
        try:
            if getattr(client, "_anti", False):
                client.session.close()
            else:
                client.session.close()
        except Exception:
            pass


def enable_ansi():
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(ctypes.windll.kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def print_banner():
    os.system("cls" if os.name == "nt" else "clear")
    w = term_width()
    line = "=" * (w - 2)
    title = "F A C E B O O K   R E G I S T R A T I O N"
    sub = "Author: KhuyCoder0706 | Github: https://github.com/khuycoder0706"
    print()
    print(color(f"+{line}+", C.BCYAN))
    tw = display_width(title)
    pad = max(0, (w - 2 - tw) // 2)
    right = max(0, (w - 2 - tw) - pad)
    print(color("|", C.BCYAN) + " " * pad + color(title, C.BOLD + C.BWHITE) + " " * right + color("|", C.BCYAN))
    sw = display_width(sub)
    sp = max(0, (w - 2 - sw) // 2)
    sr = max(0, (w - 2 - sw) - sp)
    print(color("|", C.BCYAN) + " " * sp + color(sub, C.GRAY) + " " * sr + color("|", C.BCYAN))
    print(color(f"+{line}+", C.BCYAN))
    print()


def prompt(text, default="", clr=C.BCYAN, **kwargs):
    if "d" in kwargs:
        default = kwargs["d"]
    suffix = f"  {color('[' + default + ']', C.DGRAY)}" if default else ""
    raw = input(f" {color('>', clr)} {color(text, C.BWHITE)}{suffix}  ").strip()
    return raw or default


def build_setup():
    global DEBUG
    print_banner()
    setup = {
        "proxy_type": "none", "static_proxies": [], "tmproxy_key": "",
        "androidmodvip_key": "", "proxy5stars_key": "", "homeproxy_key": "",
        "zy_username": ZY_DEFAULT_USER, "zy_password": ZY_DEFAULT_PASS, "zy_buyer": None,
        "verify_source": "zymail", "mail_provider": "zymail", "mail_config": {},
        "country_list": list(ALL_COUNTRIES),
        "loop": 1, "otp_timeout": 120,
        "fetch_token": True,
        "reg_mode": "FULL",
        "upload_avatar": False, "avatar_source": "local",
        "upload_cover": False, "cover_source": "local",
    }

    AppLogger.section("PROXY", "*")
    AppLogger.menu_item("1", "Zy.io.vn", "buy directly", default=True)
    AppLogger.menu_item("2", "Static proxies")
    AppLogger.menu_item("3", "TMProxy")
    AppLogger.menu_item("4", "AndroidModVip")
    AppLogger.menu_item("5", "Proxy5Stars")
    AppLogger.menu_item("6", "HomeProxy", "rotatev2")
    AppLogger.menu_item("7", "No proxy")
    print()
    pc = prompt("Choose proxy", default="1")
    if pc == "1":
        setup["proxy_type"] = "zy"
        print()
        setup["zy_username"] = prompt("Zy username", default=ZY_DEFAULT_USER) or ZY_DEFAULT_USER
        setup["zy_password"] = prompt("Zy password", default=ZY_DEFAULT_PASS) or ZY_DEFAULT_PASS
        buyer = ZYProxyBuyer(setup["zy_username"], setup["zy_password"])
        if buyer.login():
            setup["zy_buyer"] = buyer
        else:
            AppLogger.error("ZY login failed - fallback to no proxy")
            setup["proxy_type"] = "none"
    elif pc == "2":
        setup["proxy_type"] = "static"
        print(f"\n {color('Enter proxies one per line - blank to stop', C.GRAY)}")
        while True:
            p = input(f"   {color('>', C.BCYAN)} {color('Proxy #' + str(len(setup['static_proxies']) + 1), C.GRAY)}  ").strip()
            if not p:
                break
            fmt = ProxyManager.format_proxy_string(p)
            if fmt:
                setup["static_proxies"].append(fmt)
                print(f"     {color('OK', C.LIME)} {color(fmt, C.WHITE)}")
        if not setup["static_proxies"]:
            setup["proxy_type"] = "none"
    elif pc == "3":
        setup["proxy_type"] = "tmproxy"
        print()
        setup["tmproxy_key"] = prompt("TMProxy API key")
    elif pc == "4":
        setup["proxy_type"] = "androidmodvip"
        print()
        AppLogger.menu_item("1", "Rotating Key", "Enter API key (rotatev2)", default=True)
        AppLogger.menu_item("2", "Rotating Proxy", "Select a proxy from purchased list")
        amv_choice = prompt("Select type [1-2, default 1]") or "1"
        if amv_choice == "2":
            amv_token = prompt("Enter Bearer Token (accessToken)")
            amv_merchant = prompt("Enter x-merchant-id")
            if not amv_token or not amv_merchant:
                AppLogger.error("Token and merchant-id cannot be empty!")
                setup["proxy_type"] = "none"
            else:
                AppLogger.info("Fetching rotating proxy list...")
                proxy_list = ProxyManager.list_androidmodvip_rotating_proxies(amv_token, amv_merchant)
                if not proxy_list:
                    AppLogger.error("No rotating proxies found. Check token/merchant-id.")
                    setup["proxy_type"] = "none"
                else:
                    active_proxies = [p for p in proxy_list if p["status"] == "ACTIVE"]
                    if not active_proxies:
                        AppLogger.warn("No ACTIVE proxies in the list.")
                        active_proxies = proxy_list
                    print("\n--- ROTATING PROXY LIST ---")
                    import datetime as _dt
                    for i, p in enumerate(active_proxies, 1):
                        exp_str = ""
                        if p.get("expiredAt"):
                            try:
                                exp_dt = _dt.datetime.fromtimestamp(p["expiredAt"] / 1000)
                                exp_str = exp_dt.strftime("%d/%m/%Y %H:%M")
                            except Exception:
                                exp_str = str(p["expiredAt"])
                        status_icon = "Y" if p["status"] == "ACTIVE" else "N"
                        note = f"{p['ip']}:{p['port']} | {p['provider']} - {p['location']} | [{status_icon}] {p['status']} | EXP: {exp_str} | Rotate: {p['rotateInterval']}s"
                        AppLogger.menu_item(str(i), p["code"] or f"Proxy #{p['id']}", note)
                    px_idx = prompt(f"Select proxy [1-{len(active_proxies)}, default 1]") or "1"
                    try:
                        selected = active_proxies[int(px_idx) - 1]
                    except (ValueError, IndexError):
                        selected = active_proxies[0]
                    setup["androidmodvip_token"] = amv_token
                    setup["androidmodvip_rotate_id"] = selected["id"]
                    AppLogger.info(f"Selected: {selected['code'] or selected['id']} | {selected['ip']}:{selected['port']} | {selected['provider']} {selected['location']}")
        else:
            setup["androidmodvip_key"] = prompt("AndroidModVip API key (Rotating Key)")
    elif pc == "5":
        setup["proxy_type"] = "proxy5stars"
        print()
        setup["proxy5stars_key"] = prompt("Proxy5Stars API key")
    elif pc == "6":
        setup["proxy_type"] = "homeproxy"
        print()
        setup["homeproxy_key"] = prompt("HomeProxy Rotate Key")
        if setup["homeproxy_key"]:
            info = ProxyManager.check_homeproxy(setup["homeproxy_key"])
            if info:
                AppLogger.proxy(f"HomeProxy check OK - proxy={info.get('proxy','?')}")
                AppLogger.proxy(f"ip={info.get('ip','?')} / timeRemaining={info.get('timeRemaining','?')}s")
                msg = info.get("message", "")
                if msg:
                    AppLogger.proxy(f"message: {msg}")
            else:
                AppLogger.warn("HomeProxy key check failed - will retry at runtime")
    elif pc == "7":
        setup["proxy_type"] = "none"

    AppLogger.section("SERVER VERIFY OTP", "*")
    AppLogger.menu_item("1", "Server Mail Zy", "email - keyhuy", default=True)
    AppLogger.menu_item("2", "10MinuteMail", "email - free")
    AppLogger.menu_item("3", "DropMail.me", "email - af_ token")
    AppLogger.menu_item("4", "Mail1s.net", "email - m1s_ token")
    AppLogger.menu_item("5", "OTPTrust", "email - Bearer token")
    print()
    mc = prompt("Choose verify source [1-5]", default="1").strip()

    if mc == "2":
        setup["verify_source"] = "tempmail"
        setup["mail_provider"] = "tempmail"
        setup["mail_config"] = {}
    elif mc == "3":
        setup["verify_source"] = "dropmail"
        setup["mail_provider"] = "dropmail"
        print()
        tok = prompt("DropMail token (af_...)", default="")
        if not tok:
            AppLogger.error("DropMail token required - fallback to Server Mail Zy")
            setup["verify_source"] = "zymail"
            setup["mail_provider"] = "zymail"
            setup["mail_config"] = {
                "api_key": ZYMAIL_DEFAULT_KEY,
                "base_url": ZYMAIL_BASE,
            }
        else:
            setup["mail_config"] = {"token": tok}
    elif mc == "4":
        setup["verify_source"] = "mail1s"
        setup["mail_provider"] = "mail1s"
        print()
        setup["mail_config"] = {
            "token": prompt("Mail1s token (m1s_...)", default=MAIL1S_DEFAULT_TOKEN) or MAIL1S_DEFAULT_TOKEN,
        }
    elif mc == "5":
        setup["verify_source"] = "otptrust"
        setup["mail_provider"] = "otptrust"
        print()
        setup["mail_config"] = {
            "api_key": prompt("OTPTrust API Key (Bearer token)"),
            "base_url": prompt("OTPTrust base URL", default=OTPTRUST_BASE) or OTPTRUST_BASE,
        }
    else:
        setup["verify_source"] = "zymail"
        setup["mail_provider"] = "zymail"
        print()
        AppLogger.info("Default key: keyhuy (Luân/Huy/Công/Khang/Hiếu available)")
        setup["mail_config"] = {
            "api_key": prompt("Server Mail Zy API key", default=ZYMAIL_DEFAULT_KEY) or ZYMAIL_DEFAULT_KEY,
            "base_url": prompt("Server Mail Zy host", default=ZYMAIL_BASE) or ZYMAIL_BASE,
        }

    AppLogger.section("REGISTRATION MODE", "*")
    AppLogger.menu_item("1", "FULL",         "fake gmail -> real mail (safest)", default=True)
    AppLogger.menu_item("2", "HYBRID",       "real mail directly (fast, no fake)")
    AppLogger.menu_item("3", "DIRECT_PHONE", "fake US phone only")
    AppLogger.menu_item("4", "DIRECT_MAIL",  "real mail directly (fastest)")
    print()
    rm_choice = prompt("Choose registration mode [1-4]", default="1").strip()
    if rm_choice == "1":
        setup["reg_mode"] = "FULL"
    elif rm_choice == "2":
        setup["reg_mode"] = "HYBRID"
    elif rm_choice == "3":
        setup["reg_mode"] = "DIRECT_PHONE"
    elif rm_choice == "4":
        setup["reg_mode"] = "DIRECT_MAIL"
    else:
        setup["reg_mode"] = "FULL"

    mode_desc = {
        "FULL":         "fake gmail -> real mail",
        "HYBRID":       "real mail directly (no fake step)",
        "DIRECT_PHONE": "fake US phone only",
        "DIRECT_MAIL":  "real mail directly",
    }
    AppLogger.info(f"Registration mode: {setup['reg_mode']} - {mode_desc[setup['reg_mode']]}")

    AppLogger.section("UPLOAD MEDIA", "*")
    setup["upload_avatar"] = prompt("Upload avatar? (y/N)", default="n").lower() in {"y", "yes", "1"}
    if setup["upload_avatar"]:
        print()
        AppLogger.menu_item("1", "Local (folder Avatar/)", default=True)
        AppLogger.menu_item("2", "Random link (online)")
        print()
        src = prompt("Avatar source", default="1")
        setup["avatar_source"] = "link" if src == "2" else "local"

    setup["upload_cover"] = prompt("Upload cover? (y/N)", default="n").lower() in {"y", "yes", "1"}
    if setup["upload_cover"]:
        print()
        AppLogger.menu_item("1", "Local (folder Cover/)", default=True)
        AppLogger.menu_item("2", "Random link (online)")
        print()
        src = prompt("Cover source", default="1")
        setup["cover_source"] = "link" if src == "2" else "local"

    AppLogger.section("COUNTRY POOL", "*")
    for i, k in enumerate(ALL_COUNTRIES, 1):
        flag = COUNTRY_META[k]['flag']
        label = COUNTRY_META[k]['label']
        print(f"   {color(str(i).rjust(2), C.TEAL)}  {flag}  "
              f"{color(label.ljust(20), C.WHITE)}  {color('(' + k.upper() + ')', C.DGRAY)}")
    print()
    rc = prompt("Choose (all = every)", default="all").strip()
    if rc.lower() in ("all", ""):
        setup["country_list"] = list(ALL_COUNTRIES)
    else:
        picked = [ALL_COUNTRIES[int(t) - 1] for t in rc.replace(" ", "").split(",")
                  if t.isdigit() and 1 <= int(t) <= len(ALL_COUNTRIES)]
        setup["country_list"] = picked or list(ALL_COUNTRIES)

    AppLogger.section("ADVANCED", "*")
    dbg = prompt("Enable DEBUG", default="n").strip().lower()
    DEBUG = dbg in {"y", "yes", "1"}
    if DEBUG:
        AppLogger.warn("DEBUG mode ON")

    setup["fetch_token"] = prompt("Fetch FB4A access token", default="y").lower() in {"y", "yes", "1", ""}
    try:
        setup["otp_timeout"] = int(prompt("OTP timeout (s)", default="120") or "120")
    except Exception:
        setup["otp_timeout"] = 120
    try:
        setup["loop"] = int(prompt("Number of LIVE accounts needed", default="1") or "1")
    except Exception:
        setup["loop"] = 1

    return setup


def run_all(setup):
    target_live = max(1, int(setup.get("loop", 1)))
    current_account = 0

    AppLogger.section("STARTING", "*")
    AppLogger.kv("Proxy", setup["proxy_type"], C.TEAL if setup["proxy_type"] != "none" else C.DGRAY)

    verify_source = setup.get("verify_source") or setup.get("mail_provider", "zymail")
    verify_label_map = {
        "zymail":   "Server Mail Zy",
        "tempmail": "10MinuteMail",
        "dropmail": "DropMail.me",
        "mail1s":   "Mail1s.net",
        "otptrust": "OTPTrust",
    }
    verify_label = verify_label_map.get(verify_source, verify_source)
    verify_color = C.LIME if verify_source == "otptrust" else C.PINK
    AppLogger.kv("Verify via", verify_label, verify_color)

    reg_mode = setup.get("reg_mode", "FULL")
    mode_color = {
        "FULL": C.LIME,
        "HYBRID": C.TEAL,
        "DIRECT_PHONE": C.GOLD,
        "DIRECT_MAIL": C.PINK,
    }.get(reg_mode, C.BWHITE)
    AppLogger.kv("Reg Mode", reg_mode, mode_color)

    media_str = []
    if setup.get("upload_avatar"):
        media_str.append(f"avt={setup.get('avatar_source')}")
    if setup.get("upload_cover"):
        media_str.append(f"cover={setup.get('cover_source')}")
    AppLogger.kv("Media", " / ".join(media_str) if media_str else "OFF",
                 C.LAV if media_str else C.DGRAY)
    AppLogger.kv("Countries", " / ".join(f"{COUNTRY_META[k]['flag']} {k.upper()}" for k in setup["country_list"]), C.LAV)
    AppLogger.kv("Target LIVE", str(target_live), C.GOLD)
    AppLogger.kv("Fetch token", "ON" if setup.get("fetch_token", True) else "OFF",
                 C.LIME if setup.get("fetch_token", True) else C.DGRAY)
    AppLogger.kv("DEBUG", "ON" if DEBUG else "OFF", C.GOLD if DEBUG else C.DGRAY)
    print()

    live_count = 0
    failed_count = 0
    checkpoint_count = 0
    die_count = 0
    no_mail_count = 0

    while live_count < target_live:
        current_account += 1
        AppLogger.account_header(current_account, f"{live_count}/{target_live}",
                                 setup["proxy_type"], verify_label)
        try:
            res = run_single(setup)
            AppLogger.result_box(res)
            st = (res.status or "").upper()
            if st in ("SUCCESS", "LIVE"):
                live_count += 1
                AppLogger.success(f"LIVE {live_count}/{target_live}")
            elif "CHECKPOINT" in st:
                checkpoint_count += 1
            elif res.error_message == "ACCOUNT_DIE":
                die_count += 1
            elif res.error_message == "NO_REAL_MAIL":
                no_mail_count += 1
            else:
                failed_count += 1
        except Exception as e:
            AppLogger.error(f"Exception: {e}")
            import traceback
            traceback.print_exc()
            failed_count += 1

        if live_count < target_live:
            wait = random.uniform(60, 120)
            AppLogger.info(f"Cooling down {wait:.1f}s  (live {live_count}/{target_live})")
            time.sleep(wait)

    AppLogger.section("SUMMARY", "*")
    AppLogger.kv("Target LIVE", str(target_live), C.BWHITE)
    AppLogger.kv("Got LIVE", str(live_count), C.LIME)
    AppLogger.kv("Attempts", str(current_account), C.BWHITE)
    AppLogger.kv("Checkpoint", str(checkpoint_count), C.GOLD)
    AppLogger.kv("Die", str(die_count), C.BRED)
    AppLogger.kv("No mail", str(no_mail_count), C.BRED)
    AppLogger.kv("Failed", str(failed_count), C.BRED)
    AppLogger.kv("Output dir", ResultWriter.OUTPUT_DIR, C.TEAL)
    print()


if __name__ == "__main__":
    enable_ansi()
    if not HAS_NACL or not HAS_CRYPTOGRAPHY:
        print(color(" Missing pynacl / cryptography - password encrypt may fail", C.BYELLOW))
    if not HAS_CRYPTODOME:
        print(color(" Missing pycryptodome - FB4A token fetch disabled", C.BYELLOW))
    try:
        setup = build_setup()
        run_all(setup)
    except KeyboardInterrupt:
        print(f"\n{color(' Stopped by user', C.BYELLOW)}")
    except Exception as e:
        print(f"\n{color(' Error: ', C.BRED)} {e}")
        import traceback
        traceback.print_exc()
