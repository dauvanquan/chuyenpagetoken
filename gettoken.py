import requests
import json
import time
import random
import uuid
import base64
import io
import struct
import re
import email.utils
from typing import Optional, Dict, Tuple
from Cryptodome.Cipher import AES, PKCS1_v1_5
from Cryptodome.PublicKey import RSA
from Cryptodome.Random import get_random_bytes
import pyotp
import threading
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

sys_dont_write_bytecode = True
print_lock = threading.Lock()

DEBUG = False


def safe_print(text):
    with print_lock:
        if not text.startswith('\033['):
            text = f"\033[1m{text}\033[0m"
        print(text)


def log_system(msg):
    safe_print(f"[Hệ Thống] | {msg}")


def log_account(uid, msg):
    safe_print(f"[{uid}] | {msg}")


def debug_print(title, content):
    if not DEBUG:
        return
    with print_lock:
        print(f"\033[1;33m[DEBUG] ==== {title} ====\033[0m")
        if isinstance(content, (dict, list)):
            try:
                content = json.dumps(content, indent=2, ensure_ascii=False)
            except Exception:
                content = str(content)
        print(content)
        print(f"\033[1;33m[DEBUG] ==== END {title} ====\033[0m")


def bold_input(prompt):
    import sys
    sys.stdout.write(f"\033[1m{prompt}\033[0m")
    sys.stdout.flush()
    return sys.stdin.readline().strip()


def banner():
    os.system("cls" if os.name == "nt" else "clear")
    banner_text = """
===================================
      TOOL GET TOKEN FACEBOOK      
===================================
Author: HuyCoder
"""
    safe_print(banner_text)


def parse_input_line(line):
    parts = line.split('|')
    parts = [p.strip() for p in parts]
    if len(parts) == 2:
        uid, pwd = parts
        return uid, pwd, "", "", False
    elif len(parts) == 3:
        uid, pwd, third = parts
        if ';' in third or '=' in third:
            return uid, pwd, "", third, False
        else:
            return uid, pwd, third, "", True
    elif len(parts) == 4:
        uid, pwd, twofa, cookie = parts
        return uid, pwd, twofa, cookie, True
    else:
        raise ValueError(f"Số trường không hợp lệ: {len(parts)}. Cần 2, 3 hoặc 4 trường.")


def extract_datr_from_cookie(cookie_str: str) -> str:
    if not cookie_str:
        return ""
    match = re.search(r'datr=([^;]+)', cookie_str)
    return match.group(1) if match else cookie_str


def parse_proxy(proxy_str: Optional[str]) -> Optional[Dict[str, str]]:
    if not proxy_str or not str(proxy_str).strip():
        return None
    p = str(proxy_str).strip()
    if p.startswith(('http://', 'https://', 'socks5://', 'socks4://')):
        return {'http': p, 'https': p}
    parts = p.split(':')
    if len(parts) == 4:
        host, port, user, pwd = parts
        formatted = f"http://{user}:{pwd}@{host}:{port}"
        return {'http': formatted, 'https': formatted}
    elif len(parts) == 2:
        host, port = parts
        formatted = f"http://{host}:{port}"
        return {'http': formatted, 'https': formatted}
    else:
        formatted = f"http://{p}"
        return {'http': formatted, 'https': formatted}


COOKIE_ORDER = ['c_user', 'xs', 'fr', 'datr', 'sb', 'spin', 'wd', 'presence', 'm_pixel_ratio', 'locale']


def _recursive_collect_strings(obj, out):
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _recursive_collect_strings(v, out)
    elif isinstance(obj, list):
        for item in obj:
            _recursive_collect_strings(item, out)


def _unescape_many(s: str) -> str:
    prev = None
    cur = s
    for _ in range(6):
        if prev == cur:
            break
        prev = cur
        if cur.startswith('"') and cur.endswith('"'):
            try:
                cur = json.loads(cur)
                continue
            except Exception:
                pass
        try:
            cur = json.loads('"' + cur.replace('"', '\\"') + '"')
            continue
        except Exception:
            pass
        cur = (cur
               .replace('\\/', '/')
               .replace('\\"', '"')
               .replace('\\\\', '\\'))
    return cur


def _find_cookie_pairs_in_text(text: str):
    pairs = []
    for m in re.finditer(r'"name"\s*:\s*"([^"]+)"\s*,\s*"value"\s*:\s*"([^"]*)"', text):
        pairs.append((m.group(1), m.group(2)))
    if not pairs:
        for m in re.finditer(r'"name"\s*:\s*"([^"]+)"\s*,\s*"value"\s*:\s*"([^"]*)"', _unescape_many(text)):
            pairs.append((m.group(1), m.group(2)))
    return pairs


def calc_jazoest(token: str) -> str:
    return "2" + str(sum(ord(c) for c in token))


def parse_cookie_str(cookie_str: str) -> dict:
    cookies = {}
    for item in cookie_str.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def check_token_status(access_token: str, proxy: Optional[str] = None) -> dict:
    url = "https://graph.facebook.com/me"
    params = {"access_token": access_token}
    try:
        r = requests.get(url, params=params, proxies=parse_proxy(proxy), timeout=20)
        try:
            data = r.json()
        except Exception:
            return {"status": "die", "error": f"Non-JSON response: {r.text[:200]}"}

        debug_print("CHECK TOKEN RESPONSE", data)

        if "error" in data:
            err = data["error"]
            err_data = err.get("error_data", "")
            try:
                err_data_obj = json.loads(err_data) if isinstance(err_data, str) else err_data
            except Exception:
                err_data_obj = {}
            checkpoint_flow_id = err_data_obj.get("checkpoint_flow_id", "")
            if checkpoint_flow_id == "601051028565049":
                return {"status": "checkpoint", "raw": data}
            return {"status": "die", "error": err.get("message", "Unknown error"), "raw": data}

        if "id" in data:
            return {"status": "live", "data": data}

        return {"status": "die", "error": "Unknown response", "raw": data}
    except requests.exceptions.RequestException as e:
        return {"status": "die", "error": f"Request error: {e}"}
    except Exception as e:
        return {"status": "die", "error": f"Exception: {e}"}


def clear_checkpoint_with_native_template(access_token: str, uid: str = "", proxy: Optional[str] = None) -> dict:
    url = "https://b-graph.facebook.com/graphql"

    headers = {
        'x-fb-rmd': 'state=URL_ELIGIBLE',
        'user-agent': '[FBAN/FB4A;FBAV/581.0.0.45.58;FBBV/1080624597;FBDM/{density=1.5,width=540,height=960};FBLC/vi_VN;FBRV/0;FBCR/MobiFone;FBMF/TDTOOL;FBBD/TDTOOL;FBPN/com.facebook.katana;FBDV/TDTOOl;FBSV/9;FBOP/1;FBCA/x86_64:arm64-v8a;]',
        'x-fb-friendly-name': 'NativeTemplateAsyncQuery',
        'x-zero-f-device-id': '5e4021a2-edf1-4e42-aae0-864aa7453a00',
        'x-graphql-client-library': 'graphservice',
        'x-meta-tasos-tlbwe-config': 'quic_transport_bwe:config_33_carrier_srs_nk',
        'x-fb-appnetsession-nid': '5a5cbfdd109f3ee0537c5c8667bed45f,Wifi',
        'x-fb-sim-hni': '45201',
        'content-type': 'application/x-www-form-urlencoded',
        'x-fb-navigation-chain': 'FbScreenFragment,internal,,1791393330.514,79501662,,,,1791393330.514;IXTEnrollmentActivity,,,1791393330.201,55947123,,,,1791393330.201;NewsFeedFragment,native_newsfeed,cold_start,1791393328.947,260276491,4748854339,,,1791393328.947',
        'authorization': f'OAuth {access_token}',
        'x-fb-connection-type': 'WIFI',
        'x-fb-net-hni': '45201',
        'x-meta-zca': 'empty_token',
        'app-scope-id-header': '5e4021a2-edf1-4e42-aae0-864aa7453a00',
        'x-meta-usdid': '6718039c-0c9e-4daf-b732-c16098b849c7.1791396936.MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEKnowhX53L_gAqEuzNUc4p4rHRF2qdDStEmXu0GYD-7CrhOmn_Duu_1NPrLEmyXROnpUYBjEq7b7ZggcDM5URZg.MEUCIC6IwlqUS8FPeqFgmpk6UnipwZnxLtp0_GIAPd3tQWFkAiEAqWVYRB0zGaI0Lio_R8IyDueGUuHm_NJoEuBQkTKIWkM',
        'x-fb-device-group': '639',
        'x-zero-eh': '2,,AXU7PSn2_R9SQw24B8XQ01Lyow8eA_l1i0Ede6Fs0JiCSJFl09Ag0pHDsA7sTbNx-cQ',
        'x-fb-integrity-machine-id': 'DX7GajRSKnR7lWe07shBRfsO',
        'x-meta-tasos-congestion-config': 'v6_1',
        'x-fb-network-properties': 'Wifi;Validated;',
        'priority': 'u=3, i',
        'x-fb-qpl-active-flows-json': '{"schema_version":"v3","inprogress_qpls":[{"marker_id":25952257,"annotations":{"current_endpoint":"FbScreenFragment:internal"}}],"snapshot_attributes":{}}',
        'x-meta-enable-tasos-ss-bwe': '1',
        'x-fb-tasos-experimental': '1',
        'x-fb-request-analytics-tags': '{"network_tags":{"product":"350685531728","request_category":"graphql","purpose":"none","retry_attempt":"0"},"application_tags":"graphservice"}',
        'x-fb-tasos-td-v2-config': 'prod_android',
        'x-meta-tasos-dcc-constraint': 'active=0;dcc=0;mit=0;alw=0;level=none;mode=0',
        'x-tigon-is-retry': 'False',
        'x-fb-appnetsession-sid': 'cbce8ef8983900adb373eab95bde520c',
        'x-fb-http-engine': 'Tigon/Liger',
        'x-fb-client-ip': 'True',
        'x-fb-server-cluster': 'True',
        'x-fb-conn-uuid-client': 'YyEC3khVoY4Zf2L4XuLEHQ==',
    }

    data = {
        'method': 'post',
        'format': 'json',
        'server_timestamps': 'true',
        'locale': 'vi_VN',
        'fb_api_req_friendly_name': 'NativeTemplateAsyncQuery',
        'fb_api_caller_class': 'graphservice',
        'client_doc_id': '30749539923215446186086828468',
        'fb_api_client_context': '{"is_background":false}',
        'variables': '{"params":{"payload":"nt/checkpoint/322333145742201/clear","nt_context":{"using_white_navbar":true,"styles_id":"0c28c2fb31d4e397db6494e82e716e1b","pixel_ratio":1.5,"is_push_on":true,"is_flipper_enabled":false,"android_device_performance_class":null,"debug_tooling_metadata_token":null,"gpu_memory_mb":null,"theme_params":[{"value":["BUTTON_LARGE_48X12_TEST","DARKER_PRIMARY_DEEMPHASIZED_BUTTON_BACKGROUND_TEST"],"design_system_name":"FDS"}],"bloks_version":"79a0afc68073f4ad82dc89dc1190ef093443a09f1b2cbe0c1e8d1ef4c5b3ef8e","android_os_api_level":28}},"nt_context":{"using_white_navbar":true,"styles_id":"0c28c2fb31d4e397db6494e82e716e1b","pixel_ratio":1.5,"is_push_on":true,"is_flipper_enabled":false,"android_device_performance_class":null,"debug_tooling_metadata_token":null,"gpu_memory_mb":null,"theme_params":[{"value":["BUTTON_LARGE_48X12_TEST","DARKER_PRIMARY_DEEMPHASIZED_BUTTON_BACKGROUND_TEST"],"design_system_name":"FDS"}],"bloks_version":"79a0afc68073f4ad82dc89dc1190ef093443a09f1b2cbe0c1e8d1ef4c5b3ef8e","android_os_api_level":28},"scale":"1.5","use_native_entrypoint_for_stars_on_reels":true,"profile_image_size":141,"include_image_ranges":true}',
        'fb_api_analytics_tags': '["GraphServices"]',
        'client_trace_id': 'cf6b38b5-75de-4a0f-9131-cd39318bdc73',
    }

    try:
        resp = requests.post(url, headers=headers, data=data, proxies=parse_proxy(proxy), timeout=25)
        text = resp.text

        debug_print("CLEAR CHECKPOINT RESPONSE", text)

        try:
            raw = resp.json()
        except Exception:
            return {"success": False, "error": f"Non-JSON response: {text[:200]}", "raw": text}

        try:
            bundles = raw.get("data", {}).get("native_templates_async", {}).get("native_template_bundles", None)
            if bundles is not None and len(bundles) == 0:
                return {"success": True, "empty_bundles": True, "raw": raw}
        except Exception:
            pass

        if "error" in raw:
            return {"success": False, "error": raw["error"].get("message", "Unknown error"), "raw": raw}

        return {"success": True, "empty_bundles": False, "raw": raw}

    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Request error: {e}"}
    except Exception as e:
        return {"success": False, "error": f"Exception: {e}"}


def ensure_token_live(uid: str, access_token: str, proxy: Optional[str] = None) -> dict:
    status = check_token_status(access_token, proxy=proxy)

    if status["status"] == "live":
        return {"ok": True, "status": "live"}

    if status["status"] == "die":
        return {"ok": False, "status": "die", "error": status.get("error", "Token die")}

    log_account(uid, "Token bị checkpoint 601051028565049, đang gỡ tự động...")
    clear_result = clear_checkpoint_with_native_template(access_token, uid=uid, proxy=proxy)

    if not clear_result.get("success"):
        return {
            "ok": False,
            "status": "checkpoint_fail",
            "error": f"Gỡ thất bại: {clear_result.get('error', 'Unknown')}"
        }

    time.sleep(3)
    status2 = check_token_status(access_token, proxy=proxy)

    if status2["status"] == "live":
        return {"ok": True, "status": "cleared"}

    if status2["status"] == "checkpoint":
        return {
            "ok": False,
            "status": "checkpoint_fail",
            "error": "Sau khi gỡ vẫn còn checkpoint"
        }

    return {
        "ok": False,
        "status": "die",
        "error": f"Sau khi gỡ token die: {status2.get('error', 'Unknown')}"
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


def gen_uuid():
    return str(uuid.uuid4()).upper()


def _gen_android_id():
    return ''.join(random.choice("0123456789abcdef") for _ in range(16))


def _gen_imei_android():
    base = "35" + ''.join(random.choice("0123456789") for _ in range(12))
    ds = [int(d) for d in base]
    total = 0
    for i, d in enumerate(reversed(ds)):
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return base + str((10 - total % 10) % 10)


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


def _build_cookie_from_session_keys(session_data: dict, uid: str) -> str:
    c_user = str(session_data.get('uid', uid))
    xs = session_data.get('session_key', '')
    if not xs:
        return ""
    parts = [f"c_user={c_user}"]
    if xs:
        parts.append(f"xs={xs}")
    datr = session_data.get('user_storage_key', '')
    if datr:
        parts.append(f"datr={datr}")
    fr = session_data.get('secret', '')
    if fr:
        parts.append(f"fr={fr}")
    return '; '.join(parts)


class FacebookPasswordEncryptor:
    @staticmethod
    def get_public_key(proxy: Optional[str] = None) -> Tuple[str, str, float]:
        url = 'https://b-graph.facebook.com/pwd_key_fetch'
        params = {
            'version': '2',
            'flow': 'CONTROLLER_INITIALIZATION',
            'method': 'GET',
            'fb_api_req_friendly_name': 'pwdKeyFetch',
            'fb_api_caller_class': 'com.facebook.auth.login.AuthOperations',
            'access_token': '350685531728|62f8ce9f74b12f84c123cc23437a4a32'
        }
        headers = {
            'User-Agent': 'okhttp/5.1.0',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip',
            'content-length': '0'
        }
        r = requests.post(url, params=params, headers=headers, proxies=parse_proxy(proxy), timeout=15)
        response = r.json()

        debug_print("PWD KEY FETCH RESPONSE", response)

        pub_key = response.get('public_key')
        key_id = str(response.get('key_id', '25'))

        server_ts = time.time()
        date_hdr = r.headers.get('Date')
        if date_hdr:
            try:
                server_ts = email.utils.parsedate_to_datetime(date_hdr).timestamp()
            except Exception:
                pass

        if not pub_key:
            raise Exception(f"Không nhận được public key: {response}")
        return pub_key, key_id, server_ts

    @staticmethod
    def encrypt(password: str, proxy: Optional[str] = None) -> Tuple[str, float]:
        public_key, key_id, server_ts = FacebookPasswordEncryptor.get_public_key(proxy)

        rand_key = get_random_bytes(32)
        iv = get_random_bytes(12)

        pubkey = RSA.import_key(public_key)
        cipher_rsa = PKCS1_v1_5.new(pubkey)
        encrypted_rand_key = cipher_rsa.encrypt(rand_key)

        cipher_aes = AES.new(rand_key, AES.MODE_GCM, nonce=iv)
        current_time = int(server_ts)
        cipher_aes.update(str(current_time).encode('utf-8'))
        (encrypted_passwd, auth_tag) = cipher_aes.encrypt_and_digest(password.encode('utf-8'))

        buf = io.BytesIO()
        buf.write(bytes([1, int(key_id)]))
        buf.write(iv)
        buf.write(struct.pack('<h', len(encrypted_rand_key)))
        buf.write(encrypted_rand_key)
        buf.write(auth_tag)
        buf.write(encrypted_passwd)

        encoded = base64.b64encode(buf.getvalue()).decode('utf-8')
        result = f'#PWD_FB4A:2:{current_time}:{encoded}'
        return result, server_ts


class FacebookLogin:
    GQL_URL = 'https://b-graph.facebook.com/graphql'
    AUTH_URL = 'https://b-graph.facebook.com/auth/login'
    ACCESS_TOKEN = '350685531728|62f8ce9f74b12f84c123cc23437a4a32'
    BLOKS_VERSION = '3469837656910fc29c9aa968ab33845cd52eb5253ae110610b944c8e9028d8f6'
    CLIENT_DOC_ID = '119940804214876861379510865434'
    TWO_FA_ENTRYPOINT_DOC_ID = '105373461558397492702779496'
    ATTESTATION_SIG = 'MEQCIDHrmQ86yvC7yeVBi0eYpIr2cnhtaSWxYm8I ZcZ081fAiBLzhHez6CMvaQqaFrCvfCMYker7WNLiQ4L99JpVR9K Q=='
    ATTESTATION_KEY = '9c620c1c59a053c07d9ce2f1166b1385e359254b6c461b3b55ca256d75e0976e'

    def __init__(self, uid_phone_mail: str, password: str, twofa_secret: Optional[str] = None, machine_id: Optional[str] = None, proxy: Optional[str] = None, device: Optional[dict] = None):
        self.uid_phone_mail = str(uid_phone_mail).strip()
        self.twofa_secret = re.sub(r'[\s\-]+', '', str(twofa_secret or '')).upper()
        self.raw_password = password
        self.proxy = proxy
        self.px_dict = parse_proxy(proxy)
        self.server_time_offset = 0.0

        if password.startswith('#PWD_FB4A'):
            self.password = password
        else:
            self.password, server_ts = FacebookPasswordEncryptor.encrypt(password, proxy=proxy)
            self.server_time_offset = server_ts - time.time()

        self.session = requests.Session()

        if device is None:
            device = gen_android_device("VN", "Asia/Ho_Chi_Minh")
        self.device = device

        self.device_id = device.get("device_id") or str(uuid.uuid4())
        self.secure_family_device_id = device.get("family_device_id") or str(uuid.uuid4())
        self.waterfall_id = str(uuid.uuid4())
        self.infra_flow_id = str(uuid.uuid4())
        self.client_trace_id = str(uuid.uuid4())
        self.machine_id = machine_id or device.get("machine_id") or ''

    def _get_server_now(self) -> float:
        return time.time() + self.server_time_offset

    def _build_attestation(self):
        nonce = base64.b64encode(get_random_bytes(32)).decode()
        data_json = json.dumps({'challenge_nonce': nonce, 'username': self.uid_phone_mail})
        return {
            'data': base64.b64encode(data_json.encode()).decode(),
            'signature': self.ATTESTATION_SIG,
            'keyHash': self.ATTESTATION_KEY
        }

    def _build_user_agent(self):
        d = self.device
        fbav = d.get("fbav", "542.0.0.46.151")
        fbbv = d.get("fbbv", "840338789")
        fbrv = d.get("fbrv", "0")
        model_id = d.get("model_id", "MTool-Max")
        brand = d.get("brand", "MTool-Max")
        os_ver = d.get("os_version", "9")
        locale = d.get("locale", "vi_VN")
        carrier = d.get("carrier", "MobiFone")
        dpi = d.get("density_dpi", 160)
        sw = d.get("screen_w", 300)
        sh = d.get("screen_h", 540)
        density = dpi / 160.0
        return (
            f"[FBAN/FB4A;FBAV/{fbav};FBBV/{fbbv};"
            f"FBDM/{{density={density:.2f},width={sw},height={sh}}};"
            f"FBLC/{locale};FBRV/{fbrv};"
            f"FBCR/{carrier};FBMF/{brand};FBBD/{brand};"
            f"FBPN/com.facebook.katana;"
            f"FBDV/{model_id};FBSV/{os_ver};"
            f"FBOP/1;FBCA/x86_64:arm64-v8a;]"
        )

    def _build_gql_headers(self):
        d = self.device
        return {
            'User-Agent': self._build_user_agent(),
            'Accept': 'application/json, text/json, text/x-json, text/javascript, application/xml, text/xml',
            'Accept-Encoding': 'gzip',
            'x-fb-connection-type': d.get("conn_type", "WIFI"),
            'x-fb-http-engine': 'Tigon/Liger',
            'x-fb-client-ip': 'True',
            'x-fb-server-cluster': 'True',
            'x-tigon-is-retry': 'False',
            'x-fb-device-group': str(random.randint(500, 6000)),
            'x-graphql-request-purpose': 'fetch',
            'x-fb-privacy-context': str(random.randint(3000000000000000, 3999999999999999)),
            'x-graphql-client-library': 'graphservice',
            'x-fb-net-hni': d.get("mccmnc", "45201"),
            'x-fb-sim-hni': d.get("sim_hni", "45201"),
            'authorization': f'OAuth {self.ACCESS_TOKEN}',
            'x-fb-request-analytics-tags': json.dumps({
                'network_tags': {
                    'product': '350685531728',
                    'purpose': 'fetch',
                    'request_category': 'graphql',
                    'retry_attempt': '0'
                },
                'application_tags': 'graphservice'
            })
        }

    def _build_client_input_params(self):
        d = self.device
        return {
            'password': self.password,
            'device_id': self.device_id,
            'family_device_id': self.device_id,
            'contact_point': self.uid_phone_mail,
            'login_attempt_count': 1,
            'event_flow': 'login_manual',
            'sim_phones': [],
            'secure_family_device_id': self.secure_family_device_id,
            'attestation_result': self._build_attestation(),
            'auth_secure_device_id': '',
            'has_whatsapp_installed': 0,
            'sso_token_map_json_string': '',
            'password_contains_non_ascii': 'false',
            'sim_serials': [],
            'client_known_key_hash': '',
            'encrypted_msisdn': '',
            'should_show_nested_nta_from_aymh': 0,
            'machine_id': self.machine_id,
            'flash_call_permission_status': {
                'READ_PHONE_STATE': 'DENIED',
                'READ_CALL_LOG': 'DENIED',
                'ANSWER_PHONE_CALLS': 'DENIED'
            },
            'accounts_list': [],
            'fb_ig_device_id': [],
            'device_emails': [],
            'try_num': 1,
            'lois_settings': {'lois_token': '', 'lara_override': ''},
            'event_step': 'home_page',
            'headers_infra_flow_id': self.infra_flow_id,
            'openid_tokens': {}
        }

    def _build_server_params(self):
        d = self.device
        return {
            'should_trigger_override_login_2fa_action': 0,
            'is_from_logged_out': 0,
            'should_trigger_override_login_success_action': 0,
            'login_credential_type': 'none',
            'server_login_source': 'login',
            'waterfall_id': self.waterfall_id,
            'login_source': 'Login',
            'is_platform_login': 0,
            'pw_encryption_try_count': 1,
            'INTERNAL__latency_qpl_marker_id': 36707139,
            'offline_experiment_group': 'caa_iteration_v6_perf_fb_2',
            'is_from_landing_page': 0,
            'password_text_input_id': 'nmi7ws:95',
            'is_from_empty_password': 0,
            'ar_event_source': 'login_home_page',
            'username_text_input_id': 'nmi7ws:94',
            'layered_homepage_experiment_group': None,
            'device_id': self.device_id,
            'INTERNAL__latency_qpl_instance_id': random.randint(100000000000000, 999999999999999),
            'reg_flow_source': 'login_home_native_integration_point',
            'is_caa_perf_enabled': 1,
            'credential_type': 'password',
            'is_from_password_entry_page': 0,
            'caller': 'gslr',
            'family_device_id': self.device_id,
            'INTERNAL_INFRA_THEME': 'harm_f',
            'is_from_assistive_id': 0,
            'access_flow_version': 'F2_FLOW',
            'is_from_logged_in_switcher': 0
        }

    def _build_payload(self):
        client_input = self._build_client_input_params()
        server_params = self._build_server_params()

        inner_params = json.dumps({
            'client_input_params': client_input,
            'server_params': server_params
        })
        variables = json.dumps({
            'params': {
                'params': inner_params,
                'bloks_versioning_id': self.BLOKS_VERSION,
                'app_id': 'com.bloks.www.bloks.caa.login.async.send_login_request'
            },
            'scale': '2',
            'nt_context': {
                'using_white_navbar': True,
                'styles_id': '964d559c1e2aa0142b5069bc8cb1adea',
                'pixel_ratio': 2,
                'is_push_on': True,
                'debug_tooling_metadata_token': None,
                'is_flipper_enabled': False,
                'theme_params': [],
                'bloks_version': self.BLOKS_VERSION
            }
        })
        return {
            'method': 'post',
            'pretty': 'false',
            'format': 'json',
            'server_timestamps': 'true',
            'locale': self.device.get("locale", "vi_VN"),
            'purpose': 'fetch',
            'fb_api_req_friendly_name': 'FbBloksActionRootQuery-com.bloks.www.bloks.caa.login.async.send_login_request',
            'fb_api_caller_class': 'graphservice',
            'client_doc_id': self.CLIENT_DOC_ID,
            'variables': variables,
            'fb_api_analytics_tags': '["GraphServices"]',
            'client_trace_id': self.client_trace_id,
            'generate_session_cookies': '1'
        }

    def _extract_token(self, text: str) -> Optional[str]:
        match = re.search(r'"access_token"\s*:\s*"([^"]+)"', text)
        if not match:
            match = re.search(r'access_token=([^&"\s]+)', text)
        if not match:
            match = re.search(r'access_token.*?([A-Za-z0-9:_-]{20,})', text)
        if match:
            return match.group(1)
        return None

    def _extract_session_data(self, text: str) -> Optional[dict]:
        try:
            patterns = [
                r'session_key\\*"\s*:\s*\\*"([^"\\]+)\\*"',
                r'"session_key"\s*:\s*"([^"]+)"',
            ]
            session_key = None
            for pat in patterns:
                m = re.search(pat, text)
                if m:
                    session_key = m.group(1)
                    break

            if not session_key:
                return None

            uid_match = re.search(r'uid\\*"\s*:\s*(\d+)', text)
            if not uid_match:
                uid_match = re.search(r'"uid"\s*:\s*(\d+)', text)

            secret_match = re.search(r'secret\\*"\s*:\s*\\*"([^"\\]+)\\*"', text)
            if not secret_match:
                secret_match = re.search(r'"secret"\s*:\s*"([^"]+)"', text)

            user_storage_match = re.search(r'user_storage_key\\*"\s*:\s*\\*"([^"\\]+)\\*"', text)
            if not user_storage_match:
                user_storage_match = re.search(r'"user_storage_key"\s*:\s*"([^"]+)"', text)

            return {
                'session_key': session_key,
                'uid': uid_match.group(1) if uid_match else '',
                'secret': secret_match.group(1) if secret_match else '',
                'user_storage_key': user_storage_match.group(1) if user_storage_match else ''
            }
        except Exception:
            return None

    def _extract_cookies_from_response(self, response_text: str) -> str:
        if not response_text:
            return ""

        session_data = self._extract_session_data(response_text)
        if session_data and session_data.get('session_key'):
            cookie_str = _build_cookie_from_session_keys(session_data, self.uid_phone_mail)
            if cookie_str:
                return cookie_str

        all_strings = []
        try:
            data = json.loads(response_text)
            _recursive_collect_strings(data, all_strings)
        except Exception:
            all_strings.append(response_text)

        all_strings.append(response_text)

        pairs = []
        seen_names = set()
        for s in all_strings:
            candidates = [s]
            unescaped = _unescape_many(s)
            if unescaped != s:
                candidates.append(unescaped)
            for cand in candidates:
                for name, value in _find_cookie_pairs_in_text(cand):
                    if name in seen_names:
                        continue
                    if not value:
                        continue
                    seen_names.add(name)
                    pairs.append((name, value))

        if not pairs:
            return ""

        ordered = []
        used = set()
        for want in COOKIE_ORDER:
            for name, value in pairs:
                if name == want and name not in used:
                    ordered.append(f"{name}={value}")
                    used.add(name)
                    break
        for name, value in pairs:
            if name not in used:
                ordered.append(f"{name}={value}")
                used.add(name)

        return '; '.join(ordered)

    def _extract_cookies_from_session(self) -> str:
        cookie_jar = self.session.cookies
        if not cookie_jar:
            return ""
        pairs = []
        seen = set()
        for c in cookie_jar:
            if c.name in seen:
                continue
            seen.add(c.name)
            pairs.append((c.name, c.value))
        ordered = []
        used = set()
        for want in COOKIE_ORDER:
            for name, value in pairs:
                if name == want and name not in used:
                    ordered.append(f"{name}={value}")
                    used.add(name)
                    break
        for name, value in pairs:
            if name not in used:
                ordered.append(f"{name}={value}")
                used.add(name)
        return '; '.join(ordered)

    def _call_2fa_entrypoint(self, two_step_verification_context: str, machine_id_2fa: str):
        screen_id = f'{uuid.uuid4().hex[:6]}:5'
        inner_params = json.dumps({
            'client_input_params': {
                'device_id': self.device_id,
                'is_whatsapp_installed': 0,
                'machine_id': machine_id_2fa
            },
            'server_params': {
                'family_device_id': self.device_id,
                'device_id': self.device_id,
                'two_step_verification_context': two_step_verification_context,
                'INTERNAL_INFRA_THEME': 'harm_f,default,harm_f',
                'flow_source': 'two_factor_login',
                'INTERNAL_INFRA_screen_id': screen_id
            }
        })
        variables = json.dumps({
            'params': {
                'params': inner_params,
                'bloks_versioning_id': self.BLOKS_VERSION,
                'is_on_load_actions_supported': True,
                'app_id': 'com.bloks.www.two_step_verification.entrypoint'
            },
            'scale': '2',
            'nt_context': {
                'using_white_navbar': True,
                'styles_id': '964d559c1e2aa0142b5069bc8cb1adea',
                'pixel_ratio': 2,
                'is_push_on': True,
                'debug_tooling_metadata_token': None,
                'is_flipper_enabled': False,
                'theme_params': [],
                'bloks_version': self.BLOKS_VERSION
            }
        })
        payload = {
            'method': 'post',
            'pretty': 'false',
            'format': 'json',
            'server_timestamps': 'true',
            'locale': self.device.get("locale", "vi_VN"),
            'purpose': 'fetch',
            'fb_api_req_friendly_name': 'FbBloksAppRootQuery-com.bloks.www.two_step_verification.entrypoint',
            'fb_api_caller_class': 'graphservice',
            'client_doc_id': self.TWO_FA_ENTRYPOINT_DOC_ID,
            'variables': variables,
            'fb_api_analytics_tags': '["GraphServices"]'
        }
        headers = self._build_gql_headers()
        self.session.post(self.GQL_URL, data=payload, headers=headers, proxies=self.px_dict, timeout=20)

    def _handle_2fa(self, two_step_verification_context: str, machine_id_2fa: str) -> dict:
        if not self.twofa_secret:
            return {
                'success': False,
                'api_failed': '2FA_VERIFY',
                'error': 'Tài khoản có bảo mật 2FA nhưng chưa cung cấp mã 2FA Secret'
            }

        try:
            self._call_2fa_entrypoint(two_step_verification_context, machine_id_2fa)

            server_now = self._get_server_now()
            totp = pyotp.TOTP(self.twofa_secret)
            twofactor_code = totp.at(server_now)

            safe_print(f"[2FA] | Debug OTP: {twofactor_code}")

            inner_params = json.dumps({
                'client_input_params': {
                    'auth_secure_device_id': '',
                    'machine_id': machine_id_2fa,
                    'code': twofactor_code,
                    'should_trust_device': 1,
                    'family_device_id': self.device_id,
                    'device_id': self.device_id
                },
                'server_params': {
                    'INTERNAL__latency_qpl_marker_id': 36707139,
                    'device_id': self.device_id,
                    'challenge': 'totp',
                    'machine_id': machine_id_2fa,
                    'INTERNAL__latency_qpl_instance_id': random.randint(100000000000000, 999999999999999),
                    'two_step_verification_context': two_step_verification_context,
                    'flow_source': 'two_factor_login'
                }
            })
            variables = json.dumps({
                'params': {
                    'params': inner_params,
                    'bloks_versioning_id': self.BLOKS_VERSION,
                    'app_id': 'com.bloks.www.two_step_verification.verify_code.async'
                },
                'scale': '2',
                'nt_context': {
                    'using_white_navbar': True,
                    'styles_id': '964d559c1e2aa0142b5069bc8cb1adea',
                    'pixel_ratio': 2,
                    'is_push_on': True,
                    'debug_tooling_metadata_token': None,
                    'is_flipper_enabled': False,
                    'theme_params': [],
                    'bloks_version': self.BLOKS_VERSION
                }
            })
            payload_2fa = {
                'method': 'post',
                'pretty': 'false',
                'format': 'json',
                'server_timestamps': 'true',
                'locale': self.device.get("locale", "vi_VN"),
                'purpose': 'fetch',
                'fb_api_req_friendly_name': 'FbBloksActionRootQuery-com.bloks.www.two_step_verification.verify_code.async',
                'fb_api_caller_class': 'graphservice',
                'client_doc_id': self.CLIENT_DOC_ID,
                'variables': variables,
                'fb_api_analytics_tags': '["GraphServices"]',
                'generate_session_cookies': '1'
            }
            headers = self._build_gql_headers()
            resp = self.session.post(self.GQL_URL, data=payload_2fa, headers=headers, proxies=self.px_dict, timeout=25)
            text = resp.text

            token = self._extract_token(text)
            if token:
                return self._build_success_result(token, text)

            bloks_err = None
            try:
                data_2fa = resp.json()
                inner_action = data_2fa.get('data', {}).get('fb_bloks_action', {}).get('root_action', {}).get('action', {}).get('action_bundle', {}).get('bloks_bundle_action', '')
                if inner_action:
                    m = re.search(r'BLOKS_TWO_STEP_VERIFICATION_ENTER_CODE:error_message\\*"\s*,\s*\\*"([^"\\]*(?:\\.[^"\\]*)*)', inner_action)
                    if m:
                        raw_escaped = m.group(1)
                        bloks_err = raw_escaped.encode('utf-8').decode('unicode_escape')
            except Exception:
                pass

            if bloks_err:
                return {'success': False, 'api_failed': '2FA_VERIFY', 'error': bloks_err, 'code_sent': twofactor_code}

            err_match = re.search(r'"error_message":"([^"]*)"', text)
            if err_match:
                return {'success': False, 'api_failed': '2FA_VERIFY', 'error': err_match.group(1), 'code_sent': twofactor_code}

            return {
                'success': False,
                'api_failed': '2FA_VERIFY',
                'error': 'Mã 2FA không chính xác hoặc đã hết hạn',
                'code_sent': twofactor_code
            }

        except Exception as e:
            return {'success': False, 'api_failed': '2FA_VERIFY', 'error': f'Lỗi ngoại lệ 2FA: {str(e)}'}

    def _build_success_result(self, token: str, response_text: str = "") -> dict:
        cookies = self._extract_cookies_from_response(response_text)
        if not cookies:
            cookies = self._extract_cookies_from_session()
        return {
            'success': True,
            'access_token': token,
            'cookies': cookies
        }

    def login(self) -> dict:
        try:
            headers = self._build_gql_headers()
            payload = self._build_payload()
            resp = self.session.post(self.GQL_URL, data=payload, headers=headers, proxies=self.px_dict, timeout=30)
            text = resp.text

            token = self._extract_token(text)
            if token:
                return self._build_success_result(token, text)

            if 'two_step_verification_context' in text or 'error_2fa' in text:
                dataJson = json.loads(text)
                inner = dataJson.get('data', {}).get('fb_bloks_action', {}).get('root_action', {}).get('action', {}).get('action_bundle', {}).get('bloks_bundle_action', '')
                ctx_match = re.search(r'two_step_verification_context.*?"([A-Za-z0-9_\-]{100,})', inner)
                mid_match = re.search(r'SaveMachineID[^A-Za-z0-9_-]+([A-Za-z0-9_-]{10,})', text)

                if ctx_match:
                    context = ctx_match.group(1)
                    machine_id_2fa = self.machine_id or (mid_match.group(1) if mid_match else '')
                    return self._handle_2fa(context, machine_id_2fa)
                else:
                    return {
                        'success': False,
                        'api_failed': 'LOGIN_PARSE_2FA_CONTEXT',
                        'error': 'Cần 2FA nhưng không bóc tách được two_step_verification_context',
                        'response_raw': text
                    }

            try:
                data = resp.json()
                errors = data.get('errors', [])
                if errors:
                    return {
                        'success': False,
                        'api_failed': 'LOGIN_GRAPHQL_ERROR',
                        'error': errors[0].get('message', 'Lỗi không xác định'),
                        'response_raw': text
                    }
            except Exception:
                pass

            err_match = re.search(r'"error_message":"([^"]*)"', text)
            if err_match:
                return {'success': False, 'api_failed': 'LOGIN_SEND_REQUEST', 'error': err_match.group(1), 'response_raw': text}

            msg_match = re.search(r'"message":"([^"]*)"', text)
            if msg_match:
                return {'success': False, 'api_failed': 'LOGIN_SEND_REQUEST', 'error': msg_match.group(1), 'response_raw': text}

            return {
                'success': False,
                'api_failed': 'LOGIN_NO_TOKEN',
                'error': 'Đăng nhập không thành công, không nhận được token',
                'response_raw': text
            }

        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'api_failed': 'REQUEST_CONNECTION_ERROR',
                'error': f'Lỗi kết nối mạng/proxy: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'api_failed': 'UNKNOWN_EXCEPTION',
                'error': str(e)
            }


def process_account(index, line, has_2fa, uid, password, twofa, cookie):
    machine_id = extract_datr_from_cookie(cookie)
    try:
        device = gen_android_device("VN", "Asia/Ho_Chi_Minh")
        fb = FacebookLogin(uid_phone_mail=uid, password=password, twofa_secret=twofa, machine_id=machine_id, proxy=None, device=device)
        result = fb.login()
        if result.get('success'):
            token = result['access_token']
            cookies = result.get('cookies', '')

            check = ensure_token_live(uid, token, proxy=None)

            if check.get("ok"):
                if check.get("status") == "cleared":
                    log_account(uid, "✅ Đã gỡ checkpoint tự động")
                elif check.get("status") == "live":
                    log_account(uid, "✅ Token live bình thường")

                if has_2fa:
                    out_line = f"{uid}|{password}|{twofa}|{cookies}|{token}"
                else:
                    out_line = f"{uid}|{password}|{cookies}|{token}"

                log_account(uid, "✅ Đăng nhập thành công")
                return index, True, [out_line]
            else:
                if check.get("status") == "checkpoint_fail":
                    log_account(uid, f"❌ Token vẫn bị checkpoint sau khi gỡ: {check.get('error')}")
                else:
                    log_account(uid, f"❌ Token die: {check.get('error')}")

                if has_2fa:
                    die_line = f"{uid}|{password}|{twofa}|{cookies}|{token}"
                else:
                    die_line = f"{uid}|{password}|{cookies}|{token}"

                return index, False, [die_line]
        else:
            error = result.get('error', 'Unknown error')
            log_account(uid, f"❌ Thất bại: {error}")
            return index, False, [line]
    except Exception as e:
        log_account(uid, f"❌ Ngoại lệ: {str(e)}")
        return index, False, [line]


def main():
    banner()
    print("\033[1mChọn chế độ nhập:\033[0m")
    print("\033[1m1. Nhập trực tiếp\033[0m")
    print("\033[1m2. Nhập từ file txt\033[0m")
    mode = bold_input("Chọn (1/2): ")

    success_accounts = []
    fail_accounts = []
    all_success_lines = []
    results = []

    if mode == '1':
        print("\033[1m\nNhập dòng dữ liệu:\033[0m")
        print("\033[1mHỗ trợ các định dạng:\033[0m")
        print("  - UID|PASS")
        print("  - UID|PASS|2FA")
        print("  - UID|PASS|COOKIE")
        print("  - UID|PASS|2FA|COOKIE")
        line = bold_input("> ")
        try:
            uid, pwd, twofa, cookie, has_2fa = parse_input_line(line)
        except ValueError as e:
            log_system(f"Lỗi: {e}")
            return

        log_system("Đang xử lý 1 tài khoản...")
        idx, success, lines = process_account(1, line, has_2fa, uid, pwd, twofa, cookie)
        if success:
            success_accounts.append(lines[0])
            all_success_lines.extend(lines)
        else:
            fail_accounts.append(lines[0])

    elif mode == '2':
        file_path = bold_input("Nhập đường dẫn file txt: ")
        if not os.path.exists(file_path):
            log_system(f"Không tìm thấy file: {file_path}")
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]

        total = len(lines)
        log_system(f"Đang xử lý {total} tài khoản...")

        tasks = []
        for idx, line in enumerate(lines, 1):
            try:
                uid, pwd, twofa, cookie, has_2fa = parse_input_line(line)
            except ValueError as e:
                log_system(f"Lỗi dòng {idx}: {e} - {line}")
                fail_accounts.append(line)
                continue
            tasks.append((idx, line, has_2fa, uid, pwd, twofa, cookie))

        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_idx = {}
            for task in tasks:
                idx, line, has_2fa, uid, pwd, twofa, cookie = task
                future = executor.submit(process_account, idx, line, has_2fa, uid, pwd, twofa, cookie)
                future_to_idx[future] = idx

            for future in as_completed(future_to_idx):
                idx, success, lines_result = future.result()
                results.append((idx, success, lines_result))

        results.sort(key=lambda x: x[0])
        for idx, success, lines_result in results:
            if success:
                success_accounts.append(lines_result[0])
                all_success_lines.extend(lines_result)
            else:
                fail_accounts.append(lines_result[0])

    else:
        log_system("Chế độ không hợp lệ")
        return

    success_count = len(success_accounts)
    fail_count = len(fail_accounts)
    log_system(f"Login Thành Công: {success_count} | Login Thất Bại: {fail_count}")

    if all_success_lines:
        with open("Acc_Live.txt", "w", encoding="utf-8") as f:
            for line in all_success_lines:
                f.write(line + "\n")
        log_system(f"Đã lưu {len(all_success_lines)} dòng vào Acc_Live.txt")
    else:
        log_system("Không có Acc nào thành công")

    if fail_accounts:
        with open("Acc_Die.txt", "w", encoding="utf-8") as f:
            for acc in fail_accounts:
                f.write(acc + "\n")
        log_system(f"Đã lưu {fail_count} Acc thất bại vào Acc_Die.txt")
    else:
        log_system("Không có Acc nào thất bại")


if __name__ == '__main__':
    main()
