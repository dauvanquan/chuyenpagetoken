# -*- coding: utf-8 -*-
import telebot
from telebot import types
import concurrent.futures
from datetime import datetime
import json
import os
import random
import re
import time
from time import sleep
import requests
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, Thread
import uuid
import base64
import io
import struct
import email.utils
import string

# ==================== IMPORT BẢO MẬT ====================
try:
    from Cryptodome.Cipher import AES, PKCS1_v1_5
    from Cryptodome.PublicKey import RSA
    from Cryptodome.Random import get_random_bytes
    _HAS_CRYPTO = True
except ImportError:
    try:
        from Crypto.Cipher import AES, PKCS1_v1_5
        from Crypto.PublicKey import RSA
        from Crypto.Random import get_random_bytes
        _HAS_CRYPTO = True
    except ImportError:
        _HAS_CRYPTO = False

try:
    import pyotp
    _HAS_PYOTP = True
except ImportError:
    _HAS_PYOTP = False

# ============================================
BOT_TOKEN = "8801430268:AAEjRi8SwHoi4YYYaFDI10eFuWH802x4YIM"      # <-- Thay token bot của bạn
ADMIN_IDS = [8483517282]               # <-- THAY ID CỦA BẠN VÀO ĐÂY
ALLOWED_FILE = "allowed_users.json"
# ============================================

bot = telebot.TeleBot(BOT_TOKEN)

user_data = {}
running_batches = {}
message_ids = {}
STOP_FLAGS = {}         
message_lock = Lock()
proxy_lock = Lock()

# ==================== AUTH & HELPERS ====================
def load_allowed_users():
    try:
        with open(ALLOWED_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {int(k): v for k, v in data.items()}
    except Exception:
        return {}

def save_allowed_users():
    try:
        with open(ALLOWED_FILE, 'w', encoding='utf-8') as f:
            json.dump(ALLOWED_USERS, f, indent=2)
    except Exception as e:
        print(f"[SAVE ERR] {e}")

ALLOWED_USERS = load_allowed_users()

def parse_duration(s):
    if not s: return None
    s = s.lower().strip()
    m = re.match(r'^(\d+)\s*(min|mo|[dhmy])$', s)
    if not m: return None
    val = int(m.group(1))
    if val <= 0: return None
    unit = m.group(2)
    now = time.time()
    if unit == 'min': return now + val * 60
    if unit == 'h':   return now + val * 3600
    if unit == 'd':   return now + val * 86400
    if unit in ('m', 'mo'): return now + val * 30 * 86400
    if unit == 'y':   return now + val * 365 * 86400
    return None

def format_remaining(expire_ts):
    if expire_ts is None: return "∞ Vĩnh viễn"
    diff = expire_ts - time.time()
    if diff <= 0: return "❌ Đã hết hạn"
    d = int(diff // 86400)
    h = int((diff % 86400) // 3600)
    m = int((diff % 3600) // 60)
    parts = []
    if d > 0: parts.append(f"{d}d")
    if h > 0: parts.append(f"{h}h")
    if m > 0 and d == 0: parts.append(f"{m}m")
    if not parts: parts.append(f"{int(diff)}s")
    return f"còn {' '.join(parts)}"

def format_datetime(ts):
    return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")

def is_admin(user_id): return user_id in ADMIN_IDS

def is_allowed(user_id):
    if user_id in ADMIN_IDS: return True
    if user_id not in ALLOWED_USERS: return False
    exp = ALLOWED_USERS[user_id]
    if exp is None: return True
    return time.time() <= exp

def no_permission_reply(chat_id, user_id):
    if user_id in ALLOWED_USERS:
        exp = ALLOWED_USERS[user_id]
        if exp is not None and time.time() > exp:
            bot.send_message(chat_id, f"❌ *Tài khoản của bạn đã hết hạn.*\n\n⏰ Hết hạn: `{format_datetime(exp)}`\n📝 ID: `{user_id}`", parse_mode="Markdown")
            return
    bot.send_message(chat_id, f"❌ *Bạn không có quyền.*\n\n📝 ID: `{user_id}`", parse_mode="Markdown")

def format_proxy(p):
    if not p: return None
    p = p.strip()
    parts = p.split(':')
    if len(parts) == 4:
        if parts[1].isdigit(): h, port, u, pw = parts
        else: u, pw, h, port = parts
        return f"http://{u}:{pw}@{h}:{port}"
    if len(parts) == 2:
        h, port = parts
        return f"http://{h}:{port}"
    return p

def parse_proxy(proxy_str):
    if not proxy_str or not str(proxy_str).strip(): return None
    p = str(proxy_str).strip()
    if p.startswith(('http://', 'https://', 'socks5://', 'socks4://')): return {'http': p, 'https': p}
    formatted = format_proxy(p)
    return {'http': formatted, 'https': formatted}

def get_real_ip(proxy_str):
    formatted = format_proxy(proxy_str)
    proxies = {"http": formatted, "https": formatted} if formatted else None
    try:
        r = requests.get("http://ip-api.com/json/?fields=query", proxies=proxies, timeout=10)
        if r.status_code == 200: return r.json().get('query', 'Unknown')
    except: pass
    return "Unknown"

def get_next_proxy(proxies_list, proxy_index_ref):
    with proxy_lock:
        proxy_index_ref[0] = (proxy_index_ref[0] + 1) % len(proxies_list)
        return proxies_list[proxy_index_ref[0]]

def get_consistent_device_fingerprint():
    chrome_versions = [("120.0.6099.144", "120"), ("121.0.6167.85", "121"), ("122.0.6261.94", "122"), ("123.0.6312.58", "123"), ("124.0.6367.60", "124")]
    v_full, v_major = random.choice(chrome_versions)
    platform = random.choice(['"Windows"', '"Macintosh"'])
    ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v_full} Safari/537.36"
    sec_ch_ua = f'"Chromium";v="{v_major}", "Google Chrome";v="{v_major}", "Not=A?Brand";v="99"'
    vw = str(random.choice([1366, 1440, 1536, 1920]))
    return ua, sec_ch_ua, platform, vw

def get_random_name(name_type):
    if name_type == "1":
        arrayho = ["Nguyễn","Trần","Lê","Phạm","Hoàng","Huỳnh","Võ","Vũ","Phan","Trương","Bùi","Đặng","Đỗ","Ngô","Hồ","Dương","Đinh"]
        arraylot = ["Văn","Gia","Hữu","Đình","Thanh","Minh","Tuấn","Hoàng"]
        arrayten = ["Hưng","Anh","Đạt","Tuấn","Long","Quốc","Nam","Giang","Khang","Dương","Phúc","Bảo","Khôi"]
        return f"{random.choice(arrayho)} {random.choice(arraylot)} {random.choice(arrayten)}"
    f = ["James","John","Robert","Michael","William","David","Richard","Joseph","Thomas","Charles","Mary","Patricia","Jennifer","Linda","Elizabeth"]
    l = ["Smith","Johnson","Williams","Brown","Jones","Miller","Davis","Garcia","Rodriguez","Wilson"]
    return f"{random.choice(f)} {random.choice(l)}"

def extract_cookie(line):
    if '|' in line:
        for p in line.split('|'):
            if 'c_user=' in p and 'xs=' in p: return p.strip()
    m = re.search(r'(c_user=\d+;[^|\n]+)', line)
    return m.group(1).strip() if m else line.strip()

# --- Parse Accounts (Dành cho Transfer/Delete) ---
def _is_token(s): return bool(s and re.match(r'^EAAAA[A-Za-z0-9_\-]{20,}$', s.strip()))
def _is_cookie(s): return bool(s and ';' in s and (('c_user=' in s) or ('xs=' in s) or ('datr=' in s)))
def _is_2fa(s):
    if not s: return False
    sl = s.strip().replace(' ', '').replace('-', '')
    if sl.startswith('EAAAA') or '=' in sl or ';' in sl: return False
    return bool(re.match(r'^[A-Za-z2-7]{16,64}$', sl))
def _is_probably_password(s): return bool(s and not (_is_token(s) or _is_cookie(s)))
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

def _looks_like_proxy(s):
    if not s: return False
    s = s.strip()
    if s.startswith(("http://", "https://", "socks")): return True
    if re.match(r'^[\w\.\-]+:\d{2,5}$', s): return True
    if re.match(r'^[\w\.\-]+:[\w\.\-]+@[\w\.\-]+:\d{2,5}$', s): return True
    if _split_4parts_proxy(s): return True
    return False

def parse_account_line(line):
    result = {"uid": "", "password": "", "twofa": "", "cookie": "", "token": "", "proxy": None}
    if not line: return result
    parts = [p.strip() for p in line.strip().split('|')]
    if not parts: return result
    result["uid"] = parts[0]
    rest = parts[1:]
    
    proxy_candidate = None
    for p in rest:
        if _looks_like_proxy(p) and not _is_token(p) and not _is_cookie(p) and not _is_2fa(p):
            proxy_candidate = p
            break
    if proxy_candidate:
        result["proxy"] = format_proxy(proxy_candidate)
        rest = [p for p in rest if p != proxy_candidate]

    for p in rest:
        if _is_token(p) and not result["token"]: result["token"] = p; continue
        if _is_cookie(p) and not result["cookie"]: result["cookie"] = p; continue
    for p in rest:
        if p in (result.get("token"), result.get("cookie")): continue
        if _is_2fa(p) and not result["twofa"]: result["twofa"] = p.strip().replace(' ', '').replace('-', '').upper(); continue
    for p in rest:
        if p in (result.get("token"), result.get("cookie")) or p == result.get("twofa"): continue
        if _is_probably_password(p) and not result["password"]: result["password"] = p; continue
    return result

# ==================== FACEBOOK API (TRANSFER/DELETE) ====================
UA_ANDROID = "[FBAN/FB4A;FBAV/555.0.0.49.59;FBBV/926292501;FBDM/{density=2.0,width=720,height=1280};FBLC/en_US;FBRV/0;FBCR/MobiFone;FBMF/Xiaomi;FBBD/Xiaomi;FBPN/com.facebook.katana;FBDV/2210132C;FBSV/14;FBOP/1;FBCA/x86:armeabi-v7a;]"
CLIENT_DOC_ID_OLD = "30749539926140469301601199541"
CLIENT_DOC_ID_ACCEPT_OLD = "30749539927629244093798192451"
CLIENT_DOC_ID_SCREEN_OLD = "221080835214205752894689842827"

NT_CONTEXT_OLD = {"using_white_navbar": True,"theme_params": [{"value": ["three_neutral_gray"], "design_system_name": "XMDS"},{"value": ["DARKER_PRIMARY_DEEMPHASIZED_BUTTON_BACKGROUND_TEST"], "design_system_name": "FDS"}],"styles_id": "6100e7e89411ccf67ace027cedecd84f","is_flipper_enabled": False, "pixel_ratio": 2, "is_push_on": True, "debug_tooling_metadata_token": None,"bloks_version": "d1583f026cccd22345fea8de656bb1d8162dabcca3249d6a0610be47545ec31a"}
NT_CONTEXT_ACCEPT = {"using_white_navbar": True, "styles_id": "588d028b36bed0e1889e09b60e0f9aea", "pixel_ratio": 2,"is_push_on": True, "debug_tooling_metadata_token": None, "is_flipper_enabled": False,"theme_params": [{"value": [], "design_system_name": "FDS"}],"bloks_version": "338f8ead5977a2c41eba3e92584dcf1d132e8b7928f1f5796662ec064023047d"}
FALLBACK_ADMIN_ROWS_FULL = '["slkbhp:2",null]'
FALLBACK_ENTRY_POINT = '["slgmzs:70",null]'
STATE_IDS_FULL_ADD = {"authenticated": "sobd7y:0","authentication_attempted": "sobd7y:1","show_entry_point_saving_spinner": "slkbhp:0","show_saving_spinner": "sobd7y:3","ads": "snzjoo:2","content": "snzjoo:3","insights": "snzjoo:4","messages": "snzjoo:5","moderate": "snzjoo:6"}
STATE_IDS_SELF_REMOVE = {"authenticated": "srik2l:0","authentication_attempted": "srik2l:1","show_saving_spinner": "srik2l:3"}

class FacebookPasswordEncryptor:
    @staticmethod
    def get_public_key(proxy=None):
        url = 'https://b-graph.facebook.com/pwd_key_fetch'
        params = {'version': '2','flow': 'CONTROLLER_INITIALIZATION','method': 'GET','fb_api_req_friendly_name': 'pwdKeyFetch','fb_api_caller_class': 'com.facebook.auth.login.AuthOperations','access_token': '438142079694454|fc0a7caa49b192f64f6f5a6d9643bb28'}
        headers = {'User-Agent': 'okhttp/5.1.0','Accept': 'application/json','Accept-Encoding': 'gzip','content-length': '0'}
        r = requests.post(url, params=params, headers=headers, proxies=parse_proxy(proxy), timeout=15)
        response = r.json()
        pub_key = response.get('public_key')
        key_id = str(response.get('key_id', '25'))
        server_ts = time.time()
        date_hdr = r.headers.get('Date')
        if date_hdr:
            try: server_ts = email.utils.parsedate_to_datetime(date_hdr).timestamp()
            except: pass
        if not pub_key: raise Exception(f"No Public Key: {response}")
        return pub_key, key_id, server_ts

    @staticmethod
    def encrypt(password, proxy=None):
        public_key, key_id, server_ts = FacebookPasswordEncryptor.get_public_key(proxy)
        rand_key = get_random_bytes(32); iv = get_random_bytes(12)
        pubkey = RSA.import_key(public_key); cipher_rsa = PKCS1_v1_5.new(pubkey)
        encrypted_rand_key = cipher_rsa.encrypt(rand_key)
        cipher_aes = AES.new(rand_key, AES.MODE_GCM, nonce=iv)
        current_time = int(server_ts)
        cipher_aes.update(str(current_time).encode('utf-8'))
        (encrypted_passwd, auth_tag) = cipher_aes.encrypt_and_digest(password.encode('utf-8'))
        buf = io.BytesIO()
        buf.write(bytes([1, int(key_id)])); buf.write(iv)
        buf.write(struct.pack('<h', len(encrypted_rand_key)))
        buf.write(encrypted_rand_key); buf.write(auth_tag); buf.write(encrypted_passwd)
        encoded = base64.b64encode(buf.getvalue()).decode('utf-8')
        return f'#PWD_FB4A:2:{current_time}:{encoded}', server_ts

class FacebookLoginAuthAPI:
    API_URL = "https://b-graph.facebook.com/auth/login"
    ACCESS_TOKEN = "350685531728|62f8ce9f74b12f84c123cc23437a4a32"
    API_KEY = "882a8490361da98702bf97a021ddc14d"
    SIG = "214049b9f17c38bd767de53752b53946"
    BASE_HEADERS = {"content-type": "application/x-www-form-urlencoded","user-agent": "[FBAN/FB4A;FBAV/542.0.0.46.151;FBBV/840338789;FBDM/{density=0.75,width=300,height=540};FBLC/vi_VN;FBRV/0;FBCR/MobiFone;FBMF/MTool-Max;FBBD/MTool-Max;FBPN/com.facebook.katana;FBDV/MTool-Max;FBSV/9;FBOP/1;FBCA/x86_64:arm64-v8a;]"}

    def __init__(self, uid, password, twofa="", machine_id=None, proxy=None):
        self.uid = str(uid).strip()
        self.twofa = re.sub(r'[\s\-]+', '', str(twofa or '')).upper()
        self.proxy = proxy
        self.px_dict = parse_proxy(proxy)
        if password.startswith("#PWD_FB4A"): self.password = password
        else: self.password, _ = FacebookPasswordEncryptor.encrypt(password, proxy=proxy)
        self.session = requests.Session()
        if self.px_dict: self.session.proxies.update(self.px_dict)
        self.device_id = str(uuid.uuid4()); self.adid = str(uuid.uuid4()); self.secure_family_device_id = str(uuid.uuid4())
        self.machine_id = machine_id if machine_id else ''.join(random.choices(string.ascii_letters + string.digits, k=24))
        self.jazoest = ''.join(random.choices(string.digits, k=5)); self.sim_serial = ''.join(random.choices(string.digits, k=20))
        self.headers = self.BASE_HEADERS.copy(); self.data = self._build_data()

    def _build_data(self):
        return {"format": "json", "email": self.uid, "password": self.password, "credentials_type": "password", "generate_session_cookies": "1","locale": "vi_VN", "client_country_code": "VN", "api_key": self.API_KEY, "access_token": self.ACCESS_TOKEN,"adid": self.adid, "device_id": self.device_id, "generate_analytics_claim": "1", "community_id": "", "linked_guest_account_userid": "","cpl": "true", "try_num": "1", "family_device_id": self.device_id, "secure_family_device_id": self.secure_family_device_id,"sim_serials": f'["{self.sim_serial}"]', "openid_flow": "ios_login", "openid_provider": "apple", "openid_tokens": "[]","account_switcher_uids": f'["{self.uid}"]', "fb4a_shared_phone_cpl_experiment": "fb4a_shared_phone_nonce_cpl_at_risk_v3","fb4a_shared_phone_cpl_group": "enable_v3_at_risk", "enroll_misauth": "false", "error_detail_type": "button_with_disabled","source": "login", "machine_id": self.machine_id, "jazoest": self.jazoest, "meta_inf_fbmeta": "V2_UNTAGGED","advertiser_id": self.adid, "encrypted_msisdn": "", "currently_logged_in_userid": "0", "fb_api_req_friendly_name": "authenticate","fb_api_caller_class": "Fb4aAuthHandler", "sig": self.SIG}

    def _build_result(self, response_json):
        cookies_dict = {}; cookies_str = ""
        if 'session_cookies' in response_json:
            for c in response_json['session_cookies']:
                cookies_dict[c['name']] = c['value']; cookies_str += f"{c['name']}={c['value']}; "
            cookies_str = cookies_str.rstrip('; ')
        return {'success': True, 'access_token': response_json.get('access_token'), 'cookies': cookies_str, 'cookies_dict': cookies_dict, 'user_id': response_json.get('user_id', '')}

    def _handle_2fa(self, error_data):
        if not self.twofa: return {'success': False, 'error': 'Cần 2FA Nhưng Chưa Cung Cấp'}
        try:
            twofactor_code = pyotp.TOTP(self.twofa).now()
            data_2fa = {'locale': 'vi_VN','format': 'json','email': self.uid,'device_id': self.device_id,'access_token': self.ACCESS_TOKEN,'generate_session_cookies': 'true','generate_machine_id': '1','twofactor_code': twofactor_code,'credentials_type': 'two_factor','error_detail_type': 'button_with_disabled','first_factor': error_data['login_first_factor'],'password': self.password,'userid': error_data['uid'],'machine_id': error_data['login_first_factor']}
            response = self.session.post(self.API_URL, data=data_2fa, headers=self.headers, timeout=30)
            response_json = response.json()
            if 'access_token' in response_json: return self._build_result(response_json)
            elif 'error' in response_json: return {'success': False, 'error': response_json['error'].get('message', 'Unknown Error')}
        except Exception as e: return {'success': False, 'error': f'Lỗi 2FA: {str(e)}'}

    def login(self):
        try:
            response = self.session.post(self.API_URL, headers=self.headers, data=self.data, timeout=30)
            response_json = response.json()
            if 'access_token' in response_json: return self._build_result(response_json)
            if 'error' in response_json:
                error_data = response_json.get('error', {}).get('error_data', {})
                if 'login_first_factor' in error_data and 'uid' in error_data: return self._handle_2fa(error_data)
                return {'success': False, 'error': response_json['error'].get('message', 'Unknown Error')}
            return {'success': False, 'error': 'Unknown Response Format'}
        except Exception as e: return {'success': False, 'error': str(e)}

def check_token_status(access_token, proxy=None):
    try:
        r = requests.get("https://graph.facebook.com/me", params={"access_token": access_token}, proxies=parse_proxy(proxy), timeout=20)
        data = r.json()
        if "error" in data: return {"status": "die", "error": data["error"].get("message", "Unknown Error")}
        if "id" in data: return {"status": "live", "data": data}
        return {"status": "die", "error": "Unknown Response"}
    except Exception as e: return {"status": "die", "error": f"Request Error: {e}"}

def login_get_token(uid, password, twofa, machine_id, proxy=None):
    if not _HAS_CRYPTO or (twofa and not _HAS_PYOTP): return {'ok': False, 'error': 'Thiếu thư viện Crypto/pyotp'}
    fb = FacebookLoginAuthAPI(uid=uid, password=password, twofa=twofa, machine_id=machine_id, proxy=proxy)
    result = fb.login()
    if result.get('success'): return {'ok': True, 'token': result['access_token'], 'cookie': result.get('cookies', '')}
    return {'ok': False, 'error': result.get('error', 'Unknown Error')}

def get_id(token):
    try:
        data = requests.get("https://graph.facebook.com/v24.0/me", params={"fields": "id,name", "access_token": token}, timeout=30).json()
        if "error" in data: return None
        return str(data.get("id")), data.get("name", "")
    except: return None

def _build_headers(token, friendly="NativeTemplateAsyncQuery"):
    return {"Accept-Encoding": "gzip","authorization": f"OAuth {token}","Connection": "Keep-Alive","Content-Type": "application/x-www-form-urlencoded; charset=utf-8","Host": "graph.facebook.com","user-agent": UA_ANDROID,"x-fb-friendly-name": friendly,"x-graphql-client-library": "graphservice"}

def _build_form_data(variables, friendly="NativeTemplateAsyncQuery", doc_id=CLIENT_DOC_ID_OLD, purpose="fetch", analytics_tags='["GraphServices"]'):
    return {"fb_api_client_context": '{"is_background":false}',"pretty": "false","variables": json.dumps(variables, ensure_ascii=False),"method": "post","client_doc_id": doc_id,"format": "json","server_timestamps": "true","locale": "en_US","fb_api_req_friendly_name": friendly,"fb_api_analytics_tags": analytics_tags,"client_trace_id": str(uuid.uuid4()),"fb_api_caller_class": "graphservice"}

def _fetch_all_pages_raw(token, profile_id):
    pages_dict = {}
    try:
        params_graph = {"fields": "id,name,access_token,additional_profile_id", "access_token": token}
        data = requests.get("https://graph.facebook.com/v24.0/me/accounts", params=params_graph, timeout=30).json()
        if isinstance(data, dict):
            for p in data.get("data", []):
                pid = str(p.get("id", ""))
                pages_dict[pid] = {"page_id": pid, "name": p.get("name", ""), "additional_profile_id": str(p.get("additional_profile_id", "") or pid), "access_token": p.get("access_token", "")}
    except: pass

    try:
        variables = {"profile_switcher_connection_first": 300, "additional_profile_picture_size": 80, "profileID": profile_id, "main_profile_picture_size": 80, "scale": "2", "nt_context": NT_CONTEXT_ACCEPT, "overflow_recent_searches_filter_ids": [], "use_native_entrypoint_for_stars_on_reels": True}
        data_sw = {"method": "post","pretty": "false","format": "json","server_timestamps": "true","locale": "vi_VN","client_doc_id": "116912609015732060545213902280","variables": json.dumps(variables, separators=(",", ":"))}
        result = requests.post("https://b-graph.facebook.com/graphql", headers=_build_headers(token), data=data_sw, timeout=30).json()
        if isinstance(result, dict):
            profiles = result.get("data", {}).get("user", {}).get("profile_switcher_eligible_profiles", {}).get("edges", [])
            for edge in profiles:
                node = edge.get("node", {}); prof = node.get("profile", {}); sinfo = node.get("session_info", {})
                prof_id = str(prof.get("id", "")); prof_name = prof.get("name", ""); sw_token = sinfo.get("access_token", "")
                matched = False
                for pid, item in pages_dict.items():
                    if item["additional_profile_id"] == prof_id or item["page_id"] == prof_id:
                        if sw_token: item["access_token"] = sw_token
                        matched = True; break
                if not matched and prof_id: pages_dict[prof_id] = {"page_id": prof_id, "name": prof_name, "additional_profile_id": prof_id, "access_token": sw_token}
    except: pass
    return list(pages_dict.values())

def get_all_pages(token, profile_id):
    return [{"page_uid": p["additional_profile_id"] or p["page_id"],"page_token": p["access_token"],"page_name": p["name"],"page_id": p["page_id"]} for p in _fetch_all_pages_raw(token, profile_id)]

def _payload_permissions_reauth(admin_id, profile_id, admin_type="full_access"):
    parts = ["/nt/profile/admin_management/permissions_reauth",f"admin_id={admin_id}",f"admin_rows_container_id={requests.utils.quote(FALLBACK_ADMIN_ROWS_FULL, safe='')}",f"admin_type={admin_type}",f"entry_point_screen_id={requests.utils.quote(FALLBACK_ENTRY_POINT, safe='')}",f"profile_id={profile_id}"]
    for k, v in STATE_IDS_FULL_ADD.items(): parts.append(f"state_ids%5B{k}%5D={v.replace(':', '%3A')}")
    return "?".join([parts[0], "&".join(parts[1:])])

def xac_nhan_mk(auth_token, admin_id, profile_id, password, admin_type="full_access"):
    headers = _build_headers(auth_token.replace("OAuth ", "").replace("Bearer ", "").strip())
    payload_string = _payload_permissions_reauth(admin_id, profile_id, admin_type)
    client_data = {"sensitive_string_value": json.dumps([["password", password]])}
    variables = {"params": {"nt_context": NT_CONTEXT_OLD,"payload": payload_string,"client_data": client_data},"scale": "2","nt_context": NT_CONTEXT_OLD,"profile_image_size": 188,"include_image_ranges": True,"use_native_entrypoint_for_stars_on_reels": True}
    try:
        resp_json = requests.post("https://graph.facebook.com/graphql", headers=headers, data=_build_form_data(variables, doc_id=CLIENT_DOC_ID_OLD), timeout=30).json()
        if "errors" in resp_json: return None, "Sai MK/Reauth"
        return resp_json["data"]["native_templates_async"]["native_template_bundles"][0]["nt_bundle_tree"], None
    except Exception as e: return None, "Lỗi Reauth"

def extract_payload_from_tree(nt_bundle_tree):
    if not nt_bundle_tree: return None
    m = re.search(r'(/nt/profile/admin_management/permissions/update\?[^"\'\\}]+)', nt_bundle_tree)
    if m: return m.group(1).replace(r'\/', '/')
    return None

def gui_loi_moi(auth_token, nt_bundle_tree, profile_id, target_admin_id, admin_type="full_access"):
    payload = extract_payload_from_tree(nt_bundle_tree)
    if not payload:
        parts = ["/nt/profile/admin_management/permissions/update",f"admin_rows_container_id={requests.utils.quote(FALLBACK_ADMIN_ROWS_FULL, safe='')}",f"entry_point_screen_id={requests.utils.quote(FALLBACK_ENTRY_POINT, safe='')}",f"admin_type={admin_type}",f"profile_id={profile_id}",f"target_admin_id={target_admin_id}","secured_sensitive_actions%5B0%5D=page_admin_access_addition"]
        for k, v in STATE_IDS_FULL_ADD.items(): parts.append(f"state_ids%5B{k}%5D={v.replace(':', '%3A')}")
        payload = "?".join([parts[0], "&".join(parts[1:])])
    
    state_data = {"ads": False, "insights": False, "messages": False, "show_entry_point_saving_spinner": "NONE", "content": False, "moderate": False}
    variables = {"params": {"payload": payload,"state_data": json.dumps(state_data),"nt_context": NT_CONTEXT_OLD},"nt_context": NT_CONTEXT_OLD,"scale": "2","profile_image_size": 188,"include_image_ranges": True,"use_native_entrypoint_for_stars_on_reels": True}
    try:
        resp_json = requests.post("https://graph.facebook.com/graphql", headers=_build_headers(auth_token), data=_build_form_data(variables, doc_id=CLIENT_DOC_ID_OLD), timeout=30).json()
        if "errors" in resp_json:
            err = resp_json["errors"][0]
            if err.get("code") == 1357004 or "pending" in str(err).lower(): return True, True, None # Đã có lời mời
            return False, False, "Lỗi gửi lời mời"
        return True, False, None
    except: return False, False, "Lỗi gửi lời mời"

def ktra_loi_moi(auth_token, profile_id, invitee_id):
    params_str = json.dumps({"screen_id": '["sz9fnp:17",null]',"profile_id": profile_id,"invitee_id": invitee_id})
    variables = {"params": {"nt_context": NT_CONTEXT_ACCEPT,"path": "/nt/profile/admin_management/invitation","params": params_str,"extra_client_data": {}},"scale": "2","use_native_entrypoint_for_stars_on_reels": True,"nt_context": NT_CONTEXT_ACCEPT}
    data = {"pretty": "false","variables": json.dumps(variables, ensure_ascii=False),"method": "post","client_doc_id": CLIENT_DOC_ID_SCREEN_OLD,"purpose": "fetch","format": "json","server_timestamps": "true","locale": "vi_VN","fb_api_req_friendly_name": "NativeTemplateScreenQuery","client_trace_id": str(uuid.uuid4()),"fb_api_client_context": '{"is_background":false}',"fb_api_analytics_tags": '["surfaces.fb.GraphServiceEmitter","GraphServices"]',"fb_api_caller_class": "graphservice"}
    try:
        res = requests.post("https://graph.facebook.com/graphql", headers=_build_headers(auth_token, "NativeTemplateScreenQuery"), data=data, timeout=30).json()
        res_str = json.dumps(res)
        m = re.search(r'invitation_id[\\"\':=]+(\d+)', res_str)
        if m: return m.group(1), "full_access"
        return None, None
    except: return None, None

def xac_nhan_loi_moi(auth_token, invitation_id, admin_type="full_access"):
    payload = f"/nt/profile/admin_management/invitation_response?accept_invitation=1&invitation_id={invitation_id}&admin_type={admin_type}"
    variables = {"params": {"payload": payload,"nt_context": NT_CONTEXT_ACCEPT},"nt_context": NT_CONTEXT_ACCEPT,"scale": "2","use_native_entrypoint_for_stars_on_reels": True,"profile_image_size": 188,"include_image_ranges": True}
    try:
        resp = requests.post("https://graph.facebook.com/graphql", headers=_build_headers(auth_token), data=_build_form_data(variables, doc_id=CLIENT_DOC_ID_ACCEPT_OLD), timeout=30).json()
        return "errors" not in resp
    except: return False

def xac_nhan_mk_xoa(auth_token, uid_bi_xoa, profile_id, uid_viewer, password):
    headers = _build_headers(auth_token.replace("OAuth ", "").replace("Bearer ", "").strip())
    admin_row_id = '["srf5xe:6",true]'; admin_rows = '["srf5xe:2",null]'
    parts = ["/nt/profile/admin_management/remove_admin_reauth",f"admin_id={uid_bi_xoa}",f"admin_row_id={requests.utils.quote(admin_row_id, safe='')}",f"admin_rows_container_id={requests.utils.quote(admin_rows, safe='')}",f"admin_type=full_access",f"entry_point_screen_id={requests.utils.quote(FALLBACK_ENTRY_POINT, safe='')}",f"profile_id={profile_id}",f"underlying_viewer_id={uid_viewer}"]
    for k, v in STATE_IDS_SELF_REMOVE.items(): parts.append(f"state_ids%5B{k}%5D={v.replace(':', '%3A')}")
    payload_string = "?".join([parts[0], "&".join(parts[1:])])
    client_data = {"sensitive_string_value": json.dumps([["password", password]])}
    variables = {"params": {"nt_context": NT_CONTEXT_OLD,"payload": payload_string,"client_data": client_data},"scale": "2","nt_context": NT_CONTEXT_OLD,"profile_image_size": 188,"include_image_ranges": True,"use_native_entrypoint_for_stars_on_reels": True}
    try:
        resp_json = requests.post("https://graph.facebook.com/graphql", headers=headers, data=_build_form_data(variables, doc_id=CLIENT_DOC_ID_OLD), timeout=30).json()
        if "errors" in resp_json: return None
        return resp_json["data"]["native_templates_async"]["native_template_bundles"][0]["nt_bundle_tree"]
    except: return None

def xoa_admin(auth_token, profile_id, uid_bi_xoa):
    headers = _build_headers(auth_token)
    admin_row_id = '["srf5xe:6",true]'; admin_rows = '["srf5xe:2",null]'
    parts = ["/nt/profile/admin_management/remove_admin",f"admin_row_id={requests.utils.quote(admin_row_id, safe='')}",f"admin_rows_container_id={requests.utils.quote(admin_rows, safe='')}",f"entry_point_screen_id={requests.utils.quote(FALLBACK_ENTRY_POINT, safe='')}",f"admin_type=full_access",f"full_access=1",f"profile_id={profile_id}",f"target_admin_id={uid_bi_xoa}","secured_sensitive_actions%5B0%5D=page_admin_access_self_removal"]
    payload = "?".join([parts[0], "&".join(parts[1:])])
    variables = {"params": {"nt_context": NT_CONTEXT_OLD,"payload": payload},"nt_context": NT_CONTEXT_OLD,"scale": "2","profile_image_size": 188,"include_image_ranges": True,"use_native_entrypoint_for_stars_on_reels": True}
    try:
        resp_json = requests.post("https://graph.facebook.com/graphql", headers=headers, data=_build_form_data(variables, doc_id=CLIENT_DOC_ID_OLD), timeout=30).json()
        return "errors" not in resp_json
    except: return False

# ==================== STATUS UPDATE & THREADS ====================
def update_status(chat_id, thread_id, text):
    key = (chat_id, thread_id)
    with message_lock:
        mid = message_ids.get(key)
    if mid:
        try:
            bot.edit_message_text(text, chat_id, mid, disable_web_page_preview=True)
            return
        except Exception as e:
            err = str(e).lower()
            if "message is not modified" in err: return
            if "429" in err:
                time.sleep(2) 
                try: bot.edit_message_text(text, chat_id, mid, disable_web_page_preview=True); return
                except: pass
    try:
        m = bot.send_message(chat_id, text, disable_web_page_preview=True)
        with message_lock: message_ids[key] = m.message_id
    except: pass

def reset_messages(chat_id):
    with message_lock:
        for k in [k for k in message_ids if k[0] == chat_id]: del message_ids[k]

def _ensure_token(chat_id, thread_id, acc, results_dict):
    uid_file, password, cookie, twofa, token, px = acc.get("uid", ""), acc.get("password", ""), acc.get("cookie", ""), acc.get("twofa", ""), acc.get("token", ""), acc.get("proxy")
    def status(text, emoji="🔄"):
        update_status(chat_id, thread_id, f"{emoji} L{thread_id}: {uid_file} | {text}")

    if not token:
        if not uid_file or not password:
            status("Thiếu pass để login", "❌")
            results_dict[thread_id] = {"status": "fail", "reason": "Thiếu pass/login", "ok": 0, "fail": 1}
            return None
        status("Login FB4A...")
        machine_id_login = ""
        if cookie:
            m = re.search(r'datr=([^;]+)', cookie)
            if m: machine_id_login = m.group(1)
        lg = login_get_token(uid_file, password, twofa, machine_id_login, proxy=px)
        if not lg.get("ok"):
            status(f"Login fail: {lg.get('error', '')[:50]}", "❌")
            results_dict[thread_id] = {"status": "fail", "reason": "Login fail", "ok": 0, "fail": 1}
            return None
        token = lg["token"]
        if check_token_status(token, proxy=px)["status"] != "live":
            status("Token die", "❌")
            results_dict[thread_id] = {"status": "fail", "reason": "Token die", "ok": 0, "fail": 1}
            return None
        status("Login OK", "✅")
    else:
        status("Verify token...")
        if check_token_status(token, proxy=px)["status"] != "live":
            if not uid_file or not password:
                status("Token die, không có pass", "❌")
                results_dict[thread_id] = {"status": "fail", "reason": "Token die", "ok": 0, "fail": 1}
                return None
            status("Token die, login lại...")
            machine_id_login = ""
            if cookie:
                m = re.search(r'datr=([^;]+)', cookie)
                if m: machine_id_login = m.group(1)
            lg = login_get_token(uid_file, password, twofa, machine_id_login, proxy=px)
            if not lg.get("ok") or check_token_status(lg["token"], proxy=px)["status"] != "live":
                status("Token die", "❌")
                results_dict[thread_id] = {"status": "fail", "reason": "Token die", "ok": 0, "fail": 1}
                return None
            token = lg["token"]
    return token

def run_transfer_account(chat_id, thread_id, acc, id_nhan, token_nhan, auto_accept, delay, results_dict):
    uid = acc['uid']
    token = _ensure_token(chat_id, thread_id, acc, results_dict)
    if not token: return
    
    pages = get_all_pages(token, uid)
    total = len(pages)
    if not pages:
        update_status(chat_id, thread_id, f"❌ L{thread_id}: {uid} | Không có Page")
        results_dict[thread_id] = {"status": "fail", "reason": "Không có Page", "ok": 0, "fail": 1}
        return
        
    last_msg = ""
    ok_count = 0
    fail_count = 0
    error_reasons = set()
    
    for i, page in enumerate(pages, 1):
        if STOP_FLAGS.get(chat_id): 
            results_dict[thread_id] = {"status": "stop", "reason": "Dừng khẩn cấp", "ok": ok_count, "fail": fail_count + (total-i+1)}
            return
            
        pname, puid, ptoken = page['page_name'], page['page_uid'], page['page_token']
        
        update_status(chat_id, thread_id, f"🔄 L{thread_id}: {uid} | ({i}/{total}) | Đang xử lý: {pname}")
        
        nt_tree, err_reauth = xac_nhan_mk(ptoken, id_nhan, puid, acc['password'])
        if not nt_tree:
            last_msg = f"❌ L{thread_id}: {uid} | ({i}/{total}) | {err_reauth} {pname}"
            error_reasons.add(err_reauth)
            fail_count += 1
        else:
            step2_ok, pending, err_invite = gui_loi_moi(ptoken, nt_tree, puid, id_nhan)
            if not step2_ok:
                last_msg = f"❌ L{thread_id}: {uid} | ({i}/{total}) | {err_invite} {pname}"
                error_reasons.add(err_invite)
                fail_count += 1
            else:
                if auto_accept and token_nhan:
                    inv_id, admin_type = ktra_loi_moi(token_nhan, puid, id_nhan)
                    if inv_id and xac_nhan_loi_moi(token_nhan, inv_id, admin_type):
                        last_msg = f"✅ L{thread_id}: {uid} | ({i}/{total}) | Chuyển thành công page {pname}"
                        ok_count += 1
                    else:
                        last_msg = f"❌ L{thread_id}: {uid} | ({i}/{total}) | Lỗi accept {pname}"
                        error_reasons.add("Lỗi Accept")
                        fail_count += 1
                else:
                    last_msg = f"✅ L{thread_id}: {uid} | ({i}/{total}) | Đã gửi lời mời {pname}"
                    ok_count += 1
        
        if i < total:
            update_status(chat_id, thread_id, last_msg + f"\n⏳ Chờ {delay}s...")
            for _ in range(int(delay)):
                if STOP_FLAGS.get(chat_id): break
                time.sleep(1)
        else:
            update_status(chat_id, thread_id, last_msg)
            
    reason_str = ", ".join(error_reasons) if error_reasons else ""
    results_dict[thread_id] = {"status": "done", "reason": reason_str, "ok": ok_count, "fail": fail_count}

def run_delete_account(chat_id, thread_id, acc, delay, results_dict):
    uid = acc['uid']
    token = _ensure_token(chat_id, thread_id, acc, results_dict)
    if not token: return
    
    pages = get_all_pages(token, uid)
    total = len(pages)
    if not pages:
        update_status(chat_id, thread_id, f"❌ L{thread_id}: {uid} | Không có Page")
        results_dict[thread_id] = {"status": "fail", "reason": "Không có Page", "ok": 0, "fail": 1}
        return
        
    last_msg = ""
    ok_count = 0
    fail_count = 0
    error_reasons = set()
    
    for i, page in enumerate(pages, 1):
        if STOP_FLAGS.get(chat_id):
            results_dict[thread_id] = {"status": "stop", "reason": "Dừng khẩn cấp", "ok": ok_count, "fail": fail_count + (total-i+1)}
            return
            
        pname, puid, ptoken = page['page_name'], page['page_uid'], page['page_token']
        
        update_status(chat_id, thread_id, f"🔄 L{thread_id}: {uid} | ({i}/{total}) | Đang xoá: {pname}")
        
        nt_tree = xac_nhan_mk_xoa(ptoken, uid, puid, uid, acc['password'])
        if not nt_tree:
            last_msg = f"❌ L{thread_id}: {uid} | ({i}/{total}) | Sai MK/Reauth {pname}"
            error_reasons.add("Sai MK/Reauth")
            fail_count += 1
        else:
            if xoa_admin(ptoken, puid, uid):
                last_msg = f"✅ L{thread_id}: {uid} | ({i}/{total}) | Xoá thành công page {pname}"
                ok_count += 1
            else:
                last_msg = f"❌ L{thread_id}: {uid} | ({i}/{total}) | Lỗi xoá {pname}"
                error_reasons.add("Lỗi xoá")
                fail_count += 1
                
        if i < total:
            update_status(chat_id, thread_id, last_msg + f"\n⏳ Chờ {delay}s...")
            for _ in range(int(delay)):
                if STOP_FLAGS.get(chat_id): break
                time.sleep(1)
        else:
            update_status(chat_id, thread_id, last_msg)
            
    reason_str = ", ".join(error_reasons) if error_reasons else ""
    results_dict[thread_id] = {"status": "done", "reason": reason_str, "ok": ok_count, "fail": fail_count}

# ==================== REG PAGE CORE ====================
class reg_pro5:
    def __init__(self, cookies, proxy=None):
        self.cookies = cookies
        self.update_proxy(proxy)
        ua, sec_ch_ua, platform, vw = get_consistent_device_fingerprint()
        self.ua, self.sec_ch_ua, self.platform, self.viewport_width = ua, sec_ch_ua, platform, vw
        try: self.id_acc = self.cookies.split('c_user=')[1].split(';')[0]
        except: self.id_acc = ""
        self.headers = {"authority": "www.facebook.com","accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8","accept-language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7","cookie": self.cookies,"sec-ch-prefers-color-scheme": "light","sec-ch-ua": self.sec_ch_ua,"sec-ch-ua-mobile": "?0","sec-ch-ua-platform": self.platform,"sec-fetch-dest": "document","sec-fetch-mode": "navigate","sec-fetch-site": "none","sec-fetch-user": "?1","upgrade-insecure-requests": "1","user-agent": self.ua,"viewport-width": self.viewport_width}
        self.fb_dtsg = ""; self.lsd = "AVr-4211_Q"; self.__rev = "1011500000"; self.__hs = "19783.HYP:comet_pkg.2.1.0.2.1"
        self.refresh_session_info()

    def update_proxy(self, proxy):
        self.proxy = proxy; self.formatted_proxy = format_proxy(proxy)
        self.proxies_dict = ({"http": self.formatted_proxy, "https": self.formatted_proxy} if self.formatted_proxy else None)
        if not hasattr(self, 'session') or self.session is None: self.session = requests.Session()
        if self.proxies_dict: self.session.proxies.update(self.proxies_dict)
        else: self.session.proxies.clear()

    def refresh_session_info(self):
        try:
            res_me = self.session.get("https://www.facebook.com/me", headers=self.headers, timeout=15)
            url_profile = res_me.url
            if "checkpoint" in url_profile or "login" in url_profile: return
            profile = self.session.get(url_profile, headers=self.headers, timeout=15).text
            if 'DTSGInitialData' in profile:
                try: self.fb_dtsg = profile.split('"token":"')[1].split('"')[0]
                except: self.fb_dtsg = profile.split('{"name":"fb_dtsg","value":"')[1].split('"}')[0]
            elif '["DTSGInitData",[],{"token":"' in profile: self.fb_dtsg = profile.split('["DTSGInitData",[],{"token":"')[1].split('"')[0]
            else:
                try: self.fb_dtsg = profile.split('{"name":"fb_dtsg","value":"')[1].split('"}')[0]
                except: self.fb_dtsg = profile.split(',"f":"')[1].split('","l":null}')[0]
            try: self.lsd = profile.split('["LSD",[],{"token":"')[1].split('"')[0]
            except: pass
            m = re.search(r'"rev":\s*(\d+)', profile)
            if m: self.__rev = m.group(1)
            m = re.search(r'"client_revision":\s*"([^"]+)"', profile)
            if m: self.__hs = m.group(1)
        except: pass

    def Reg(self, name):
        if not self.fb_dtsg or not self.id_acc: return {"error": "Lấy fb_dtsg thất bại (die cookie/checkpoint/proxy)"}
        h = {"authority": "www.facebook.com", "accept": "*/*","accept-language": "vi-VN,vi;q=0.9", "cookie": self.cookies,"origin": "https://www.facebook.com","referer": "https://www.facebook.com/pages/creation?ref_type=launch_point","sec-ch-prefers-color-scheme": "light", "sec-ch-ua": self.sec_ch_ua,"sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": self.platform,"sec-fetch-dest": "empty", "sec-fetch-mode": "cors", "sec-fetch-site": "same-origin","user-agent": self.ua, "x-fb-friendly-name": "AdditionalProfilePlusCreationMutation","x-fb-lsd": self.lsd}
        d = {"av": self.id_acc, "__user": self.id_acc, "__a": "1","__dyn": "7AzHxq1mxu1syUbFuC0BVU98nwgU29zEdEc8co5S3O2S7o11Ue8hw6vwb-q7oc81xoswIwuo886C11xmfz81sbzoaEnxO0Bo7O2l2Utwwwi831wiEjwZwlo5qfK6E7e58jwGzE8FU5e7oqBwJK2W5olwuEjUlDw-wUws9ovUaU3qxWm2Sq2-azo2NwkQ0z8c84K2e3u362-2B0oobo","__csr": "gP4ZAN2d-hbbRmLObkZO8LvRcXWVvth9d9GGXKSiLCqqr9qEzGTozAXiCgyBhbHrRG8VkQm8GFAfy94bJ7xeufz8jK8yGVVEgx-7oiwxypqCwgF88rzKV8y2O4ocUak4UpDxu3x1K4opAUrwGx63J0Lw-wa90eG18wkE7y14w4hw6Bw2-o069W00CSE0PW06aU02Z3wjU6i0btw3TE1wE5u","__req": "t", "__hs": self.__hs,"dpr": str(random.choice([1, 1.25, 1.5])),"__ccg": "EXCELLENT", "__rev": self.__rev,"__s": f"{random.choice('abc')}{random.randint(1000,9999)}:x{random.randint(100,999)}","__hsi": str(random.randint(7200000000000000000, 7300000000000000000)),"__comet_req": "15", "fb_dtsg": self.fb_dtsg,"jazoest": str(random.randint(20000, 28000)), "lsd": self.lsd,"__aaid": "800444344545377","__spin_r": self.__rev, "__spin_b": "trunk","__spin_t": str(int(datetime.now().timestamp())),"fb_api_caller_class": "RelayModern","fb_api_req_friendly_name": "AdditionalProfilePlusCreationMutation","variables": json.dumps({"input": {"bio": "", "categories": ["181475575221097"],"creation_source": "comet", "name": name,"page_referrer": "launch_point", "actor_id": self.id_acc,"client_mutation_id": str(random.randint(1, 999999))}}),"server_timestamps": "true", "doc_id": "5903223909690825"}
        try:
            resp = self.session.post("https://www.facebook.com/api/graphql/", headers=h, data=d, timeout=20)
            raw = resp.text.strip()
            if not raw: return {"error": "Phản hồi trống"}
            if raw.startswith("for (;;);"): raw = raw[9:].strip()
            return json.loads(raw)
        except Exception as e: return {"error": str(e)}

def run_reg_account(chat_id, thread_id, raw_line, initial_proxy, proxies_list, proxy_index_ref, sl_pro5, dl, name_type, avatar_mode, custom_link):
    current_ip = ["..."]
    last_success_line = ""  

    def status(text, emoji="🔄", ip=None, is_success=False):
        nonlocal last_success_line
        ip_val = ip if ip is not None else current_ip[0]
        if is_success:
            last_success_line = f"{emoji} L{thread_id}: IP: {ip_val}  {text}"
            update_status(chat_id, thread_id, last_success_line); return
        current_line = f"{emoji} {text}" if text.startswith(("Chờ", "Đang tạo")) else f"{emoji} L{thread_id}: IP: {ip_val}  {text}"
        final_text = f"{last_success_line}\n{current_line}" if last_success_line else current_line
        update_status(chat_id, thread_id, final_text)

    if STOP_FLAGS.get(chat_id): return
    status("Đang khởi tạo...", "🔄", "...")
    try:
        cookie = extract_cookie(raw_line)
        if not cookie or 'c_user=' not in cookie:
            status(f"Cookie không hợp lệ: {raw_line[:30]}...", "❌"); return
        current_proxy = initial_proxy; current_ip[0] = get_real_ip(current_proxy)
        status("Đang đăng nhập Facebook...", "🔄")
        client = reg_pro5(cookie, current_proxy)
        if not client.id_acc or not client.fb_dtsg:
            status("Cookie die/Checkpoint - thử đổi proxy...", "⚠️")
            if proxies_list:
                current_proxy = get_next_proxy(proxies_list, proxy_index_ref)
                client.update_proxy(current_proxy); client.refresh_session_info(); current_ip[0] = get_real_ip(current_proxy)
                if not client.fb_dtsg: status("Cookie die/Checkpoint (vẫn fail)", "❌"); return
                status(f"Đã đổi proxy - bắt đầu reg", "🔄")
            else: status("Cookie die/Checkpoint", "❌"); return
                
        success_count = 0
        for i in range(1, int(sl_pro5) + 1):
            if STOP_FLAGS.get(chat_id): status("Đã dừng khẩn cấp!", "🛑", is_success=True); return
            name = get_random_name(name_type)
            status(f"Đang tạo Pro5 {i}/{sl_pro5}: {name}...", "🔄")
            res = client.Reg(name)
            is_success, error_msg, page_id = False, "", None
            if isinstance(res, dict):
                if "errors" in res: error_msg = str(res.get("errors"))
                elif "error" in res: error_msg = f"FB: {res.get('error')}"
                elif "data" in res:
                    inner = res.get("data") or {}
                    add_profile = inner.get("additional_profile_plus_create") if isinstance(inner, dict) else None
                    if isinstance(add_profile, dict):
                        err_fb = add_profile.get("error_message"); page_info = add_profile.get("page")
                        if err_fb: error_msg = err_fb
                        elif isinstance(page_info, dict) and page_info.get("id"):
                            is_success = True; page_id = page_info.get("id")
                        else: error_msg = "Bị chặn ngầm"
                    else: error_msg = "Thiếu data"
                else: error_msg = str(res)
            else: error_msg = str(res)

            if is_success:
                success_count += 1
                status(f"Đã tạo Pro5 {success_count}/{sl_pro5}: {name} (ID: {page_id})", "✅", is_success=True)
            else:
                status(f"Fail ({name}): {error_msg[:100]}", "❌"); return

            if i < int(sl_pro5):
                wait = dl + random.randint(2, 5); wait_text = f"{wait}s" + (f" (~{wait//60} phút)" if wait >= 60 else "")
                status(f"Chờ {wait_text} trước page tiếp theo...", "⏳")
                for _ in range(wait):
                    if STOP_FLAGS.get(chat_id): status("Đã dừng khẩn cấp!", "🛑", is_success=True); return
                    time.sleep(1)
        status(f"Hoàn tất ({success_count}/{sl_pro5})", "🏁", is_success=True)
    except Exception as e: status(f"Lỗi: {str(e)[:100]}", "❌")

# ==================== BATCH RUNNER & SUMMARY ====================
def run_batch(chat_id, user_id, mode, data):
    STOP_FLAGS[chat_id] = False
    reset_messages(chat_id)
    results_dict = {}
    
    try:
        with ThreadPoolExecutor(max_workers=data.get("max_threads", 1)) as ex:
            if mode == "reg":
                lines, proxies = data["accounts"], data["proxies"]; proxy_index_ref = [0]
                for index, raw_line in enumerate(lines):
                    if STOP_FLAGS.get(chat_id): break 
                    initial_proxy = proxies[index % len(proxies)] if proxies else None
                    ex.submit(run_reg_account, chat_id, index + 1, raw_line, initial_proxy, proxies, proxy_index_ref, data["sl_pro5"], data["dl"], data["name_type"], data["avatar_mode"], data["custom_link"])
                    if data.get("thread_delay", 0) > 0: time.sleep(data["thread_delay"])
            elif mode == "transfer":
                creds = data["accounts"]
                for index, cred in enumerate(creds):
                    if STOP_FLAGS.get(chat_id): break
                    ex.submit(run_transfer_account, chat_id, index + 1, cred, data["id_nhan"], data["token_nhan"], data["auto_accept"], data["delay"], results_dict)
            elif mode == "delete":
                creds = data["accounts"]
                for index, cred in enumerate(creds):
                    if STOP_FLAGS.get(chat_id): break
                    ex.submit(run_delete_account, chat_id, index + 1, cred, data["delay"], results_dict)
                    
        if mode in ("transfer", "delete") and results_dict:
            total_ok = sum(r.get("ok", 0) for r in results_dict.values())
            total_fail = sum(r.get("fail", 0) for r in results_dict.values())
            total_processed = total_ok + total_fail
            
            title = "CHUYỂN PAGE" if mode == "transfer" else "GỠ ADMIN"
            summary = f"📊 **TỔNG KẾT {title}**\n\n"
            summary += f"Tổng số Page xử lý: {total_processed}\n"
            summary += f"✅ Thành công: {total_ok}\n"
            summary += f"❌ Thất bại: {total_fail}\n"
            
            error_lines = []
            for tid in sorted(results_dict.keys()):
                r = results_dict[tid]
                if r.get("fail", 0) > 0 or r.get("status") == "fail":
                    uid_str = data["accounts"][tid-1].get("uid", "Unknown") if tid-1 < len(data["accounts"]) else "Unknown"
                    reason = r.get("reason", "Lỗi không xác định")
                    if not reason: reason = "Lỗi"
                    error_lines.append(f"- L{tid} (UID: {uid_str}): {reason}")
                    
            if error_lines:
                summary += "\n⚠️ **Chi tiết lỗi:**\n" + "\n".join(error_lines)
            else:
                summary += "\n🎉 Tuyệt vời! Không có luồng nào bị lỗi."
                
            bot.send_message(chat_id, summary, parse_mode="Markdown")
            
        bot.send_message(chat_id, "🏁 Đã kết thúc phiên chạy!", reply_markup=types.ReplyKeyboardRemove())
    except Exception as e:
        bot.send_message(chat_id, f"❌ Lỗi batch: {e}")
    finally:
        running_batches[chat_id] = {"start": time.time(), "status": "done"}

# ==================== KEYBOARDS ====================
def step_menu(skip=False):
    m = types.InlineKeyboardMarkup(row_width=2)
    btns = []
    if skip: btns.append(types.InlineKeyboardButton("⏭ Bỏ qua", callback_data="act_skip"))
    btns.append(types.InlineKeyboardButton("🛑 Stop", callback_data="act_stop"))
    m.add(*btns)
    return m

def name_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("🇻🇳 Tên Việt", callback_data="name_1"), types.InlineKeyboardButton("🇺🇸 Tên Ngoại", callback_data="name_2"))
    return m

def avatar_menu():
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("🤖 AI Random", callback_data="avatar_1"), types.InlineKeyboardButton("🔗 Link tùy chỉnh", callback_data="avatar_2"), types.InlineKeyboardButton("⏭ Không up ảnh", callback_data="avatar_0"))
    return m

def admin_panel_menu():
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("📋 Danh sách user", callback_data="admin_list"), types.InlineKeyboardButton("📖 Hướng dẫn lệnh", callback_data="admin_help"))
    return m

# ==================== TEXT & COMMANDS ====================
HELP_TEXT = """🤖 *FB MANAGER BOT*

*Chức năng:*
1. 🚀 Reg Page Pro5
2. 📤 Chuyển Page (Transfer)
3. 🗑 Gỡ Admin Page (Remove)

*Lệnh:*
/start - Mở Menu chính
/reg - Bắt đầu Reg Page
/chuyenpage - Bắt đầu Chuyển Page
/goadmin - Bắt đầu Gỡ Admin
/stop - Dừng khẩn cấp
/status - Xem trạng thái"""

ADMIN_HELP = """👑 *Quản trị User*\n\n`/add 123 1h` - Thêm 1 giờ\n`/add 123 1d` - Thêm 1 ngày\n`/add 123 7d` - Thêm 7 ngày\n`/add 123 1m` - Thêm 1 tháng\n`/remove 123` - Xóa\n`/list` - Xem DS\n`/cleanup` - Xóa user hết hạn"""

@bot.message_handler(commands=['start'])
def cmd_start(msg):
    user_id = msg.from_user.id
    if not is_allowed(user_id):
        no_permission_reply(msg.chat.id, user_id); return
    name = msg.from_user.first_name or "bạn"
    exp_text = "\n👑 *Admin*" if is_admin(user_id) else (f"\n⏰ {format_remaining(ALLOWED_USERS[user_id])}" if user_id in ALLOWED_USERS else "")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🚀 Reg Page", callback_data="act_start"),
        types.InlineKeyboardButton("📤 Chuyển Page", callback_data="act_tr_start"),
        types.InlineKeyboardButton("🗑 Gỡ Admin", callback_data="act_del_start"),
        types.InlineKeyboardButton("📊 Trạng thái", callback_data="act_status"),
        types.InlineKeyboardButton("🛑 Stop", callback_data="act_stop")
    )
    bot.send_message(msg.chat.id, f"🤖 *Chào {name}!*{exp_text}\n\nChọn thao tác 👇", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(commands=['quanli'])
def cmd_quanli(msg):
    if not is_admin(msg.from_user.id): 
        bot.reply_to(msg, "❌ Bạn không phải Admin."); return
    bot.send_message(msg.chat.id, f"⚙️ *Quản trị*\nUser duyệt: *{len(ALLOWED_USERS)}*\nAdmin: *{len(ADMIN_IDS)}*", reply_markup=admin_panel_menu(), parse_mode="Markdown")

@bot.message_handler(commands=['myid'])
def cmd_myid(msg):
    uid = msg.from_user.id
    status = "👑 Admin" if is_admin(uid) else (f"✅ Đã duyệt — {format_remaining(ALLOWED_USERS[uid])}" if is_allowed(uid) else "❌ Chưa có quyền")
    bot.reply_to(msg, f"📝 ID: `{uid}`\n\n{status}", parse_mode="Markdown")

@bot.message_handler(commands=['add'])
def cmd_add(msg):
    if not is_admin(msg.from_user.id): 
        bot.reply_to(msg, "❌ Bạn không phải Admin.")
        return
    parts = msg.text.split()[1:]
    if not parts: bot.reply_to(msg, "Cú pháp: `/add <id> [1h|1d|1m]`", parse_mode="Markdown"); return
    expire_ts, ids_args = None, parts
    parsed = parse_duration(parts[-1])
    if parsed is not None: expire_ts, ids_args = parsed, parts[:-1]
    added, updated = [], []
    for p in ids_args:
        try: uid = int(p)
        except: continue
        if uid in ALLOWED_USERS: ALLOWED_USERS[uid] = expire_ts; updated.append(uid)
        else: ALLOWED_USERS[uid] = expire_ts; added.append(uid)
    if added or updated:
        save_allowed_users()
        for uid in added + updated:
            try: bot.send_message(uid, f"✅ Đã được duyệt. Hạn: {'∞' if not expire_ts else format_datetime(expire_ts)}")
            except: pass
    bot.reply_to(msg, f"✅ Thêm: {len(added)} | Gia hạn: {len(updated)}")

@bot.message_handler(commands=['remove'])
def cmd_remove(msg):
    if not is_admin(msg.from_user.id): 
        bot.reply_to(msg, "❌ Bạn không phải Admin."); return
    parts = msg.text.split()[1:]
    removed = 0
    for p in parts:
        try: uid = int(p)
        except: continue
        if uid in ALLOWED_USERS: del ALLOWED_USERS[uid]; removed += 1
    if removed: save_allowed_users()
    bot.reply_to(msg, f"🗑 Đã xóa {removed} user.")

@bot.message_handler(commands=['list'])
def cmd_list(msg):
    if not is_admin(msg.from_user.id): 
        bot.reply_to(msg, "❌ Bạn không phải Admin."); return
    txt = "\n".join([f"• `{uid}` — {format_remaining(exp)}" for uid, exp in sorted(ALLOWED_USERS.items())])
    bot.reply_to(msg, f"📋 *User*:\n{txt or 'Trống'}", parse_mode="Markdown")

# ==================== CALLBACKS ====================
@bot.callback_query_handler(func=lambda c: True)
def handle_callback(call):
    user_id, chat_id, data = call.from_user.id, call.message.chat.id, call.data
    if not is_allowed(user_id):
        bot.answer_callback_query(call.id, "❌ Không có quyền."); return

    if data == "act_stop":
        STOP_FLAGS[chat_id] = True; user_data.pop(chat_id, None)
        bot.send_message(chat_id, "🛑 **Đã gửi lệnh DỪNG KHẨN CẤP!**")
        bot.answer_callback_query(call.id, "Đã Stop!"); return

    if data == "act_status":
        rb = running_batches.get(chat_id)
        text = f"📊 Trạng thái: *{rb['status']}*\n⏱ Thời gian: `{int(time.time() - rb['start'])}s`" if rb else "ℹ️ Không có batch nào."
        bot.send_message(chat_id, text, parse_mode="Markdown"); bot.answer_callback_query(call.id); return

    if data == "act_start":
        user_data[chat_id] = {"mode": "reg", "step": "proxies", "data": {"proxies": []}}
        bot.send_message(chat_id, "📡 *Bước 1/8:* Nhập danh sách Proxy (text/file) hoặc Bỏ qua:", reply_markup=step_menu(skip=True), parse_mode="Markdown"); bot.answer_callback_query(call.id); return
    elif data == "act_tr_start":
        user_data[chat_id] = {"mode": "transfer", "step": "tr_acc", "data": {}}
        bot.send_message(chat_id, "📤 *Chuyển Page*\nNhập danh sách Acc nguồn (uid|pass|cookie|token...)\n💬 Gửi *text* hoặc *file .txt*:", reply_markup=step_menu(), parse_mode="Markdown"); bot.answer_callback_query(call.id); return
    elif data == "act_del_start":
        user_data[chat_id] = {"mode": "delete", "step": "del_acc", "data": {}}
        bot.send_message(chat_id, "🗑 *Gỡ Admin Page*\nNhập danh sách Acc cần gỡ (uid|pass|cookie|token...)\n💬 Gửi *text* hoặc *file .txt*:", reply_markup=step_menu(), parse_mode="Markdown"); bot.answer_callback_query(call.id); return

    st = user_data.get(chat_id)
    if not st: return

    if data == "act_skip":
        if st["step"] == "proxies":
            st["data"]["proxies"] = []; st["step"] = "accounts"
            bot.send_message(chat_id, "✅ Bỏ qua proxy.\n\n📝 *Bước 2/8:* Nhập danh sách Cookie (text/file):", reply_markup=step_menu(), parse_mode="Markdown")
        bot.answer_callback_query(call.id); return

    if data.startswith("name_"):
        st["data"]["name_type"] = data.split("_")[1]; st["step"] = "avatar_mode"
        bot.edit_message_text("📸 *Bước 8/8:* Chọn kiểu Avatar:", chat_id, call.message.message_id, reply_markup=avatar_menu(), parse_mode="Markdown"); bot.answer_callback_query(call.id); return

    if data.startswith("avatar_"):
        mode = data.split("_")[1]; st["data"]["avatar_mode"] = mode
        if mode == "2":
            st["step"] = "custom_link"
            bot.edit_message_text("🔗 Nhập URL ảnh trực tiếp:", chat_id, call.message.message_id)
        else:
            st["data"]["custom_link"] = ""; st["step"] = "run"
            bot.edit_message_text("🚀 Bắt đầu chạy...", chat_id, call.message.message_id)
            start_running(chat_id, user_id, st["mode"], st["data"])
        bot.answer_callback_query(call.id); return

    if data.startswith("tr_auto_"):
        st["data"]["auto_accept"] = (data == "tr_auto_y")
        if st["data"]["auto_accept"]:
            st["step"] = "tr_token"
            bot.edit_message_text("🔑 Nhập Token của acc nhận Page:", chat_id, call.message.message_id)
        else:
            st["step"] = "tr_uid"
            bot.edit_message_text("🔑 Nhập UID của acc nhận Page (chỉ gửi mời):", chat_id, call.message.message_id)
        bot.answer_callback_query(call.id)

# ==================== TEXT HANDLERS (LUỒNG CHÍNH) ====================
@bot.message_handler(commands=['reg', 'chuyenpage', 'goadmin'])
def cmd_shortcuts(msg):
    if not is_allowed(msg.from_user.id):
        no_permission_reply(msg.chat.id, msg.from_user.id); return
    chat_id = msg.chat.id
    if msg.text.startswith('/reg'):
        user_data[chat_id] = {"mode": "reg", "step": "proxies", "data": {"proxies": []}}
        bot.send_message(chat_id, "📡 *Bước 1/8:* Nhập danh sách Proxy (text/file) hoặc Bỏ qua:", reply_markup=step_menu(skip=True), parse_mode="Markdown")
    elif msg.text.startswith('/chuyenpage'):
        user_data[chat_id] = {"mode": "transfer", "step": "tr_acc", "data": {}}
        bot.send_message(chat_id, "📤 *Chuyển Page*\nNhập danh sách Acc nguồn (uid|pass|cookie|token...)\n💬 Gửi *text* hoặc *file .txt*:", reply_markup=step_menu(), parse_mode="Markdown")
    elif msg.text.startswith('/goadmin'):
        user_data[chat_id] = {"mode": "delete", "step": "del_acc", "data": {}}
        bot.send_message(chat_id, "🗑 *Gỡ Admin Page*\nNhập danh sách Acc cần gỡ (uid|pass|cookie|token...)\n💬 Gửi *text* hoặc *file .txt*:", reply_markup=step_menu(), parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def cmd_stop(msg):
    STOP_FLAGS[msg.chat.id] = True
    user_data.pop(msg.chat.id, None)  
    bot.send_message(msg.chat.id, "🛑 **Đã gửi lệnh DỪNG KHẨN CẤP!**", reply_markup=types.ReplyKeyboardRemove())

@bot.message_handler(commands=['status'])
def cmd_status(msg):
    chat_id = msg.chat.id
    if not is_allowed(msg.from_user.id): return
    rb = running_batches.get(chat_id)
    text = f"📊 Trạng thái: *{rb['status']}*\n⏱ Thời gian: `{int(time.time() - rb['start'])}s`" if rb else "ℹ️ Không có batch nào."
    bot.send_message(chat_id, text, parse_mode="Markdown")

# Hàm này CHỈ bắt các văn bản thường (không bắt lệnh /...)
@bot.message_handler(func=lambda msg: msg.text and not msg.text.startswith('/'))
def handle_text(msg):
    chat_id, user_id = msg.chat.id, msg.from_user.id
    text = msg.text.strip()

    if not is_allowed(user_id):
        no_permission_reply(chat_id, user_id); return

    st = user_data.get(chat_id)
    if not st:
        bot.send_message(chat_id, "👉 Bấm /start để mở Menu.", reply_markup=types.ReplyKeyboardRemove()); return

    step = st["step"]

    # --- LUỒNG REG PAGE ---
    if step == "proxies":
        st["data"]["proxies"] = [l.strip() for l in text.splitlines() if l.strip()]
        st["step"] = "accounts"
        bot.reply_to(msg, f"✅ Đã lưu {len(st['data']['proxies'])} proxy.\n\n📝 *Bước 2/8:* Nhập Cookie:", reply_markup=step_menu(), parse_mode="Markdown")
    elif step == "accounts":
        accs = [l.strip() for l in text.splitlines() if l.strip()]
        if not accs: bot.reply_to(msg, "❌ Danh sách trống."); return
        st["data"]["accounts"] = accs; st["step"] = "sl_pro5"
        bot.reply_to(msg, f"✅ Đã nhận {len(accs)} acc.\n\n🔢 *Bước 3/8:* Nhập số Pro5/acc:", reply_markup=step_menu(), parse_mode="Markdown")
    elif step == "sl_pro5":
        if not text.isdigit(): bot.reply_to(msg, "❌ Phải là số:"); return
        st["data"]["sl_pro5"] = int(text); st["step"] = "dl"
        bot.reply_to(msg, "⏱ *Bước 4/8:* Delay mỗi lần reg (giây):", reply_markup=step_menu(), parse_mode="Markdown")
    elif step == "dl":
        if not text.isdigit(): bot.reply_to(msg, "❌ Phải là số:"); return
        st["data"]["dl"] = int(text); st["step"] = "max_threads"
        bot.reply_to(msg, "🔀 *Bước 5/8:* Số luồng chạy:", reply_markup=step_menu(), parse_mode="Markdown")
    elif step == "max_threads":
        if not text.isdigit(): bot.reply_to(msg, "❌ Phải là số:"); return
        st["data"]["max_threads"] = int(text); st["step"] = "thread_delay"
        bot.reply_to(msg, "⏱ *Bước 6/8:* Delay giữa các luồng (0 = không delay):", reply_markup=step_menu(), parse_mode="Markdown")
    elif step == "thread_delay":
        try: st["data"]["thread_delay"] = float(text)
        except: bot.reply_to(msg, "❌ Phải là số:"); return
        st["step"] = "name_type"
        bot.send_message(chat_id, "📛 *Bước 7/8:* Chọn loại tên:", reply_markup=name_menu(), parse_mode="Markdown")
    elif step == "custom_link":
        st["data"]["custom_link"] = text; st["step"] = "run"
        bot.reply_to(msg, "🚀 Bắt đầu chạy...")
        start_running(chat_id, user_id, st["mode"], st["data"])

    # --- LUỒNG CHUYỂN PAGE ---
    elif step == "tr_acc":
        try:
            accs = [parse_account_line(l) for l in text.splitlines() if l.strip()]
            accs = [a for a in accs if a["uid"]]
            if not accs: raise Exception()
        except: bot.reply_to(msg, "❌ Không có acc hợp lệ."); return
        st["data"]["accounts"] = accs; st["step"] = "tr_auto"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("Có (Auto Accept)", callback_data="tr_auto_y"), types.InlineKeyboardButton("Không (Chỉ gửi mời)", callback_data="tr_auto_n"))
        bot.reply_to(msg, f"✅ Đã nhận {len(accs)} acc.\n\n⚙️ Tự động Accept lời mời sau khi chuyển?", reply_markup=markup)
    elif step == "tr_token":
        token = text
        info = get_id(token)
        if not info: bot.reply_to(msg, "❌ Token không hợp lệ. Nhập lại:"); return
        st["data"]["token_nhan"] = token; st["data"]["id_nhan"] = info[0]
        st["step"] = "tr_delay"
        bot.reply_to(msg, "⏱ Nhập delay giữa các Page (giây):", reply_markup=step_menu(), parse_mode="Markdown")
    elif step == "tr_uid":
        if not text.isdigit(): bot.reply_to(msg, "❌ UID phải là số. Nhập lại:"); return
        st["data"]["token_nhan"] = ""; st["data"]["id_nhan"] = text
        st["step"] = "tr_delay"
        bot.reply_to(msg, "⏱ Nhập delay giữa các Page (giây):", reply_markup=step_menu(), parse_mode="Markdown")
    elif step == "tr_delay":
        try: st["data"]["delay"] = int(text)
        except: bot.reply_to(msg, "❌ Phải là số:"); return
        st["step"] = "run"
        bot.reply_to(msg, "🚀 Bắt đầu chạy...")
        start_running(chat_id, user_id, st["mode"], st["data"])

    # --- LUỒNG GỠ ADMIN ---
    elif step == "del_acc":
        try:
            accs = [parse_account_line(l) for l in text.splitlines() if l.strip()]
            accs = [a for a in accs if a["uid"]]
            if not accs: raise Exception()
        except: bot.reply_to(msg, "❌ Không có acc hợp lệ."); return
        st["data"]["accounts"] = accs; st["step"] = "del_delay"
        bot.reply_to(msg, f"✅ Đã nhận {len(accs)} acc.\n\n⏱ Nhập delay giữa các Page (giây):", reply_markup=step_menu(), parse_mode="Markdown")
    elif step == "del_delay":
        try: st["data"]["delay"] = int(text)
        except: bot.reply_to(msg, "❌ Phải là số:"); return
        st["step"] = "run"
        bot.reply_to(msg, "🚀 Bắt đầu chạy...")
        start_running(chat_id, user_id, st["mode"], st["data"])

@bot.message_handler(content_types=['document'])
def handle_document(msg):
    chat_id, user_id = msg.chat.id, msg.from_user.id
    if not is_allowed(user_id): return
    st = user_data.get(chat_id)
    if not st: return
    step = st["step"]
    if step not in ("accounts", "proxies", "tr_acc", "del_acc"):
        bot.reply_to(msg, "⚠️ Bước này không nhận file."); return

    doc = msg.document
    if not (doc.file_name or "").lower().endswith(('.txt', '.log', '.csv')):
        bot.reply_to(msg, "❌ Chỉ nhận .txt/.log/.csv"); return

    try:
        file_info = bot.get_file(doc.file_id)
        content = bot.download_file(file_info.file_path).decode('utf-8', errors='ignore')
        lines = [l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith('#')]
        if not lines: bot.reply_to(msg, "❌ File rỗng."); return

        if step == "accounts":
            st["data"]["accounts"] = lines; st["step"] = "sl_pro5"
            bot.reply_to(msg, f"✅ Đã nhận {len(lines)} acc.\n\n🔢 Nhập số Pro5/acc:", reply_markup=step_menu(), parse_mode="Markdown")
        elif step == "proxies":
            st["data"]["proxies"] = lines; st["step"] = "accounts"
            bot.reply_to(msg, f"✅ Đã nhận {len(lines)} proxy.\n\n📝 Nhập Cookie:", reply_markup=step_menu(), parse_mode="Markdown")
        elif step == "tr_acc":
            accs = [parse_account_line(l) for l in lines]; accs = [a for a in accs if a["uid"]]
            st["data"]["accounts"] = accs; st["step"] = "tr_auto"
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(types.InlineKeyboardButton("Có (Auto Accept)", callback_data="tr_auto_y"), types.InlineKeyboardButton("Không (Chỉ gửi mời)", callback_data="tr_auto_n"))
            bot.reply_to(msg, f"✅ Đã nhận {len(accs)} acc.\n\n⚙️ Tự động Accept lời mời sau khi chuyển?", reply_markup=markup)
        elif step == "del_acc":
            accs = [parse_account_line(l) for l in lines]; accs = [a for a in accs if a["uid"]]
            st["data"]["accounts"] = accs; st["step"] = "del_delay"
            bot.reply_to(msg, f"✅ Đã nhận {len(accs)} acc.\n\n⏱ Nhập delay mỗi Page:", reply_markup=step_menu(), parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(msg, f"❌ Lỗi đọc file: {e}")

def start_running(chat_id, user_id, mode, data):
    st = user_data.pop(chat_id, None)
    if not st: return
    if mode == "reg": msg = f"🚀 *REG PAGE*\nAcc: {len(data['accounts'])} | Pro5/acc: {data['sl_pro5']} | Threads: {data['max_threads']}"
    elif mode == "transfer": msg = f"🚀 *CHUYỂN PAGE*\nAcc: {len(data['accounts'])} | Auto Accept: {data['auto_accept']} | Delay: {data['delay']}s"
    elif mode == "delete": msg = f"🚀 *GỠ ADMIN PAGE*\nAcc: {len(data['accounts'])} | Delay: {data['delay']}s"
    bot.send_message(chat_id, msg, parse_mode="Markdown")
    Thread(target=run_batch, args=(chat_id, user_id, mode, data), daemon=True).start()

# ==================== MAIN ====================
if __name__ == "__main__":
    print("[BOT] Đang khởi động...")
    try:
        bot.set_my_commands([
            types.BotCommand("start", "Mở Menu chính"),
            types.BotCommand("quanli", "Quản trị viên (Admin)"),
            types.BotCommand("reg", "Reg Page Pro5"),
            types.BotCommand("chuyenpage", "Chuyển quyền quản trị Page"),
            types.BotCommand("goadmin", "Gỡ Admin/Xoá Page"),
            types.BotCommand("stop", "Dừng khẩn cấp"),
            types.BotCommand("status", "Xem trạng thái"),
            types.BotCommand("myid", "Lấy ID Telegram")
        ])
    except: pass
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
