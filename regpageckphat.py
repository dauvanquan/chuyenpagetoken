import concurrent.futures
from datetime import datetime
import json
import os
import random
import re
import sys
from time import sleep, strftime
import requests

os.system('') # Kích hoạt ANSI escape sequence cho Windows CMD
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

os.system('clear' if os.name == 'posix' else 'cls')
dau = "\033[1;32m~ [✓] => "
s3x = f"""\033[1;93m             
\033[1;32m  ██████╗░███████╗░██████╗░.     ██████╗░██████╗░░█████╗░███████╗
\033[1;35m  ██╔══██╗██╔════╝██╔════╝░.     ██╔══██╗██╔══██╗██╔══██╗██╔════╝
\033[1;32m  ██████╔╝█████╗░░██║░░██╗░.     ██████╔╝██████╔╝██║░░██║██████╗░
\033[1;35m  ██╔══██╗██╔══╝░░██║░░╚██╗.     ██╔═══╝░██╔══██╗██║░░██║╚╚████╗
\033[1;36m  ██║░░██║███████╗╚██████╔╝.     ██║░░░░░██║░░██║╚█████╔╝██████╔╝
\033[1;35m  ╚═╝░░╚═╝╚══════╝░╚═════╝░.     ╚═╝░░░░░╚═╝░░╚═╝░╚╚╚════╝░╚╚╚════╝░
\033[1;37m- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
\033[1;37m- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -"""
for h in s3x:
    sys.stdout.write(h)
    sys.stdout.flush()
    sleep(0.0005)

def format_proxy(proxy_str):
    if not proxy_str:
        return None
    proxy_str = proxy_str.strip()
    parts = proxy_str.split(':')
    
    if len(parts) == 4:
        if parts[1].isdigit():
            host, port, user, pwd = parts
        else:
            user, pwd, host, port = parts
        return f"http://{user}:{pwd}@{host}:{port}"
    elif len(parts) == 2:
        host, port = parts
        return f"http://{host}:{port}"
    return proxy_str

def check_ip_address(proxy_str):
    formatted = format_proxy(proxy_str)
    proxies = {"http": formatted, "https": formatted} if formatted else None
    try:
        res = requests.get("http://ip-api.com/json/?fields=query,country,isp", proxies=proxies, timeout=10)
        if res.status_code == 200:
            data = res.json()
            ip = data.get('query', 'Unknown')
            country = data.get('country', 'Unknown')
            isp = data.get('isp', 'Unknown')
            return f"{ip} ({country} - {isp})"
    except Exception:
        pass
    return "Không check được IP (Proxy lỗi/timeout)"

def get_consistent_device_fingerprint():
    chrome_versions = [
        ("120.0.6099.144", "120"), 
        ("121.0.6167.85", "121"), 
        ("122.0.6261.94", "122"), 
        ("123.0.6312.58", "123"), 
        ("124.0.6367.60", "124")
    ]
    v_full, v_major = random.choice(chrome_versions)
    platforms = ['"Windows"', '"Macintosh"']
    platform = random.choice(platforms)
    
    ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v_full} Safari/537.36"
    sec_ch_ua = f'"Chromium";v="{v_major}", "Google Chrome";v="{v_major}", "Not=A?Brand";v="99"'
    viewport_width = str(random.choice([1366, 1440, 1536, 1920]))
    
    return ua, sec_ch_ua, platform, viewport_width

class reg_pro5:
    def __init__(self, cookies, proxy=None) -> None:
        self.cookies = cookies
        self.update_proxy(proxy)

        ua, sec_ch_ua, platform, viewport_width = get_consistent_device_fingerprint()
        self.ua = ua
        self.sec_ch_ua = sec_ch_ua
        self.platform = platform
        self.viewport_width = viewport_width

        try:
            self.id_acc = self.cookies.split('c_user=')[1].split(';')[0]
        except:
            self.id_acc = ""

        self.headers = {
            "authority": "www.facebook.com",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "accept-language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "cookie": self.cookies,
            "sec-ch-prefers-color-scheme": "light",
            "sec-ch-ua": self.sec_ch_ua,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": self.platform,
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "upgrade-insecure-requests": "1",
            "user-agent": self.ua,
            "viewport-width": self.viewport_width,
        }
        
        self.fb_dtsg = ""
        self.lsd = "AVr-4211_Q"
        self.__rev = "1011500000"
        self.__hs = "19783.HYP:comet_pkg.2.1.0.2.1"
        
        self.refresh_session_info()

    def update_proxy(self, proxy):
        self.proxy = proxy
        self.formatted_proxy = format_proxy(proxy)
        self.proxies_dict = {"http": self.formatted_proxy, "https": self.formatted_proxy} if self.formatted_proxy else None
        
        if not hasattr(self, 'session') or self.session is None:
            self.session = requests.Session()
        
        if self.proxies_dict:
            self.session.proxies.update(self.proxies_dict)
        else:
            self.session.proxies.clear()

    def refresh_session_info(self):
        try:
            res_me = self.session.get("https://www.facebook.com/me", headers=self.headers, timeout=15)
            url_profile = res_me.url
            
            if "checkpoint" in url_profile or "login" in url_profile:
                return

            profile = self.session.get(url_profile, headers=self.headers, timeout=15).text
            
            if 'DTSGInitialData' in profile:
                try:
                    self.fb_dtsg = profile.split('"token":"')[1].split('"')[0]
                except:
                    self.fb_dtsg = profile.split('{"name":"fb_dtsg","value":"')[1].split('"}')[0]
            elif '["DTSGInitData",[],{"token":"' in profile:
                self.fb_dtsg = profile.split('["DTSGInitData",[],{"token":"')[1].split('"')[0]
            else:
                try:
                    self.fb_dtsg = profile.split('{"name":"fb_dtsg","value":"')[1].split('"}')[0]
                except:
                    self.fb_dtsg = profile.split(',"f":"')[1].split('","l":null}')[0]
            
            try:
                self.lsd = profile.split('["LSD",[],{"token":"')[1].split('"')[0]
            except:
                pass

            try:
                rev_match = re.search(r'"rev":\s*(\d+)', profile)
                if rev_match:
                    self.__rev = rev_match.group(1)
            except:
                pass

            try:
                hs_match = re.search(r'"client_revision":\s*"([^"]+)"', profile)
                if hs_match:
                    self.__hs = hs_match.group(1)
            except:
                pass
        except:
            pass

    def warm_up_activity(self):
        try:
            self.session.get(f"https://www.facebook.com/{self.id_acc}", headers=self.headers, timeout=10)
            sleep(random.uniform(2.0, 4.0))
            self.session.get("https://www.facebook.com/", headers=self.headers, timeout=10)
            sleep(random.uniform(3.0, 5.0))
        except Exception:
            pass

    def Reg(self, name):
        if not self.fb_dtsg or not self.id_acc:
            return {"error": "Lấy thông tin tài khoản hoặc fb_dtsg thất bại (Die Cookie / Checkpoint / Proxy chặn)"}

        headers_reg = {
            "authority": "www.facebook.com",
            "accept": "*/*",
            "accept-language": "vi-VN,vi;q=0.9",
            "cookie": self.cookies,
            "origin": "https://www.facebook.com",
            "referer": "https://www.facebook.com/pages/creation?ref_type=launch_point",
            "sec-ch-prefers-color-scheme": "light",
            "sec-ch-ua": self.sec_ch_ua,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": self.platform,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": self.ua,
            "x-fb-friendly-name": "AdditionalProfilePlusCreationMutation",
            "x-fb-lsd": self.lsd,
        }

        data = {
            "av": self.id_acc,
            "__user": self.id_acc,
            "__a": "1",
            "__dyn": "7AzHxq1mxu1syUbFuC0BVU98nwgU29zEdEc8co5S3O2S7o11Ue8hw6vwb-q7oc81xoswIwuo886C11xmfz81sbzoaEnxO0Bo7O2l2Utwwwi831wiEjwZwlo5qfK6E7e58jwGzE8FU5e7oqBwJK2W5olwuEjUlDw-wUws9ovUaU3qxWm2Sq2-azo2NwkQ0z8c84K2e3u362-2B0oobo",
            "__csr": "gP4ZAN2d-hbbRmLObkZO8LvRcXWVvth9d9GGXKSiLCqqr9qEzGTozAXiCgyBhbHrRG8VkQm8GFAfy94bJ7xeufz8jK8yGVVEgx-7oiwxypqCwgF88rzKV8y2O4ocUak4UpDxu3x1K4opAUrwGx63J0Lw-wa90eG18wkE7y14w4hw6Bw2-o069W00CSE0PW06aU02Z3wjU6i0btw3TE1wE5u",
            "__req": "t",
            "__hs": self.__hs,
            "dpr": str(random.choice([1, 1.25, 1.5])),
            "__ccg": "EXCELLENT",
            "__rev": self.__rev,
            "__s": f"{random.choice(['a', 'b', 'c'])}{random.randint(1000,9999)}:x{random.randint(100,999)}",
            "__hsi": str(random.randint(7200000000000000000, 7300000000000000000)),
            "__comet_req": "15",
            "fb_dtsg": self.fb_dtsg,
            "jazoest": str(random.randint(20000, 28000)),
            "lsd": self.lsd,
            "__aaid": "800444344545377",
            "__spin_r": self.__rev,
            "__spin_b": "trunk",
            "__spin_t": str(int(datetime.now().timestamp())),
            "fb_api_caller_class": "RelayModern",
            "fb_api_req_friendly_name": "AdditionalProfilePlusCreationMutation",
            "variables": json.dumps({
                "input": {
                    "bio": "",
                    "categories": ["181475575221097"],
                    "creation_source": "comet",
                    "name": name,
                    "page_referrer": "launch_point",
                    "actor_id": self.id_acc,
                    "client_mutation_id": str(random.randint(1, 999999))
                }
            }),
            "server_timestamps": "true",
            "doc_id": "5903223909690825",
        }

        try:
            response = self.session.post(
                "https://www.facebook.com/api/graphql/",
                headers=headers_reg,
                data=data,
                timeout=20
            )
            
            raw_text = response.text.strip()
            if not raw_text:
                return {"error": "Phản hồi từ Facebook trống (Bị chặn request / Rate limit)"}
            
            if raw_text.startswith("for (;;);"):
                raw_text = raw_text[9:].strip()
                
            try:
                return json.loads(raw_text)
            except json.JSONDecodeError:
                return {"error": f"Phản hồi không phải JSON hợp lệ: {raw_text[:80]}"}
                
        except Exception as e:
            return {"error": str(e)}

    def update_page_avatar(self, page_id, avatar_mode, custom_link=""):
        try:
            img_bytes = None
            if avatar_mode == "1":
                res_img = self.session.get("https://thispersondoesnotexist.com/", timeout=15, headers={"User-Agent": self.ua})
                if res_img.status_code == 200:
                    img_bytes = res_img.content
            elif avatar_mode == "2" and custom_link:
                res_img = self.session.get(custom_link, timeout=15, headers={"User-Agent": self.ua})
                if res_img.status_code == 200:
                    img_bytes = res_img.content

            if not img_bytes:
                return False

            upload_url = "https://www.facebook.com/profile/picture/upload/"
            files = {'file': ('avatar.jpg', img_bytes, 'image/jpeg')}
            data = {
                "av": page_id,
                "__user": self.id_acc,
                "__a": "1",
                "fb_dtsg": self.fb_dtsg,
                "lsd": self.lsd,
            }
            res = self.session.post(upload_url, headers=self.headers, data=data, files=files, timeout=20)
            return True
        except Exception:
            return False

def extract_cookie(line):
    if '|' in line:
        parts = line.split('|')
        for p in parts:
            if 'c_user=' in p and 'xs=' in p:
                return p.strip()
    match = re.search(r'(c_user=\d+;[^|\n]+)', line)
    if match:
        return match.group(1).strip()
    return line.strip()

def get_random_name(name_type):
    if name_type == "1":
        arrayho = ["Nguyễn", "Trần", "Lê", "Phạm", "Hoàng", "Huỳnh", "Võ", "Vũ", "Phan", "Trương", "Bùi", "Đặng", "Đỗ", "Ngô", "Hồ", "Dương", "Đinh"]
        arraylot = ["Văn", "Gia", "Hữu", "Đình", "Thanh", "Minh", "Tuấn", "Hoàng"]
        arrayten = ["Hưng", "Anh", "Đạt", "Tuấn", "Long", "Quốc", "Nam", "Giang", "Khang", "Dương", "Phúc", "Bảo", "Khôi"]
        return f"{random.choice(arrayho)} {random.choice(arraylot)} {random.choice(arrayten)}"
    else:
        first_names = ["James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph", "Thomas", "Charles", "Mary", "Patricia", "Jennifer", "Linda", "Elizabeth"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Miller", "Davis", "Garcia", "Rodriguez", "Wilson"]
        return f"{random.choice(first_names)} {random.choice(last_names)}"

def countdown_delay(dl):
    for ti in range(int(dl), 0, -1):
        print(dau, f"\033[1;31m🌸 Đang Delay Reg Pro5 > {ti} < Giây  ", end="\r"); sleep(0.200)
        print(dau, f"\033[1;32m🌸 Đang Delay Reg Pro5 > {ti} < Giây  ", end="\r"); sleep(0.200)
        print(dau, f"\033[1;33m🌸 Đang Delay Reg Pro5 > {ti} < Giây  ", end="\r"); sleep(0.200)
        print(dau, f"\033[1;35m🌸 Đang Delay Reg Pro5 > {ti} < Giây  ", end="\r"); sleep(0.200)
        print(dau, f"\033[1;36m🌸 Đang Delay Reg Pro5 > {ti} < Giây  ", end="\r"); sleep(0.200)

def run_account(raw_line, initial_proxy, proxies_list, proxy_index_ref, sl_pro5, dl, name_type, avatar_mode, custom_link):
    try:
        cookie = extract_cookie(raw_line)
        if not cookie or 'c_user=' not in cookie:
            print(dau, f"\033[1;31m Cookie không hợp lệ: {raw_line[:30]}...")
            return

        current_proxy = initial_proxy
        current_ip = check_ip_address(current_proxy)
        print(dau, f"\033[1;36m Tài khoản {cookie.split('c_user=')[1].split(';')[0]} đang dùng IP: {current_ip}")

        bot = reg_pro5(cookie, current_proxy)
        if not bot.id_acc or not bot.fb_dtsg:
            print(dau, f"\033[1;31m [UID: {bot.id_acc}] Khởi tạo thất bại hoặc chết cookie/proxy, thử đổi proxy mới...")
            if proxies_list:
                proxy_index_ref[0] = (proxy_index_ref[0] + 1) % len(proxies_list)
                current_proxy = proxies_list[proxy_index_ref[0]]
                bot.update_proxy(current_proxy)
                bot.refresh_session_info()
                current_ip = check_ip_address(current_proxy)
                print(dau, f"\033[1;33m Đã chuyển sang Proxy mới IP: {current_ip}")

        print(dau, f"\033[1;35m [UID: {bot.id_acc}] Đang lướt tương tác giả lập làm nóng tài khoản...")
        bot.warm_up_activity()

        print(dau, f"\033[1;32m Bắt đầu chạy tài khoản ID: {bot.id_acc} (Reg {sl_pro5} page)")

        success_count = 0
        for i in range(1, int(sl_pro5) + 1):
            if success_count > 0 and success_count % 5 == 0:
                if proxies_list:
                    print(dau, f"\033[1;33m [UID: {bot.id_acc}] Đã hoàn thành 5 page, tiến hành get lại proxy mới...")
                    proxy_index_ref[0] = (proxy_index_ref[0] + 1) % len(proxies_list)
                    current_proxy = proxies_list[proxy_index_ref[0]]
                    bot.update_proxy(current_proxy)
                    current_ip = check_ip_address(current_proxy)
                    print(dau, f"\033[1;36m [UID: {bot.id_acc}] Proxy mới: {current_ip}")

            name = get_random_name(name_type)
            res = bot.Reg(name)
            
            is_success = False
            error_msg = ""
            page_id = None
            
            if isinstance(res, dict):
                if "errors" in res:
                    error_msg = str(res.get("errors"))
                elif "error" in res:
                    error_msg = f"Lỗi FB Code: {res.get('error')} - {res.get('errorSummary', '')}"
                elif "data" in res:
                    data_inner = res.get("data")
                    if data_inner and isinstance(data_inner, dict):
                        add_profile = data_inner.get("additional_profile_plus_create")
                        if add_profile and isinstance(add_profile, dict):
                            err_msg_fb = add_profile.get("error_message")
                            page_info = add_profile.get("page")
                            if err_msg_fb:
                                error_msg = err_msg_fb
                            elif page_info and page_info.get("id"):
                                is_success = True
                                page_id = page_info.get("id")
                            else:
                                error_msg = "Không trả về ID Page (Bị chặn ngầm/Checkpoint ẩn)"
                        else:
                            error_msg = "Thiếu trường additional_profile_plus_create"
                    else:
                        error_msg = "Dữ liệu trả về trống"
                else:
                    error_msg = str(res)
            else:
                error_msg = str(res)

            error_lower = error_msg.lower()
            is_fb_account_error = any(kw in error_lower for kw in [
                "fb_dtsg", "lấy thông tin tài khoản", "checkpoint", "die cookie", 
                "quá nhiều lần", "không thể tạo trang", "đã thử tạo trang", "1357001", "1357002"
            ])

            is_network_or_proxy_error = False
            if not is_success and not is_fb_account_error:
                network_keywords = ["proxy", "timeout", "connection", "tunnel", "socket", "refused", "reset", "unreachable", "trống", "eof"]
                if any(kw in error_lower for kw in network_keywords):
                    is_network_or_proxy_error = True

            if is_network_or_proxy_error:
                print(dau, f"\033[1;33m [UID: {bot.id_acc}] Phát hiện lỗi proxy/kết nối mạng ({error_msg}), đang get lại proxy mới...")
                if proxies_list:
                    proxy_index_ref[0] = (proxy_index_ref[0] + 1) % len(proxies_list)
                    current_proxy = proxies_list[proxy_index_ref[0]]
                    bot.update_proxy(current_proxy)
                    current_ip = check_ip_address(current_proxy)
                    print(dau, f"\033[1;32m [UID: {bot.id_acc}] Đã đổi sang proxy mới ({current_ip}), thử lại lượt này...")
                    
                    res = bot.Reg(name)
                    if isinstance(res, dict) and "data" in res:
                        data_inner = res.get("data")
                        if data_inner and isinstance(data_inner, dict):
                            add_profile = data_inner.get("additional_profile_plus_create")
                            if add_profile and add_profile.get("page") and add_profile.get("page").get("id"):
                                is_success = True
                                page_id = add_profile.get("page").get("id")

            if is_success:
                success_count += 1
                print(dau, f"\033[1;32m [UID: {bot.id_acc}] ({success_count}/{sl_pro5}) Reg Thành Công Page: {name} (ID: {page_id})")
                
                if avatar_mode in ["1", "2"] and page_id:
                    print(dau, f"\033[1;35m [UID: {bot.id_acc}] Đang cập nhật Avatar cho Page...")
                    updated = bot.update_page_avatar(page_id, avatar_mode, custom_link)
                    if updated:
                        print(dau, f"\033[1;32m [UID: {bot.id_acc}] Cập nhật Avatar thành công!")
                    else:
                        print(dau, f"\033[1;31m [UID: {bot.id_acc}] Cập nhật Avatar thất bại!")
            else:
                print(dau, f"\033[1;31m [UID: {bot.id_acc}] Lỗi Reg Page ({name}): {error_msg}. Dừng luồng acc này để tránh die!")
                break

            if i < int(sl_pro5):
                countdown_delay(dl + random.randint(2, 5)) # Thêm độ trễ ngẫu nhiên chống quét
    except Exception as e:
        print(dau, f"\033[1;31m Lỗi luồng tài khoản: {str(e)}")

def main():
    try:
        print(dau + "\033[1;35mNhập danh sách Proxy (Mỗi proxy 1 dòng, dán xong bấm Enter 2 lần. Không có thì ấn Enter luôn):")
        proxies = []
        while True:
            try:
                line = input()
                if not line.strip():
                    break
                proxies.append(line.strip())
            except EOFError:
                break

        print(dau + "\033[1;35mNhập danh sách Acc (UID|PASS|COOKIE...):")
        print(dau + "\033[1;33m(Nhập xong bấm Enter 2 lần hoặc gõ 'done' để chạy):")
        lines = []
        while True:
            try:
                line = input()
                if line.strip().lower() == 'done' or (not line.strip() and lines):
                    break
                if line.strip():
                    lines.append(line.strip())
            except EOFError:
                break

        if not lines:
            print(dau + "\033[1;31m Không có tài khoản nào được nhập!")
            return

        sl_pro5 = input(dau + "\033[1;35mNhập số lượng Pro5 muốn reg cho mỗi acc: ").strip()
        dl = input(dau + "\033[1;35mNhập Delay giữa các lần reg (giây): ").strip()
        
        max_threads_str = input(dau + "\033[1;35mNhập số lượng luồng muốn chạy đồng thời: ").strip()
        thread_delay_str = input(dau + "\033[1;35mNhập delay giữa các luồng khởi động (giây): ").strip()

        print(dau + "\033[1;36mChọn loại tên:")
        print(dau + "\033[1;37m[1] Tên Việt Nam")
        print(dau + "\033[1;37m[2] Tên Ngoại (English)")
        name_type = input(dau + "\033[1;35mNhập lựa chọn (1 hoặc 2): ").strip()
        if name_type not in ["1", "2"]:
            name_type = "1"

        print(dau + "\033[1;36mCài đặt Ảnh đại diện (Avatar) cho Page:")
        print(dau + "\033[1;37m[1] Lấy ảnh AI ngẫu nhiên từ ThisPersonDoesNotExist.com")
        print(dau + "\033[1;37m[2] Dán link ảnh trực tiếp (tự động dùng 1 link cho tất cả)")
        print(dau + "\033[1;37m[0] Không up ảnh (Bỏ qua)")
        avatar_mode = input(dau + "\033[1;35mNhập lựa chọn (0, 1 hoặc 2): ").strip()
        
        custom_link = ""
        if avatar_mode == "2":
            custom_link = input(dau + "\033[1;35mNhập đường dẫn trực tiếp của ảnh (URL): ").strip()

        if not sl_pro5.isdigit() or not dl.isdigit() or not max_threads_str.isdigit() or not thread_delay_str.isdigit():
            print(dau + "\033[1;31m Các thông số nhập vào phải là số hợp lệ!")
            return

        max_threads = int(max_threads_str)
        thread_delay = float(thread_delay_str)
        dl_int = int(dl)

        print(dau + f"\033[1;32m Đang chạy {len(lines)} tài khoản với {max_threads} luồng (Delay giữa các luồng: {thread_delay}s)...\n")

        proxy_index_ref = [0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
            for index, raw_line in enumerate(lines):
                initial_proxy = proxies[index % len(proxies)] if proxies else None
                executor.submit(
                    run_account, 
                    raw_line, 
                    initial_proxy, 
                    proxies, 
                    proxy_index_ref, 
                    int(sl_pro5), 
                    dl_int, 
                    name_type, 
                    avatar_mode, 
                    custom_link
                )
                if thread_delay > 0:
                    sleep(thread_delay)

        print(dau + "\033[1;32m Đã hoàn tất tất cả các luồng chạy!")
    except Exception as e:
        print(dau + f"\033[1;31m Lỗi chương trình chính: {str(e)}")

if __name__ == '__main__':
    main()
    # Chống tự tắt CMD khi chạy xong
    input("\n\033[1;33mQuá trình đã kết thúc. Bấm Enter để thoát cửa sổ này...")
