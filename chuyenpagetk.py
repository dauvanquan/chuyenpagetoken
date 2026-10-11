import requests
import json
import re
import uuid
import time
import logging
import os
from typing import Tuple, Dict, Any, Optional, List, Set

# ================== CẤU HÌNH LOGGING ==================
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
file_handler = logging.FileHandler("transfer_page.log", encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


# ================== HÀM HELPER ==================

def sleep_with_countdown(seconds: float):
    if seconds <= 0:
        return
    print(f"Chờ {seconds} giây...", end="", flush=True)
    time.sleep(seconds)
    print("\r" + " " * 40 + "\r", end="", flush=True)


def load_accounts_from_file(filepath: str) -> List[Dict[str, str]]:
    """
    Đọc file tài khoản nguồn, định dạng mỗi dòng:
        uid|pass|token
    - Bỏ qua dòng trống và dòng bắt đầu bằng '#'.
    - Trả về list dict {'uid': ..., 'password': ..., 'token': ...}
    """
    if not os.path.isfile(filepath):
        print(f"\033[91m✗ File không tồn tại: {filepath}\033[0m")
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        raw_lines = f.readlines()

    lines = []
    for ln in raw_lines:
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        lines.append(s)

    if not lines:
        print("\033[91m✗ File rỗng hoặc không có dòng hợp lệ.\033[0m")
        return []

    accounts: List[Dict[str, str]] = []
    for i, ln in enumerate(lines, 1):
        parts = ln.split("|")
        if len(parts) != 3:
            logger.warning(f"Dòng {i}: Không đúng định dạng 'uid|pass|token' (cần 2 dấu '|'), bỏ qua: {ln[:60]}...")
            continue
        uid, password, token = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if not uid or not password or not token:
            logger.warning(f"Dòng {i}: Thiếu uid/pass/token, bỏ qua.")
            continue
        accounts.append({"uid": uid, "password": password, "token": token})

    print(f"\033[96m→ Đã đọc {len(accounts)} tài khoản từ file (định dạng: uid|pass|token).\033[0m")
    return accounts


# ================== CÁC HÀM KIỂM TRA RESPONSE ==================

def check_step1_response(response_data: Any) -> Tuple[bool, str, Dict[str, Any]]:
    if isinstance(response_data, str):
        try:
            res = json.loads(response_data)
        except Exception:
            return False, f"Response không phải JSON: {response_data[:150]}", {}
    elif isinstance(response_data, dict):
        res = response_data
    else:
        return False, f"Kiểu dữ liệu không hợp lệ: {type(response_data)}", {}

    errors = res.get("errors")
    if errors and isinstance(errors, list) and len(errors) > 0:
        err = errors[0]
        code = err.get("code")
        msg = err.get("message", "")
        summary = err.get("summary", "")
        desc = err.get("description", "")
        detail = {"code": code, "message": msg, "summary": summary, "description": desc}
        if "password" in msg.lower() or "mật khẩu" in desc.lower():
            return False, f"Mật khẩu không chính xác (code: {code})", detail
        return False, f"Step 1 thất bại: {desc or summary or msg} (Code: {code})", detail

    data = res.get("data", {})
    nt_async = data.get("native_templates_async") if data else None
    if nt_async is not None:
        return True, "Step 1 thành công: Đã xác thực mật khẩu", {}
    return False, "Step 1 thất bại: Không tìm thấy dữ liệu native_templates_async", {"raw": res}


def check_step2_response(response_data: Any) -> Tuple[bool, str, Dict[str, Any]]:
    if isinstance(response_data, str):
        try:
            res = json.loads(response_data)
        except Exception:
            return False, f"Response không phải JSON: {response_data[:150]}", {}
    elif isinstance(response_data, dict):
        res = response_data
    else:
        return False, f"Kiểu dữ liệu không hợp lệ: {type(response_data)}", {}

    errors = res.get("errors")
    if errors and isinstance(errors, list) and len(errors) > 0:
        err = errors[0]
        code = err.get("code")
        msg = err.get("message", "")
        summary = err.get("summary", "")
        desc = err.get("description", "")
        detail = {"code": code, "message": msg, "summary": summary, "description": desc}
        combined = f"{msg} {summary} {desc}".lower()
        if "already admin" in combined or "đã là quản trị viên" in combined:
            return False, "Tài khoản đích đã là quản trị viên của Page", detail
        if "pending" in combined or "lời mời" in combined:
            return False, "Đã có lời mời đang chờ duyệt", detail
        return False, f"Step 2 thất bại: {desc or summary or msg} (Code: {code})", detail

    data = res.get("data", {})
    nt_async = data.get("native_templates_async") if data else None
    if nt_async is not None:
        return True, "Step 2 thành công: Đã gửi lời mời", {}
    return False, "Step 2 thất bại: Dữ liệu trả về trống", {"raw": res}


def check_step3_response(response_data: Any) -> Tuple[bool, str, Dict[str, Any]]:
    if isinstance(response_data, str):
        try:
            res = json.loads(response_data)
        except Exception:
            raw_text = response_data
            m = re.search(r'invitation_id[\\"\':=]+(\d+)', raw_text)
            if m:
                inv_id = m.group(1)
                return True, f"Step 3 thành công: invitation_id = {inv_id}", {"invitation_id": inv_id}
            return False, f"Response không phải JSON: {response_data[:150]}", {}
    elif isinstance(response_data, dict):
        res = response_data
    else:
        return False, f"Kiểu dữ liệu không hợp lệ: {type(response_data)}", {}

    errors = res.get("errors")
    if errors and isinstance(errors, list) and len(errors) > 0:
        err = errors[0]
        code = err.get("code")
        msg = err.get("message", "")
        return False, f"Step 3 thất bại: {msg} (Code: {code})", {}

    invitation_id = None
    try:
        data = res.get("data", {})
        nt_screen = data.get("native_template_screen", {})
        nt_bundle = nt_screen.get("nt_bundle", {})
        attrs = nt_bundle.get("nt_bundle_attributes", [])
        for attr in attrs:
            if attr.get("name") == "1":
                params_str = attr.get("intent_value", {}).get("query", {}).get("params", "")
                if "invitation_id" in params_str:
                    m = re.search(r'invitation_id[=:]\s*(\d+)', params_str)
                    if m:
                        invitation_id = m.group(1)
                        break
    except Exception:
        pass

    if not invitation_id:
        json_dump = json.dumps(res)
        m = re.search(r'invitation_id[\\"\':=]+(\d+)', json_dump)
        if m:
            invitation_id = m.group(1)

    if invitation_id:
        return True, f"Step 3 thành công: invitation_id = {invitation_id}", {"invitation_id": invitation_id}
    return False, "Step 3 không tìm thấy lời mời (có thể chưa nhận được hoặc đã hết hạn)", {"raw": res}


def check_step4_response(response_data: Any) -> Tuple[bool, str, Dict[str, Any]]:
    if isinstance(response_data, str):
        try:
            res = json.loads(response_data)
        except Exception:
            return False, f"Response không phải JSON: {response_data[:150]}", {}
    elif isinstance(response_data, dict):
        res = response_data
    else:
        return False, f"Kiểu dữ liệu không hợp lệ: {type(response_data)}", {}

    errors = res.get("errors")
    if errors and isinstance(errors, list) and len(errors) > 0:
        err = errors[0]
        code = err.get("code")
        msg = err.get("message", "")
        summary = err.get("summary", "")
        desc = err.get("description", "")
        combined = f"{msg} {summary} {desc}".lower()
        if "accepted" in combined or "đã chấp nhận" in combined:
            return True, "Lời mời này đã được chấp nhận từ trước", {}
        if "expired" in combined or "hết hạn" in combined:
            return False, "Lời mời đã hết hạn hoặc bị hủy", {}
        return False, f"Step 4 thất bại: {desc or msg} (Code: {code})", {}

    data = res.get("data", {})
    nt_async = data.get("native_templates_async") if data else None
    if nt_async is not None:
        return True, "🎉 Chuyển Page thành công! Tài khoản đích đã là Admin", {}
    return False, "Step 4 thất bại: Không nhận được xác nhận", {"raw": res}


# ================== CÁC HÀM CHỨC NĂNG ==================

def get_id(token: str) -> Optional[Tuple[str, str]]:
    url = "https://graph.facebook.com/v24.0/me"
    headers = {
        "Accept-Encoding": "gzip",
        "Connection": "Keep-Alive",
        "Host": "graph.facebook.com",
        "User-Agent": "okhttp/5.1.0",
    }
    params = {"fields": "id,name", "access_token": token}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        data = resp.json()
    except Exception as e:
        logger.error(f"Lỗi request lấy thông tin tài khoản: {e}")
        return None
    if not isinstance(data, dict):
        logger.error(f"Response không hợp lệ: {data}")
        return None
    if "error" in data:
        err = data["error"]
        logger.error(f"Token không hợp lệ: {err.get('message')}")
        return None
    uid = data.get("id")
    uname = data.get("name")
    if not uid:
        logger.error("Không lấy được ID từ token.")
        return None
    return str(uid), uname or ""


def parse_selection(selection_str: str, max_index: int) -> List[int]:
    indices = []
    parts = selection_str.replace(" ", "").split(",")
    for part in parts:
        if not part:
            continue
        if part.lower() == "all":
            return list(range(1, max_index + 1))
        if "-" in part:
            try:
                start, end = part.split("-")
                start = int(start)
                end = int(end)
                if start < 1 or end > max_index or start > end:
                    logger.warning(f"Khoảng không hợp lệ: {part}, bỏ qua.")
                    continue
                indices.extend(range(start, end + 1))
            except ValueError:
                logger.warning(f"Không parse được: {part}, bỏ qua.")
                continue
        else:
            try:
                idx = int(part)
                if 1 <= idx <= max_index:
                    indices.append(idx)
                else:
                    logger.warning(f"Index ngoài phạm vi: {part}, bỏ qua.")
            except ValueError:
                logger.warning(f"Không parse được: {part}, bỏ qua.")
                continue
    return sorted(set(indices))


def get_managed_page_ids(token: str) -> Set[str]:
    page_ids = set()
    url = "https://graph.facebook.com/v24.0/me/accounts"
    headers = {
        "Accept-Encoding": "gzip",
        "Connection": "Keep-Alive",
        "Host": "graph.facebook.com",
        "User-Agent": "okhttp/5.1.0",
    }
    params = {"fields": "id", "access_token": token, "limit": 100}
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        data = resp.json()
        if not isinstance(data, dict):
            return page_ids
        if "error" in data:
            logger.error(f"Không thể lấy danh sách page từ token đích: {data['error'].get('message')}")
            return page_ids
        for page in data.get("data", []):
            pid = page.get("id")
            if pid:
                page_ids.add(str(pid))
        next_page = data.get("paging", {}).get("next")
        while next_page:
            resp = requests.get(next_page, timeout=30)
            data = resp.json()
            for page in data.get("data", []):
                pid = page.get("id")
                if pid:
                    page_ids.add(str(pid))
            next_page = data.get("paging", {}).get("next")
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách page từ token đích: {e}")
        return page_ids
    return page_ids


def _fetch_all_pages_raw(token: str, profile_id: str) -> List[Dict[str, str]]:
    headers_graph = {
        "Accept-Encoding": "gzip",
        "Connection": "Keep-Alive",
        "Host": "graph.facebook.com",
        "User-Agent": "okhttp/5.1.0",
    }
    params_graph = {
        "fields": "id,name,access_token,additional_profile_id",
        "access_token": token,
    }
    pages_dict = {}
    try:
        resp = requests.get("https://graph.facebook.com/v24.0/me/accounts",
                            params=params_graph, headers=headers_graph, timeout=30)
        data = resp.json()
        if isinstance(data, dict):
            for p in data.get("data", []):
                pid = str(p.get("id", ""))
                pages_dict[pid] = {
                    "page_id": pid,
                    "name": p.get("name", ""),
                    "additional_profile_id": str(p.get("additional_profile_id", "") or pid),
                    "access_token": p.get("access_token", "")
                }
    except Exception as e:
        logger.error(f"Lỗi lấy danh sách page qua Graph API: {e}")

    url = "https://b-graph.facebook.com/graphql"
    headers_sw = {
        "Accept-Encoding": "gzip",
        "Authorization": f"OAuth {token}",
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": (
            "[FBAN/FB4A;FBAV/542.0.0.46.151;FBBV/840338789;"
            "FBDM/{density=0.75,width=300,height=540};"
            "FBLC/vi_VN;FBRV/0;FBCR/MobiFone;"
            "FBMF/MTool-Max;FBBD/MTool-Max;"
            "FBPN/com.facebook.katana;FBDV/MTool-Max;"
            "FBSV/9;FBOP/1;FBCA/x86_64:arm64-v8a;]"
        ),
    }
    variables = {
        "profile_switcher_connection_first": 300,
        "additional_profile_picture_size": 80,
        "profileID": profile_id,
        "main_profile_picture_size": 80,
        "scale": "2",
        "nt_context": {
            "using_white_navbar": True,
            "styles_id": "588d028b36bed0e1889e09b60e0f9aea",
            "pixel_ratio": 2,
            "is_push_on": True,
            "debug_tooling_metadata_token": None,
            "is_flipper_enabled": False,
            "theme_params": [{"value": [], "design_system_name": "FDS"}],
            "bloks_version": "338f8ead5977a2c41eba3e92584dcf1d132e8b7928f1f5796662ec064023047d"
        },
        "overflow_recent_searches_filter_ids": [],
        "use_native_entrypoint_for_stars_on_reels": True
    }
    data_sw = {
        "method": "post",
        "pretty": "false",
        "format": "json",
        "server_timestamps": "true",
        "locale": "vi_VN",
        "client_doc_id": "116912609015732060545213902280",
        "variables": json.dumps(variables, separators=(",", ":"))
    }
    try:
        resp = requests.post(url, headers=headers_sw, data=data_sw, timeout=30)
        result = resp.json()
        if isinstance(result, dict):
            user = result.get("data", {}).get("user", {})
            profiles = user.get("profile_switcher_eligible_profiles", {}).get("edges", [])
            for edge in profiles:
                node = edge.get("node", {})
                prof = node.get("profile", {})
                sinfo = node.get("session_info", {})
                prof_id = str(prof.get("id", ""))
                prof_name = prof.get("name", "")
                sw_token = sinfo.get("access_token", "")

                matched = False
                for pid, item in pages_dict.items():
                    if item["additional_profile_id"] == prof_id or item["page_id"] == prof_id:
                        if sw_token:
                            item["access_token"] = sw_token
                        matched = True
                        break
                if not matched and prof_id:
                    pages_dict[prof_id] = {
                        "page_id": prof_id,
                        "name": prof_name,
                        "additional_profile_id": prof_id,
                        "access_token": sw_token
                    }
    except Exception as e:
        logger.error(f"Lỗi gọi ProfileSwitcherQuery: {e}")

    return list(pages_dict.values())


def get_token_pages(token: str, profile_id: str) -> List[Dict[str, str]]:
    parsed = _fetch_all_pages_raw(token, profile_id)
    if not parsed:
        logger.error("Không tìm thấy Page nào.")
        return []

    print("\nDanh sách Page có thể chuyển:")
    for i, p in enumerate(parsed, 1):
        print(f"[{i}] {p['name']} (ID: {p['page_id']})")

    max_idx = len(parsed)
    while True:
        choice = input(f"Chọn Page (ví dụ: 1-5, 1,3,5, hoặc all để chọn tất cả, q để thoát): ").strip()
        if choice.lower() == 'q':
            return []
        indices = parse_selection(choice, max_idx)
        if indices:
            selected_pages = []
            for idx in indices:
                p = parsed[idx - 1]
                selected_pages.append({
                    "page_uid": p["additional_profile_id"] or p["page_id"],
                    "page_token": p["access_token"],
                    "page_name": p["name"],
                    "page_id": p["page_id"]
                })
            return selected_pages
        else:
            print("Lựa chọn không hợp lệ, vui lòng nhập lại.")


def get_all_pages(token: str, profile_id: str) -> List[Dict[str, str]]:
    parsed = _fetch_all_pages_raw(token, profile_id)
    result = []
    for p in parsed:
        result.append({
            "page_uid": p["additional_profile_id"] or p["page_id"],
            "page_token": p["access_token"],
            "page_name": p["name"],
            "page_id": p["page_id"]
        })
    return result


def xac_nhan_mk(auth_token: str, admin_id: str, profile_id: str, password: str) -> Optional[str]:
    url = "https://graph.facebook.com/graphql"
    clean_token = auth_token.replace("OAuth ", "").replace("Bearer ", "").strip()
    headers = {
        "Accept-Encoding": "gzip",
        "authorization": f"OAuth {clean_token}",
        "Connection": "Keep-Alive",
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        "user-agent": "[FBAN/FB4A;FBAV/542.0.0.46.151;FBBV/840338789;FBDM/{density=0.75,width=300,height=540};FBLC/vi_VN;FBRV/0;FBCR/MobiFone;FBMF/MTool-Max;FBBD/MTool-Max;FBPN/com.facebook.katana;FBDV/MTool-Max;FBSV/9;FBOP/1;FBCA/x86_64:arm64-v8a;]",
        "x-fb-connection-type": "WIFI",
        "x-fb-device-group": "4789",
        "x-fb-friendly-name": "NativeTemplateAsyncQuery",
        "x-fb-request-analytics-tags": '{"network_tags":{"product":"350685531728","request_category":"graphql","purpose":"none","retry_attempt":"0"},"application_tags":"graphservice"}',
        "x-graphql-client-library": "graphservice"
    }
    nt_context = {
        "using_white_navbar": True,
        "styles_id": "588d028b36bed0e1889e09b60e0f9aea",
        "pixel_ratio": 2,
        "is_push_on": True,
        "debug_tooling_metadata_token": None,
        "is_flipper_enabled": False,
        "theme_params": [{"value": [], "design_system_name": "FDS"}],
        "bloks_version": "338f8ead5977a2c41eba3e92584dcf1d132e8b7928f1f5796662ec064023047d"
    }
    payload_string = (
        f"/nt/profile/admin_management/permissions_reauth?"
        f"admin_id={admin_id}&"
        f"admin_rows_container_id=%5B%228bxxoh%3A2%22%2Cnull%5D&"
        f"admin_type=full_access&"
        f"entry_point_screen_id=%5B%227o2xil%3A5%22%2Cnull%5D&"
        f"profile_id={profile_id}&"
        f"state_ids%5Bauthenticated%5D=8csr9g%3A0&"
        f"state_ids%5Bauthentication_attempted%5D=8csr9g%3A1&"
        f"state_ids%5Bshow_entry_point_saving_spinner%5D=8bxxoh%3A0&"
        f"state_ids%5Bshow_saving_spinner%5D=8csr9g%3A3&"
        f"state_ids%5Bads%5D=8clnk7%3A2&"
        f"state_ids%5Bcontent%5D=8clnk7%3A3&"
        f"state_ids%5Binsights%5D=8clnk7%3A4&"
        f"state_ids%5Bmessages%5D=8clnk7%3A5&"
        f"state_ids%5Bmoderate%5D=8clnk7%3A6"
    )
    client_data = {"sensitive_string_value": json.dumps([["password", password]])}
    variables = {
        "params": {
            "nt_context": nt_context,
            "payload": payload_string,
            "client_data": client_data
        },
        "nt_context": nt_context,
        "scale": "2",
        "use_native_entrypoint_for_stars_on_reels": True,
        "profile_image_size": 188,
        "include_image_ranges": True
    }
    data = {
        "fb_api_client_context": '{"is_background":false}',
        "pretty": "false",
        "variables": json.dumps(variables, ensure_ascii=False),
        "method": "post",
        "client_doc_id": "30749539927629244093798192451",
        "format": "json",
        "server_timestamps": "true",
        "locale": "vi_VN",
        "fb_api_req_friendly_name": "NativeTemplateAsyncQuery",
        "fb_api_caller_class": "graphservice"
    }
    try:
        resp = requests.post(url, headers=headers, data=data, timeout=30)
        resp_json = resp.json()
    except Exception as e:
        logger.error(f"Lỗi request Step 1: {e}")
        return None

    is_ok, msg, _ = check_step1_response(resp_json)
    if not is_ok:
        logger.error(msg)
        return None
    logger.debug(msg)
    try:
        return resp_json["data"]["native_templates_async"]["native_template_bundles"][0]["nt_bundle_tree"]
    except (KeyError, IndexError, TypeError):
        logger.error("Không tìm thấy nt_bundle_tree trong response.")
        return None


def extract_payload_from_tree(nt_bundle_tree: str) -> Optional[str]:
    if not nt_bundle_tree:
        return None
    m = re.search(r'(/nt/profile/admin_management/permissions/update\?[^"\'\\}]+)', nt_bundle_tree)
    if m:
        return m.group(1).replace(r'\/', '/')
    try:
        tree = json.loads(nt_bundle_tree)
        def find_update_url(obj):
            if isinstance(obj, dict):
                if "$" in obj and isinstance(obj["$"], str) and "/nt/profile/admin_management/permissions/update" in obj["$"]:
                    return obj["$"].replace(r'\/', '/')
                for v in obj.values():
                    res = find_update_url(v)
                    if res:
                        return res
            elif isinstance(obj, list):
                for item in obj:
                    res = find_update_url(item)
                    if res:
                        return res
            return None
        return find_update_url(tree)
    except Exception:
        return None


def gui_loi_moi(auth_token: str, nt_bundle_tree: str) -> bool:
    payload = extract_payload_from_tree(nt_bundle_tree)
    if not payload:
        logger.error("Không tìm thấy URL permissions/update trong nt_bundle_tree")
        return False

    state_data = {
        "ads": True,
        "insights": True,
        "messages": True,
        "content": True,
        "moderate": True,
        "show_entry_point_saving_spinner": "NONE"
    }
    nt_context = {
        "using_white_navbar": True,
        "styles_id": "588d028b36bed0e1889e09b60e0f9aea",
        "pixel_ratio": 2,
        "is_push_on": True,
        "debug_tooling_metadata_token": None,
        "is_flipper_enabled": False,
        "theme_params": [{"value": [], "design_system_name": "FDS"}],
        "bloks_version": "338f8ead5977a2c41eba3e92584dcf1d132e8b7928f1f5796662ec064023047d"
    }
    variables = {
        "params": {
            "payload": payload,
            "state_data": json.dumps(state_data),
            "nt_context": nt_context
        },
        "nt_context": nt_context,
        "scale": "2",
        "use_native_entrypoint_for_stars_on_reels": True,
        "profile_image_size": 188,
        "include_image_ranges": True
    }
    data = {
        "fb_api_client_context": '{"is_background":false}',
        "pretty": "false",
        "variables": json.dumps(variables, ensure_ascii=False),
        "method": "post",
        "client_doc_id": "30749539927629244093798192451",
        "format": "json",
        "server_timestamps": "true",
        "locale": "vi_VN",
        "fb_api_req_friendly_name": "NativeTemplateAsyncQuery",
        "fb_api_analytics_tags": '["GraphServices"]',
        "client_trace_id": str(uuid.uuid4()),
        "fb_api_caller_class": "graphservice"
    }
    headers = {
        "Accept-Encoding": "gzip",
        "authorization": f"OAuth {auth_token}",
        "Connection": "Keep-Alive",
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        "Host": "graph.facebook.com",
        "user-agent": "[FBAN/FB4A;FBAV/542.0.0.46.151;FBBV/840338789;FBDM/{density=0.75,width=300,height=540};FBLC/vi_VN;FBRV/0;FBCR/MobiFone;FBMF/MTool-Max;FBBD/MTool-Max;FBPN/com.facebook.katana;FBDV/MTool-Max;FBSV/9;FBOP/1;FBCA/x86_64:arm64-v8a;]",
        "x-fb-connection-type": "WIFI",
        "x-fb-device-group": "4789",
        "x-fb-friendly-name": "NativeTemplateAsyncQuery",
        "x-fb-request-analytics-tags": '{"network_tags":{"product":"350685531728","request_category":"graphql","purpose":"none","retry_attempt":"0"},"application_tags":"graphservice"}',
        "x-graphql-client-library": "graphservice"
    }
    url = "https://graph.facebook.com/graphql"
    try:
        resp = requests.post(url, headers=headers, data=data, timeout=30)
        resp_json = resp.json()
    except Exception as e:
        logger.error(f"Lỗi request Step 2: {e}")
        return False
    is_ok, msg, _ = check_step2_response(resp_json)
    if not is_ok:
        logger.error(msg)
        return False
    logger.debug(msg)
    return True


def ktra_loi_moi(auth_token: str, profile_id: str, invitee_id: str) -> Optional[str]:
    url = "https://graph.facebook.com/graphql"
    headers = {
        "Accept-Encoding": "gzip",
        "authorization": f"OAuth {auth_token}",
        "Connection": "Keep-Alive",
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        "Host": "graph.facebook.com",
        "user-agent": "[FBAN/FB4A;FBAV/542.0.0.46.151;FBBV/840338789;FBDM/{density=0.75,width=300,height=540};FBLC/vi_VN;FBRV/0;FBCR/MobiFone;FBMF/MTool-Max;FBBD/MTool-Max;FBPN/com.facebook.katana;FBDV/MTool-Max;FBSV/9;FBOP/1;FBCA/x86_64:arm64-v8a;]",
        "x-fb-connection-type": "WIFI",
        "x-fb-device-group": "4789",
        "x-fb-friendly-name": "NativeTemplateAsyncQuery",
        "x-fb-request-analytics-tags": '{"network_tags":{"product":"350685531728","request_category":"graphql","purpose":"none","retry_attempt":"0"},"application_tags":"graphservice"}',
        "x-graphql-client-library": "graphservice"
    }
    nt_context = {
        "using_white_navbar": True,
        "styles_id": "588d028b36bed0e1889e09b60e0f9aea",
        "pixel_ratio": 2,
        "is_push_on": True,
        "debug_tooling_metadata_token": None,
        "is_flipper_enabled": False,
        "theme_params": [{"value": [], "design_system_name": "FDS"}],
        "bloks_version": "338f8ead5977a2c41eba3e92584dcf1d132e8b7928f1f5796662ec064023047d"
    }
    params_str = json.dumps({
        "screen_id": '["sz9fnp:17",null]',
        "profile_id": profile_id,
        "invitee_id": invitee_id
    })
    variables = {
        "params": {
            "nt_context": nt_context,
            "path": "/nt/profile/admin_management/invitation",
            "params": params_str,
            "extra_client_data": {}
        },
        "scale": "2",
        "use_native_entrypoint_for_stars_on_reels": True,
        "nt_context": nt_context
    }
    data = {
        "pretty": "false",
        "variables": json.dumps(variables, ensure_ascii=False),
        "method": "post",
        "client_doc_id": "221080835214205752894689842827",
        "purpose": "fetch",
        "format": "json",
        "server_timestamps": "true",
        "locale": "vi_VN",
        "fb_api_req_friendly_name": "NativeTemplateScreenQuery",
        "client_trace_id": str(uuid.uuid4()),
        "fb_api_client_context": '{"is_background":false}',
        "fb_api_analytics_tags": '["surfaces.fb.GraphServiceEmitter","GraphServices"]',
        "fb_api_caller_class": "graphservice"
    }
    try:
        resp = requests.post(url, headers=headers, data=data, timeout=30)
        resp_json = resp.json()
    except Exception as e:
        logger.error(f"Lỗi request Step 3: {e}")
        return None
    is_ok, msg, detail = check_step3_response(resp_json)
    if not is_ok:
        logger.error(msg)
        return None
    logger.debug(msg)
    if is_ok:
        return detail.get("invitation_id")
    return None


def xac_nhan_loi_moi(auth_token: str, invitation_id: str, accept_invitation: int = 1) -> bool:
    url = "https://graph.facebook.com/graphql"
    headers = {
        "Accept-Encoding": "gzip",
        "authorization": f"OAuth {auth_token}",
        "Connection": "Keep-Alive",
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        "Host": "graph.facebook.com",
        "user-agent": "[FBAN/FB4A;FBAV/542.0.0.46.151;FBBV/840338789;FBDM/{density=0.75,width=300,height=540};FBLC/vi_VN;FBRV/0;FBCR/MobiFone;FBMF/MTool-Max;FBBD/MTool-Max;FBPN/com.facebook.katana;FBDV/MTool-Max;FBSV/9;FBOP/1;FBCA/x86_64:arm64-v8a;]",
        "x-fb-connection-type": "WIFI",
        "x-fb-device-group": "4789",
        "x-fb-friendly-name": "NativeTemplateAsyncQuery",
        "x-fb-request-analytics-tags": '{"network_tags":{"product":"350685531728","request_category":"graphql","purpose":"none","retry_attempt":"0"},"application_tags":"graphservice"}',
        "x-graphql-client-library": "graphservice"
    }
    nt_context = {
        "using_white_navbar": True,
        "styles_id": "588d028b36bed0e1889e09b60e0f9aea",
        "pixel_ratio": 2,
        "is_push_on": True,
        "debug_tooling_metadata_token": None,
        "is_flipper_enabled": False,
        "theme_params": [{"value": [], "design_system_name": "FDS"}],
        "bloks_version": "338f8ead5977a2c41eba3e92584dcf1d132e8b7928f1f5796662ec064023047d"
    }
    payload = f"/nt/profile/admin_management/invitation_response?accept_invitation={accept_invitation}&invitation_id={invitation_id}&admin_type=full_access"
    variables = {
        "params": {
            "payload": payload,
            "nt_context": nt_context
        },
        "nt_context": nt_context,
        "scale": "2",
        "use_native_entrypoint_for_stars_on_reels": True,
        "profile_image_size": 188,
        "include_image_ranges": True
    }
    data = {
        "fb_api_client_context": '{"is_background":false}',
        "pretty": "false",
        "variables": json.dumps(variables, ensure_ascii=False),
        "method": "post",
        "client_doc_id": "30749539927629244093798192451",
        "format": "json",
        "server_timestamps": "true",
        "locale": "vi_VN",
        "fb_api_req_friendly_name": "NativeTemplateAsyncQuery",
        "fb_api_analytics_tags": '["GraphServices"]',
        "client_trace_id": str(uuid.uuid4()),
        "fb_api_caller_class": "graphservice"
    }
    try:
        resp = requests.post(url, headers=headers, data=data, timeout=30)
        resp_json = resp.json()
    except Exception as e:
        logger.error(f"Lỗi request Step 4: {e}")
        return False
    is_ok, msg, _ = check_step4_response(resp_json)
    if not is_ok:
        logger.error(msg)
        return False
    logger.debug(msg)
    return True


# ================== THIẾT LẬP TÀI KHOẢN NGUỒN ==================

def setup_source_account(account_index: int, allow_cancel: bool = True) -> Optional[Dict[str, Any]]:
    print(f"\n\033[94m===== TÀI KHOẢN NGUỒN {account_index} =====\033[0m")
    if allow_cancel:
        print("(Nhấn Enter để bỏ trống và kết thúc nhập tài khoản nguồn)")

    while True:
        token_acc_page = input(f"Nhập token của tài khoản nguồn {account_index}: ").strip()
        if not token_acc_page:
            if allow_cancel:
                return None
            print("Token không được để trống.")
            continue

        info = get_id(token_acc_page)
        if info is None:
            print("\033[91m✗ Token không hợp lệ hoặc không lấy được thông tin tài khoản. Vui lòng nhập lại.\033[0m")
            continue

        id_acc, name_acc = info
        print(f"✓ Tài khoản nguồn {account_index}: {name_acc} (ID: {id_acc})")
        break

    while True:
        print(f"\nĐang lấy danh sách Page của tài khoản nguồn {account_index}...")
        selected_pages = get_token_pages(token_acc_page, id_acc)
        if selected_pages:
            break
        retry = input(
            f"\n\033[93m! Không có Page nào được chọn cho tài khoản nguồn {account_index}.\033[0m\n"
            f"  Nhập 'r' để thử lại, 't' để đổi token khác, hoặc 'q' để hủy: "
        ).strip().lower()
        if retry == 'q':
            return None
        if retry == 't':
            return setup_source_account(account_index, allow_cancel=allow_cancel)

    mk = input(f"\nNhập mật khẩu của tài khoản nguồn {account_index}: ").strip()

    return {
        "index": account_index,
        "id": id_acc,
        "name": name_acc,
        "password": mk,
        "pages": selected_pages
    }


def setup_source_from_file(filepath: str) -> List[Dict[str, Any]]:
    """
    Đọc file tài khoản nguồn (uid|pass|token), tự chọn TẤT CẢ Page cho từng tài khoản.
    """
    creds = load_accounts_from_file(filepath)
    if not creds:
        return []

    print(f"\n\033[96m→ Bắt đầu xử lý {len(creds)} tài khoản...\033[0m")

    accounts: List[Dict[str, Any]] = []
    for i, cred in enumerate(creds, 1):
        token = cred["token"]
        password = cred["password"]
        uid_file = cred["uid"]

        print(f"\n\033[94m--- Tài khoản nguồn #{i} (uid: {uid_file}) ---\033[0m")

        # Vẫn gọi API để verify token và lấy name, nhưng fallback về uid_file nếu lỗi
        info = get_id(token)
        if info is None:
            print(f"\033[93m! Token không verify được — vẫn dùng uid từ file: {uid_file}\033[0m")
            id_acc = str(uid_file)
            name_acc = f"(unknown - uid {uid_file})"
        else:
            id_acc_api, name_acc = info
            id_acc = str(uid_file)  # Ưu tiên uid trong file
            print(f"✓ Tài khoản: {name_acc} (uid file: {uid_file} | uid token: {id_acc_api})")

        print("  Đang lấy tất cả Page...")
        all_pages = get_all_pages(token, id_acc)
        if not all_pages:
            print(f"\033[93m! Tài khoản uid {id_acc} không có Page nào. Bỏ qua.\033[0m")
            continue
        print(f"  → Sẽ chuyển TẤT CẢ {len(all_pages)} Page.")
        accounts.append({
            "index": i,
            "id": id_acc,
            "name": name_acc,
            "password": password,
            "pages": all_pages
        })

    return accounts


# ================== MAIN ==================

if __name__ == "__main__":
    print("\033[92m=== CÔNG CỤ CHUYỂN QUYỀN QUẢN TRỊ PAGE FACEBOOK ===\033[0m")
    print("Lưu ý: Sử dụng cho mục đích hợp pháp, bạn phải có quyền quản trị Page.\n")

    # ===== BƯỚC 1: NHẬP TÀI KHOẢN NHẬN PAGE =====
    print("\033[94m===== BƯỚC 1: TÀI KHOẢN NHẬN PAGE =====\033[0m")

    token_nhan = ""
    id_acc_nhan = ""
    name_acc_nhan = ""

    while True:
        token_nhan = input("Nhập token của tài khoản nhận Page: ").strip()
        if not token_nhan:
            print("Token nhận không được để trống.")
            continue

        info_nhan = get_id(token_nhan)
        if info_nhan is None:
            print("\033[91m✗ Token không hợp lệ hoặc không lấy được thông tin tài khoản nhận. Vui lòng nhập lại.\033[0m")
            continue

        id_acc_nhan, name_acc_nhan = info_nhan
        print(f"✓ Tài khoản đích: {name_acc_nhan} (ID: {id_acc_nhan})")
        break

    logger.info("Đang kiểm tra danh sách Page mà tài khoản đích đang quản lý...")
    target_page_ids = get_managed_page_ids(token_nhan)
    if target_page_ids:
        print(f"✓ Tài khoản đích đang quản lý {len(target_page_ids)} Page.")
    else:
        print("! Không lấy được danh sách Page của tài khoản đích (sẽ không bỏ qua Page nào).")

    # ===== BƯỚC 2: THIẾT LẬP CÁC TÀI KHOẢN NGUỒN =====
    print(f"\n\033[94m===== BƯỚC 2: THIẾT LẬP TÀI KHOẢN NGUỒN =====\033[0m")
    print("Chọn phương thức nhập tài khoản nguồn:")
    print("  \033[93m[1]\033[0m Nhập thủ công (từng token, tự chọn Page)")
    print("  \033[93m[2]\033[0m Đọc từ file (định dạng uid|pass|token — tự động chọn TẤT CẢ Page)")

    while True:
        mode = input("Lựa chọn (1/2): ").strip()
        if mode in ("1", "2"):
            break
        print("Vui lòng nhập 1 hoặc 2.")

    source_accounts: List[Dict[str, Any]] = []

    if mode == "2":
        while True:
            filepath = input("Nhập đường dẫn file tài khoản nguồn: ").strip().strip('"').strip("'")
            if not filepath:
                print("Đường dẫn không được để trống.")
                continue
            source_accounts = setup_source_from_file(filepath)
            if source_accounts:
                break
            print("\033[91m✗ Không đọc được tài khoản nào từ file. Nhập lại đường dẫn hoặc Ctrl+C để thoát.\033[0m")
    else:
        print("Nhập token từng tài khoản nguồn. \033[93mNhấn Enter (bỏ trống) để kết thúc nhập.\033[0m")
        idx = 1
        while True:
            acc = setup_source_account(idx, allow_cancel=True)
            if acc is None:
                if idx == 1:
                    print("\033[91m! Cần ít nhất 1 tài khoản nguồn để chuyển. Thoát.\033[0m")
                    exit(1)
                print(f"\n✓ Đã nhập xong {len(source_accounts)} tài khoản nguồn.")
                break
            source_accounts.append(acc)
            print(f"✓ Đã thiết lập tài khoản nguồn {idx}: {acc['name']} với {len(acc['pages'])} Page.")
            idx += 1

    if not source_accounts:
        print("\033[91m! Không có tài khoản nguồn nào để xử lý. Thoát.\033[0m")
        exit(1)

    # ===== BƯỚC 3: NHẬP DELAY =====
    while True:
        delay_str = input("\nNhập số giây delay giữa các lần chuyển Page (0 để không delay): ").strip()
        try:
            delay = float(delay_str)
            if delay < 0:
                print("Delay phải >= 0.")
                continue
            break
        except ValueError:
            print("Vui lòng nhập số.")

    # ===== BƯỚC 4: BẮT ĐẦU CHUYỂN =====
    total = sum(len(acc["pages"]) for acc in source_accounts)
    print(f"\n\033[92m===== BẮT ĐẦU CHUYỂN {total} PAGE TỪ {len(source_accounts)} TÀI KHOẢN NGUỒN =====\033[0m")

    success_count = 0
    fail_count = 0
    skip_count = 0
    processed = 0

    for acc in source_accounts:
        id_acc_src = acc["id"]
        name_acc_src = acc["name"]
        mk = acc["password"]

        print(f"\n\033[96m--- Tài khoản nguồn: {name_acc_src} (uid: {id_acc_src}) ---\033[0m")

        for page in acc["pages"]:
            processed += 1
            page_uid = page["page_uid"]
            page_token = page["page_token"]
            page_name = page["page_name"]
            page_id = page["page_id"]

            print(f"\n[{processed}/{total}] Đang xử lý: {page_name} (ID: {page_id})")
            logger.info(f"===== [{processed}/{total}] Xử lý Page: {page_name} (ID: {page_id}) từ nguồn {name_acc_src} =====")

            if page_id in target_page_ids:
                msg = f"⏭️  Page {page_name}: Đã có quyền, bỏ qua."
                print(f"\033[93m{msg}\033[0m")
                logger.info(msg)
                skip_count += 1
                if processed < total:
                    sleep_with_countdown(delay)
                continue

            logger.debug("--- Bước 1: Xác thực mật khẩu ---")
            nt_tree = xac_nhan_mk(page_token, id_acc_nhan, page_uid, mk)
            if not nt_tree:
                msg = f"❌ Page {page_name}: Thất bại ở bước xác thực mật khẩu."
                print(f"\033[91m{msg}\033[0m")
                logger.error(msg)
                fail_count += 1
                if processed < total:
                    sleep_with_countdown(delay)
                continue

            logger.debug("--- Bước 2: Gửi lời mời ---")
            if not gui_loi_moi(page_token, nt_tree):
                msg = f"❌ Page {page_name}: Thất bại khi gửi lời mời."
                print(f"\033[91m{msg}\033[0m")
                logger.error(msg)
                fail_count += 1
                if processed < total:
                    sleep_with_countdown(delay)
                continue

            logger.debug("--- Bước 3: Lấy invitation_id từ tài khoản đích ---")
            invitation_id = ktra_loi_moi(token_nhan, page_uid, id_acc_nhan)
            if not invitation_id:
                msg = f"❌ Page {page_name}: Không lấy được invitation_id."
                print(f"\033[91m{msg}\033[0m")
                logger.error(msg)
                fail_count += 1
                if processed < total:
                    sleep_with_countdown(delay)
                continue

            logger.debug(f"--- Bước 4: Chấp nhận lời mời (invitation_id: {invitation_id}) ---")
            if xac_nhan_loi_moi(token_nhan, invitation_id):
                msg = f"✅ Page {page_name}: Chuyển quyền thành công!"
                print(f"\033[92m{msg}\033[0m")
                logger.info(msg)
                success_count += 1
            else:
                msg = f"❌ Page {page_name}: Thất bại ở bước chấp nhận lời mời."
                print(f"\033[91m{msg}\033[0m")
                logger.error(msg)
                fail_count += 1

            if processed < total:
                sleep_with_countdown(delay)

    # Tổng kết
    print("\n\033[92m===== KẾT QUẢ TỔNG KẾT =====\033[0m")
    print(f"Tổng số tài khoản nguồn: {len(source_accounts)}")
    print(f"Thành công: {success_count} Page")
    print(f"Thất bại: {fail_count} Page")
    print(f"Bỏ qua (đã có quyền): {skip_count} Page")
    print("Xem chi tiết trong file transfer_page.log")
