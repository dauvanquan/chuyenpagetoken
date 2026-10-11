import requests
import json
import re
import uuid
import time
from typing import Dict, List, Optional
import time
import sys
import random
import time
import math
from datetime import datetime
# ===== RGB TRUE COLOR =====
def rgb(r, g, b, text):
    return f"\033[38;2;{r};{g};{b}m{text}\033[0m"

def gradient_text(text, t_offset=0):
    out = ""
    t = time.time() + t_offset
    for i, ch in enumerate(text):
        if ch == " ":
            out += " "
            continue
        # sin wave → mượt + không bị gắt
        r = int((math.sin(i*0.25 + t) + 1) * 120 + 15)
        g = int((math.sin(i*0.25 + t + 2) + 1) * 120 + 15)
        b = int((math.sin(i*0.25 + t + 4) + 1) * 120 + 15)
        out += rgb(r, g, b, ch)
    return out

def __DELAY__(total_seconds):
    """
    Delay với hiệu ứng hiển thị % từ 0.000000% đến 100.000000%
    Kèm màu RGB đổi liên tục
    """
    steps = int(total_seconds * 100)  # Chia thành 100 bước nhỏ mỗi giây
    for step in range(steps + 1):
        percent = (step / steps) * 100
        # RGB thay đổi theo phần trăm
        r = int((percent / 100) * 255)
        g = int((1 - percent / 100) * 255)
        b = int((percent * 2) % 256)
        
        color_code = f"\033[38;2;{r};{g};{b}m"
        reset = "\033[0m"
        
        sys.stdout.write(f"\r{color_code}[NoneTool] ~~~>: [{percent:.6f}%]{reset}")
        sys.stdout.flush()
        time.sleep(total_seconds / steps)
    
    print(' ' * 50,end='\r')

import sys
import termios
import tty

def input_hidden(prompt=""):
    sys.stdout.write(prompt)
    sys.stdout.flush()

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        buf = ""
        while True:
            ch = sys.stdin.read(1)
            if ch in ("\n", "\r"):
                print()
                break
            elif ch == "\x7f":  # backspace
                if len(buf) > 0:
                    buf = buf[:-1]
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            else:
                buf += ch
                sys.stdout.write("*")
                sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    return buf
class __Runfb__:
    def __init__(self, cookie: str):
        self.cookie = cookie
        self.session_id = str(uuid.uuid4())
        self.fb_info = None
        self.session = None
        
    def get_facebook_info(self, timeout: int = 15) -> Dict:
        try:
            session = requests.Session()
            session_id = str(uuid.uuid4())
            fb_dtsg = ""
            jazoest = ""
            lsd = ""
            name = ""
            user_id = self.cookie.split("c_user=")[1].split(";")[0]
            headers = {
                "authority": "www.facebook.com",
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                "accept-language": "vi",
                "sec-ch-prefers-color-scheme": "light",
                "sec-ch-ua": '"Chromium";v="106", "Google Chrome";v="106", "Not;A=Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "none",
                "sec-fetch-user": "?1",
                "upgrade-insecure-requests": "1",
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36",
                "viewport-width": "1366",
                "Cookie": self.cookie
            }
            url = session.get(f"https://www.facebook.com/{user_id}", headers=headers, timeout=timeout).url
            response = session.get(url, headers=headers, timeout=timeout).text
            fb_token = re.findall(r'\["DTSGInitialData",\[\],\{"token":"(.*?)"\}', response)
            if fb_token:
                fb_dtsg = fb_token[0]
            jazo = re.findall(r'jazoest=(.*?)\"', response)
            if jazo:
                jazoest = jazo[0]
            lsd_match = re.findall(r'"LSD",\[\],\{"token":"(.*?)"\}', response)
            if lsd_match:
                lsd = lsd_match[0]
            get = session.get("https://www.facebook.com/me", headers=headers, timeout=timeout).url
            url = "https://www.facebook.com/" + get.split("%2F")[-2] + "/" if "next=" in get else get
            response = session.get(url, headers=headers, params={"locale": "vi_VN"}, timeout=timeout)

            data_split = response.text.split('"CurrentUserInitialData",[],{')
            json_data_raw = "{" + data_split[1].split("},")[0] + "}"
            parsed_data = json.loads(json_data_raw)

            user_id = parsed_data.get("USER_ID", "0")
            name = parsed_data.get("NAME", "")

            if user_id == "0" and name == "":
                print("[!] Cookie không hợp lệ hoặc đã hết hạn.")
                return {'success': False}
            elif "828281030927956" in response.text:
                print("[!] Tài khoản đang bị checkpoint 956.")
                return {'success': False}
            elif "1501092823525282" in response.text:
                print("[!] Tài khoản đang bị checkpoint 282 (hạn chế quảng cáo).")
                return {'success': False}
            elif "601051028565049" in response.text:
                print("[!] Tài khoản bị chặn hành động (spam).")
                return {'success': False}

            self.session = session
            self.fb_info = {
                'success': True,
                'user_id': user_id,
                'fb_dtsg': fb_dtsg,
                'jazoest': jazoest,
                'lsd': lsd,
                'name': name,
                'session': session,
                'session_id': session_id,
                'cookie': self.cookie,
                'headers': headers
            }
            
            print(gradient_text(f" Đăng nhập thành công: {name} (ID: {user_id})"))
            return self.fb_info

        except Exception as e:
            print(f"[!] Lỗi khi lấy thông tin Facebook: {e}")
            return {'success': False}

    def get_hidden_pages(self) -> List[Dict]:
        """Lấy danh sách các page bị ẩn/xóa/lên lịch xóa"""
        if not self.fb_info or not self.fb_info.get('success'):
            print("[!] Chưa có thông tin tài khoản. Hãy chạy get_facebook_info() trước.")
            return []

        try:
            headers = {
                'authority': 'web.facebook.com',
                'accept': '*/*',
                'accept-language': 'vi-VN,vi;q=0.9',
                'content-type': 'application/x-www-form-urlencoded',
                'cookie': self.cookie,
                'origin': 'https://web.facebook.com',
                'referer': 'https://web.facebook.com/settings/reactivation/?_rdc=1&_rdr',
                'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Linux"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
                'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
                'x-asbd-id': '359341',
                'x-fb-friendly-name': 'ReactivateProfileRootQuery',
                'x-fb-lsd': self.fb_info['lsd'],
            }

            # Tạo spin_t mới
            spin_t = str(int(time.time()))
            
            data = {
                'av': self.fb_info['user_id'],
                '__aaid': '0',
                '__user': self.fb_info['user_id'],
                '__a': '1',
                '__req': '1',
                '__hs': '20576.HYP:comet_pkg.2.1...0',
                'dpr': '2',
                '__ccg': 'GOOD',
                '__rev': '1038681134',
                '__s': f'vlig91:9qfcm6:57pumw',
                '__hsi': '7635467004043313276',
                '__dyn': '7xe5WK1ixt0mUyEqxemh0no6u5U4e1Nxt3odE98K360O8G0IE6u3y4o2Gwfi0LVE4W0qa321Rw8G11wBz81s8hwGwQw9m1YwBgao1aU2sx-3m1mzXw8W58jwGzEaE2iwJK14xm3y3aexfxm16wUwxwl8vw4DwLyEbUGdG1Qw8W0Lo6-bwHwKG4UrwFg2Xwr86C1nwro-5oabDzUiBG2OUqwjVqwLw4ewo83KwHwOwCxG0qu',
                '__csr': 'gLlhk8ItR5NT2lPQslMx7nFmJZaJAkCxnvlAjLVdll3FrAFHPnbGESGCVtfBFcwx49JHXWiy9AVHggVHzVFF-6oiA9zEG9Dwxx3DhEaGJe8CG4pfyHggy42938sKp0Oy8GbyGxK8xHCKim2mdxe2O1dxC6odU6y78zwbu5EW4EgwyyVUbE2rxe3WUiUeU-1XzoC1zyo47Bw9S4o88gwBxm1ewiUyuU7e5o4-bwbq0NE2PwYxO3G1ag9Eogui-262eE2gjU1tUWqbK0lq3G7WBwUwIxp3UKcyQ4Etx65GhUGto621gABwKw4Rx217c0se680t7w05WbBa0dXo0ya0c680uq0qO07P4q5Q6EW0zoG01aDy7g02eew2P8G0ly02vGdyo12obE0mpy7w11Zw',
                '__hsdp': 'l5QxA_QBqQ7EhgEGAjoxRJ6ikyiAh9a8rWDppYFUymgpibcV6zIxbzCfeyquEpwHVbF4uVzJahQSA8gGp9bCBDhHla-8-5KhiHQKWG8oB5qiiWhuVO2dF7tCj9L3_aAVmqiA5T4yowJ9Nb8-36rzU9EeVm3PO8EpBBxu5E9f-OqsLjQAoD6Ol8x1Gau8bpz3FQzBxmyeASl48xq357hF97gigsUuyE621VyQFWwRwsE22wJwiQ2-3cB6x20xU9bws84K1cwuEhw4JzUPweu08pw26o9o1481XpU0Ey0QU5K0om0bqw33o1ZE2Cwpo0qTw3e81bU0t5w5Pw3683Iw2jU0SK0w8',
                '__hblp': '08O2y0PE3FwHg9m48hw4ww26E6m0Lo26yE3XwOwuE0wG361Ww4_xO0T8O08ogd81V89o1481Zo0Ey0QU5K0nK9wXw2DE1k83rwe2u1uw6fw4cwuo0ZO0oe0T898co0K60i-0ajXDw3Q83iw9e0QoS0Z82Cw5YweO0kO0NUeE0SK0w83Sw1fq3G2e26ui0I-6U',
                '__sjsp': 'l5QxA_QBqQ7EhyOGhdy7mQp9d9ah4D82m2ckG8z2kzIxbzCfy2qouwHVbF4-aZK8qJe5pAAKqmt6KAHUzUmVOHQFpokhmAAKAnKswzqhTpAOrM_OdelCAF1x689y2QD4IzwPCx60Ro1e82cw44w5QwcW097w0nmU6m',
                '__comet_req': '15',
                'fb_dtsg': self.fb_info['fb_dtsg'],
                'jazoest': self.fb_info['jazoest'],
                'lsd': self.fb_info['lsd'],
                '__spin_r': '1038681134',
                '__spin_b': 'trunk',
                '__spin_t': spin_t,
                '__crn': 'comet.fbweb.CometReactivateProfileRoute',
                'fb_api_caller_class': 'RelayModern',
                'fb_api_req_friendly_name': 'ReactivateProfileRootQuery',
                'server_timestamps': 'true',
                'variables': '{}',
                'doc_id': '9878455382192938',
            }

            response = requests.post(
                'https://web.facebook.com/api/graphql/',
                headers=headers,
                data=data,
                timeout=30
            )
            result = response.json()
            
            # Parse danh sách page
            pages = []
            if 'data' in result:
                viewer = result['data'].get('viewer', {})
                deactivated = viewer.get('deactivated_profiles', {})
                
                # Page đã xóa/lên lịch xóa
                deleted = deactivated.get('deleted', [])
                for item in deleted:
                    profile = item.get('profile', {})
                    pages.append({
                        'id': profile.get('id'),
                        'name': profile.get('name'),
                        'type': 'deleted',
                        'delegate_page_id': item.get('delegate_page_id'),
                        'ttl': item.get('ttl', 0)
                    })
                
                # Page bị vô hiệu hóa
                deactivated_pages = deactivated.get('deactivated', [])
                for item in deactivated_pages:
                    profile = item.get('profile', {})
                    pages.append({
                        'id': profile.get('id'),
                        'name': profile.get('name'),
                        'type': 'deactivated',
                        'delegate_page_id': item.get('delegate_page_id')
                    })
            return pages

        except Exception as e:
            print(f"[!] Lỗi khi lấy danh sách page: {e}")
            import traceback
            traceback.print_exc()
            return []

    def reactivate_page(self, profile_id: str,name: str) -> bool:
        """Kích hoạt lại 1 page"""
        if not self.fb_info or not self.fb_info.get('success'):
            print("[!] Chưa có thông tin tài khoản.")
            return False

        try:
            headers = {
                'authority': 'web.facebook.com',
                'accept': '*/*',
                'accept-language': 'vi-VN,vi;q=0.9',
                'content-type': 'application/x-www-form-urlencoded',
                'cookie': self.cookie,
                'origin': 'https://web.facebook.com',
                'referer': 'https://web.facebook.com/settings/reactivation/?_rdc=1&_rdr',
                'sec-ch-ua': '"Chromium";v="137", "Not/A)Brand";v="24"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Linux"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
                'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
                'x-asbd-id': '359341',
                'x-fb-friendly-name': 'ReactivateProfileMutation',
                'x-fb-lsd': self.fb_info['lsd'],
            }

            spin_t = str(int(time.time()))
            
            variables = json.dumps({
                "profile_id": profile_id,
                "delegate_page_id": None
            })

            data = {
                'av': self.fb_info['user_id'],
                '__aaid': '0',
                '__user': self.fb_info['user_id'],
                '__a': '1',
                '__req': 's',
                '__hs': '20576.HYP:comet_pkg.2.1...0',
                'dpr': '2',
                '__ccg': 'GOOD',
                '__rev': '1038681134',
                '__s': 't6c89k:9qfcm6:uj32u5',
                '__hsi': '7635467378352424931',
                '__dyn': '7xeUjGU5a5Q1ryaxG4Vp41twWwIxu13wFwhUngS3q2ibwNw9G2Sawba1DwUx60GE3Qwb-q7oc81EEc87m221Fwgo9oO0n24oaEnxO0Bo7O2l2Utwqo31wiE4u9x-3m1mzXw8W58jwGzEaE5e3ym2SU4i5oe8cEW4-5pUfEe88o4Wm7-2K0-obUG2-azqwt8eo5d0bS1LyUaUbGxe6Uak0zU8oC1Hg6C13xecwBwWzUlwEKufxamEbbxG1fBG2-1mwto461wweW2K3abxG6E2Uwde6E',
                '__csr': 'gkgD7ihs4YZaxD3ZNaT8ynEaZNbjkXflKFe_Zsys8qSZfkyLhdfHiq9jSyW9nFliL8perQ4eRizamVF-q4EiA9zEGmVUCfV4miGVQq229GQUyWG4q_yHggy44VVA9m49prCoJeUsy8GbyGyEgy8Gd-qV9oW5EN1e4Uoyo4e8x2UlwDzUoxO5ErxO8UboowEwAwyxrz8iypE-4EKu2W0Cu4UfHxbwGzKfwuUCUC1tByo47BwhE5q4u4UG489oSui19wiUyuU7eeAU4Ch2U2Swvo4y0woqxq6E8oswWwiA2q647ALwxwzG0A4-0x8620AoWqbK0lq3G7WBwUUaEmg-bz8J1a7ohxqAuaDm1wwk99obE1dogwhP1u0qK686q06U805vdw0_Uw0e9OkE0TJw28Elw7tyJ04480uq0qO07P4q5Q6EW0zoG01aDy7g0oWweZ00hzU0aQE0IOaw5ow1Ty0a1zoC0gC2W0s503RExU0gvo',
                '__hsdp': 'g_5Qz8wux52yGhFD4EmB8AF13EHeAgF4ANyGy5EtibcV6x4FbGEwokgz8GI5gRKyOeAgY9QghqpQ98h9bHcHEzW7AbpUEhN23cgRaMg41cpcAI4cj352oRN8C8bisiOvgp8eenJAAyUziyuWr48uunCBodXn5x28BB8Ehxqf4aatX2OaAk5yKyGi8bpz22at8Vr66eWjpkgy5Eckt6AAtafgsUuyE621TVzGuEdo7aumP0qUvC4a2S5ZwLxEEkeqeWwsm9CwALwoUGWROpPd0BgG442Z7zo6e4o5m0RU-cU7S1Fzokw7SwcNO0b6A0zU9o5-2dk2qbU5e0uSu0a8wde1rw65xi0q20ii0cdw7Sw9Ccwpo0hlw2oo1IE1xo16EkwJw1B20NE1sU2QwWw2a83Iw7FwFwXw3qU20wNxK0fzw2BE',
                '__hblp': '0EwnF8a83eweC2J0Bogx60Do22z42i2u0F8fU2JwIwpo2Zw8qaxW2O7pE2awOwuE1cU36zQ321WwpU3ny8jwvU5Oczokw7Rgd86m3a0gi16wBw4gw7Rw2b85K0Ao461rweG1DwEyokwCwtU2Xwho1983EwpU3rwe2u1uw6fgsw8y58b88U7C0bcw4eg1wU2owgU98a8y0lK0gy1Yw4qxi2S09BXDw71w23EK0NE2jwd6dwbi3Gi0FE1v83Iw5cw826A2B0Wxy0diw821dway0ie08mwde0VUeE8U8pV8y0GK6U',
                '__sjsp': 'g_5Qz8wux52yGhFy125Ft9aggWaTqh2AijhyaGoB8li8zehEhaiWG86548OaH1kdozHKAgX6ipinjyk98h9bHcHFAWkogJx8WN25jjN3kH10g4NAOlk4cj352oRC89y2QD4IDG6i3zBBCAxG0KFCE1b82cw44w5QG0OU0Au01trwpo',
                '__comet_req': '15',
                'fb_dtsg': self.fb_info['fb_dtsg'],
                'jazoest': self.fb_info['jazoest'],
                'lsd': self.fb_info['lsd'],
                '__spin_r': '1038681134',
                '__spin_b': 'trunk',
                '__spin_t': spin_t,
                '__crn': 'comet.fbweb.CometReactivateProfileRoute',
                'fb_api_caller_class': 'RelayModern',
                'fb_api_req_friendly_name': 'ReactivateProfileMutation',
                'server_timestamps': 'true',
                'variables': variables,
                'doc_id': '30461474920118000',
            }

            response = requests.post(
                'https://web.facebook.com/api/graphql/',
                headers=headers,
                data=data,
                timeout=30
            )
            result = response.json()
#            time=None
            if 'data' in result and 'reactivate_profile' in result['data']:
 #               now = datetime.now()
  #              time = now.strftime("%H:%M:%S")
                print(gradient_text(f'<<{profile_id}>> | <<{name}>> | <<THANH CONG KICH HOAT>>'))
                return True
            elif 'errors' in result:
   #             now = datetime.now()
    #            time = now.strftime("%H:%M:%S")
                error_msg = result['errors'][0].get('message', 'Unknown error')
                print(gradient_text(f'<<{profile_id}>> | <<{name}>> | <<THAT BAI KICH HOAT>> | {error_msg} '))
                return False
            else:
                print(f" Kết quả không xác định cho {profile_id}: {result}")
                return False

        except Exception as e:
            print(f"[!] Lỗi reactivate: {e}")
            return False

    def reactivate_all_pages(self, delay: int = 3) -> None:
        """Kích hoạt lại tất cả page bị ẩn/xóa"""
        pages = self.get_hidden_pages()
        
        if not pages:
            print("❌ Không có page nào cần kích hoạt!")
            sys.exit(0)
        success = 0
        failed = 0
        
        for i, page in enumerate(pages, 1):
            print(f"\r [{i}/{len(pages)}] Kích Hoạt: {page['name']} (ID: {page['id']})",end='\r')
            
            if self.reactivate_page(page['id'], page['name']):
                success += 1
            else:
                failed += 1
            
            if i < len(pages):
            	__DELAY__(delay)

if __name__ == "__main__":
    COOKIE=input_hidden(gradient_text("Nhập Cookie Cần Kích Hoạt Pr5 Ẩn: "))
    print("\r", end="")
    delay=int(input(gradient_text("Delay Sau Khi Kích Hoạt 1 Page: ")))
    bot = __Runfb__(COOKIE)
    info = bot.get_facebook_info()
    if info.get('success'):
        bot.reactivate_all_pages(delay)
    else:
        sys.exit(" Không thể lấy thông tin tài khoản. Kiểm tra lại cookie!")
