import requests
import json
import re
import uuid
import time
import logging
from typing import Tuple, Dict, Any, Optional, List, Set

# ================== CẤU HÌNH LOGGING (Đã vô hiệu hóa ghi file) ==================
logger = logging.getLogger()
logger.addHandler(logging.NullHandler())  # Không ghi log ra đâu cả

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
        return True, "Chuyển Page thành công! Tài khoản đích đã là Admin", {}
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
    if "error" in data:
        logger.error(f"Token không hợp lệ: {data['error'].get('message')}")
        return None
    return data.get("id"), data.get("name")

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
    indices = sorted(set(indices))
    return indices

def get_managed_page_ids(token: str) -> Set[str]:
    page_ids = set()
    url = "https://graph.facebook.com/v24.0/me/accounts"
    headers = {
        "Accept-Encoding": "gzip",
        "Connection": "Keep-Alive",
        "Host": "graph.facebook.com",
        "User-Agent": "okhttp/5.1.0",
    }
    params = {
        "fields": "id",
        "access_token": token,
        "limit": 100
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        data = resp.json()
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

def get_token_pages(token: str, profile_id: str) -> List[Dict[str, str]]:
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
        resp = requests.get("https://graph.facebook.com/v24.0/me/accounts", params=params_graph, headers=headers_graph, timeout=30)
        data = resp.json()
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

    parsed = list(pages_dict.values())
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
    except (KeyError, IndexError):
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

# ================== MAIN ==================

if __name__ == "__main__":
    # Banner QUAN AI
    banner = r"""
  ██████╗ ██╗   ██╗ █████╗ ███╗   ██╗     █████╗ ██╗
 ██╔═══██╗██║   ██║██╔══██╗████╗  ██║    ██╔══██╗██║
 ██║   ██║██║   ██║███████║██╔██╗ ██║    ███████║██║
 ██║▄▄ ██║██║   ██║██╔══██║██║╚██╗██║    ██╔══██║██║
 ╚██████╔╝╚██████╔╝██║  ██║██║ ╚████║    ██║  ██║██║
  ╚══▀▀═╝  ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝    ╚═╝  ╚═╝╚═╝
"""
    print(banner)
    print("\033[92m=== CÔNG CỤ CHUYỂN QUYỀN QUẢN TRỊ PAGE FACEBOOK ===\033[0m")
    print("Lưu ý: Nếu chuyển thất bại hãy kiểm tra lại token, pass xem nhé 🤡.\n")

    # Nhập token đích trước
    token_nhan = input("\033[97mNhập token của tài khoản nhận Page: ").strip()
    if not token_nhan:
        print("Token nhận không được để trống.")
        exit(1)

    result = get_id(token_nhan)
    if result is None:
        print("Token đích không hợp lệ, vui lòng chạy lại và nhập token khác.")
        exit(1)
    id_acc_nhan, name_acc_nhan = result
    print(f"\033[93mTài khoản đích: {name_acc_nhan} (ID: {id_acc_nhan})")

    # Nhập delay chung
    while True:
        delay_str = input("\n\033[97mNhập số giây delay giữa các lần chuyển Page (0 để không delay): ").strip()
        try:
            delay = float(delay_str)
            if delay < 0:
                print("Delay phải >= 0.")
                continue
            break
        except ValueError:
            print("Vui lòng nhập số.")

    # Thu thập danh sách token nguồn
    source_accounts = []
    print("\n\033[92m=== NHẬP DANH SÁCH TOKEN CẦN CHUYỂN ===")
    while True:
        token = input("\033[97mNhập token cầm page (hoặc Enter để kết thúc): ").strip()
        if not token or token.lower() == 'done':
            break
        # Lấy thông tin tài khoản
        result = get_id(token)
        if result is None:
            print("Token không hợp lệ, vui lòng nhập lại token khác.")
            continue
        acc_id, acc_name = result
        print(f"\033[93mTài khoản nguồn: {acc_name} (ID: {acc_id})")
        # Lấy danh sách page và chọn
        selected_pages = get_token_pages(token, acc_id)
        if not selected_pages:
            print("\033[97mKhông chọn được Page nào cho token này. Bỏ qua hoặc nhập lại token.")
            continue
        # Nhập mật khẩu cho tài khoản này
        mk = input(f"\033[97mNhập mật khẩu của tài khoản {acc_name}: ").strip()
        # Lưu thông tin
        source_accounts.append({
            'token': token,
            'id': acc_id,
            'name': acc_name,
            'pages': selected_pages,
            'password': mk
        })
        print(f"Đã thêm tài khoản {acc_name} với {len(selected_pages)} Page.\n")

    if not source_accounts:
        print("Không có tài khoản nguồn nào để xử lý.")
        exit(1)

    # Lấy danh sách page mà tài khoản đích đang quản lý
    print("Đang kiểm tra danh sách Page mà tài khoản nhận đang quản lý...")
    target_page_ids = get_managed_page_ids(token_nhan)
    if not target_page_ids:
        print("Cảnh báo: Không lấy được danh sách Page của tài khoản nhận. Sẽ không bỏ qua Page nào.")

    # Bắt đầu xử lý
    total_success = 0
    total_fail = 0
    total_skip = 0
    total_pages = sum(len(acc['pages']) for acc in source_accounts)
    print(f"\n\033[92m=== BẮT ĐẦU CHUYỂN {total_pages} PAGE TỪ {len(source_accounts)} TÀI KHOẢN ===\n")
    for acc_idx, acc in enumerate(source_accounts, 1):
        print(f"\n\033[97m--- Xử lý tài khoản nguồn {acc_idx}/{len(source_accounts)}: {acc['name']} (ID: {acc['id']}) ---")
        for page_idx, page in enumerate(acc['pages'], 1):
            page_uid = page["page_uid"]
            page_token = page["page_token"]
            page_name = page["page_name"]
            page_id = page["page_id"]
            mk = acc['password']

            global_idx = sum(len(a['pages']) for a in source_accounts[:acc_idx-1]) + page_idx

            print(f"===== Bắt đầu xử lý Page [{global_idx}/{total_pages}]: {page_name} (ID: {page_id}) =====")

            if page_id in target_page_ids:
                msg = f"⏭️  {global_idx}. Page {page_name}: Đã có quyền, bỏ qua."
                print(f"\033[93m{msg}\033[0m")
                total_skip += 1
                if not (acc_idx == len(source_accounts) and page_idx == len(acc['pages'])) and delay > 0:
                    time.sleep(delay)
                continue

            # Bước 1
            nt_tree = xac_nhan_mk(page_token, id_acc_nhan, page_uid, mk)
            if not nt_tree:
                msg = f"❌ {global_idx}. Page {page_name}: Thất bại ở bước xác thực mật khẩu."
                print(f"\033[91m{msg}\033[0m")
                total_fail += 1
                if not (acc_idx == len(source_accounts) and page_idx == len(acc['pages'])) and delay > 0:
                    time.sleep(delay)
                continue

            # Bước 2
            success = gui_loi_moi(page_token, nt_tree)
            if not success:
                msg = f"❌ {global_idx}. Page {page_name}: Thất bại khi gửi lời mời."
                print(f"\033[91m{msg}\033[0m")
                total_fail += 1
                if not (acc_idx == len(source_accounts) and page_idx == len(acc['pages'])) and delay > 0:
                    time.sleep(delay)
                continue

            # Bước 3
            invitation_id = ktra_loi_moi(token_nhan, page_uid, id_acc_nhan)
            if not invitation_id:
                msg = f"❌ {global_idx}. Page {page_name}: Không lấy được invitation_id."
                print(f"\033[91m{msg}\033[0m")
                total_fail += 1
                if not (acc_idx == len(source_accounts) and page_idx == len(acc['pages'])) and delay > 0:
                    time.sleep(delay)
                continue

            # Bước 4
            success = xac_nhan_loi_moi(token_nhan, invitation_id)
            if success:
                msg = f"✅ {global_idx}. Page {page_name}: Chuyển quyền thành công!"
                print(f"\033[92m{msg}\033[0m")
                total_success += 1
            else:
                msg = f"❌ {global_idx}. Page {page_name}: Thất bại ở bước chấp nhận lời mời."
                print(f"\033[91m{msg}\033[0m")
                total_fail += 1

            if not (acc_idx == len(source_accounts) and page_idx == len(acc['pages'])) and delay > 0:
                time.sleep(delay)

    # Tổng kết
    print("\n\033[92m===== KẾT QUẢ TỔNG KẾT =====")
    print(f"\033[97mTổng số Page đã xử lý: {total_pages}")
    print(f"\033[97mThành công: {total_success} Page")
    print(f"\033[97mThất bại: {total_fail} Page")
    print(f"\033[97mBỏ qua (đã có quyền): {total_skip} Page")