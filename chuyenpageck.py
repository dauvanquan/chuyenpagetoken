import requests, json, os, sys,uuid ,re ,random 
from threading import Thread
import threading
from datetime import datetime
from time import strftime
from time import sleep
from sys import platform
def random_rgb():
    return random.randint(50, 255), random.randint(50, 255), random.randint(50, 255)

def rgb_to_ansi(r, g, b):
    return f'\033[38;2;{r};{g};{b}m'

def banner():
    colors = [rgb_to_ansi(*random_rgb()) for _ in range(21)]
    banner_lines = [
        "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢲⢄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀",
        "⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀",
        "⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⠄⠂⢉⠤⠐⠋⠈⠡⡈⠉⠐⠠⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀",
        "⠀⠀⠀⠀⢀⡀⢠⣤⠔⠁⢀⠀⠀⠀⠀⠀⠀⠀⠈⢢⠀⠀⠈⠱⡤⣤⠄⣀⠀⠀⠀⠀⠀",
        "⠀⠀⠰⠁⠀⣰⣿⠃⠀⢠⠃⢸⠀⠀⠀⠀⠀⠀⠀⠀⠁⠀⠀⠀⠈⢞⣦⡀⠈⡇⠀⠀⠀",
        "⠀⠀⠀⢇⣠⡿⠁⠀⢀⡃⠀⣈⠀⠀⠀⠀⢰⡀⠀⠀⠀⠀⢢⠰⠀⠀⢺⣧⢰⠀⠀⠀⠀",
        "⠀⠀⠀⠈⣿⠁⡘⠀⡌⡇⠀⡿⠸⠀⠀⠀⠈⡕⡄⠀⠐⡀⠈⠀⢃⠀⠀⠾⠇⠀⠀⠀⠀",
        "⠀⠀⠀⠀⠇⡇⠃⢠⠀⠶⡀⡇⢃⠡⡀⠀⠀⠡⠈⢂⡀⢁⠀⡁⠸⠀⡆⠘⡀⠀⠀⠀⠀",
        "⠀⠀⠀⠸⠀⢸⠀⠘⡜⠀⣑⢴⣀⠑⠯⡂⠄⣀⣣⢀⣈⢺⡜⢣⠀⡆⡇⠀⢣⠀⠀⠀⠀",
        "⠀⠀⠀⠇⠀⢸⠀⡗⣰⡿⡻⠿⡳⡅⠀⠀⠀⠀⠈⡵⠿⠿⡻⣷⡡⡇⡇⠀⢸⣇⠀⠀⠀",
        "⠀⠀⢰⠀⠀⡆⡄⣧⡏⠸⢠⢲⢸⠁⠀⠀⠀⠀⠐⢙⢰⠂⢡⠘⣇⡇⠃⠀⠀⢹⡄⠀⠀",
        "⠀⠀⠟⠀⠀⢰⢁⡇⠇⠰⣀⢁⡜⠀⠀⠀⠀⠀⠀⠘⣀⣁⠌⠀⠃⠰⠀⠀⠀⠈⠰⠀⠀",
        "⠀⡘⠀⠀⠀⠀⢊⣤⠀⠀⠤⠄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠤⠄⠀⢸⠃⠀⠀⠀⠀⠀⠃⠀",
        "⢠⠁⢀⠀⠀⠀⠈⢿⡀⠀⠀⠀⠀⠀⠀⢀⡀⠀⠀⠀⠀⠀⠀⢀⠏⠀⠀⠀⠀⠀⠀⠸⠀",
        "⠘⠸⠘⡀⠀⠀⠀⠀⢣⠀⠀⠀⠀⠀⠀⠁⠀⠃⠀⠀⠀⠀⢀⠎⠀⠀⠀⠀⠀⠀⢠⠀⠀⡇",
        "⠀⠇⢆⢃⠀⠀⠀⠀⠀⡏⢲⢤⢀⡀⠀⠀⠀⠀⠀⢀⣠⠄⡚⠀⠀⠀⠀⠀⠀⣾⠀⠀⠀",
        "⢰⠈⢌⢎⢆⠀⠀⠀⠀⠁⣌⠆⡰⡁⠉⠉⠀⠉⠁⡱⡘⡼⠇⠀⠀⠀⠀⢀⢬⠃⢠⠀⡆",
        "⠀⢢⠀⠑⢵⣧⡀⠀⠀⡿⠳⠂⠉⠀⠀⠀⠀⠀⠀⠀⠁⢺⡀⠀⠀⢀⢠⣮⠃⢀⠆⡰⠀",
        "⠀⠀⠑⠄⣀⠙⡭⠢⢀⡀⠀⠁⠄⣀⣀⠀⢀⣀⣀⣀⡠⠂⢃⡀⠔⠱⡞⢁⠄⣁⠔⠁⠀",
        "⠀⠀⠀⠀⠀⢠⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠸⠉⠁⠀⠀⠀⠀",
        "⠀⠀⠀⠀⠀⡄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡇⠀⠀⠀⠀⠀"
    ]
    for i, line in enumerate(banner_lines):
        sys.stdout.write(colors[i % len(colors)] + line + '\n')
        sys.stdout.flush()
        sleep(0.00125)
    print('\033[0m')
den = '\x1b[1;90m'
luc = '\x1b[1;32m'
trang = '\x1b[1;37m'
red = '\x1b[1;31m'
vang = '\x1b[1;33m'
tim = '\x1b[1;35m'
lamd = '\x1b[1;34m'
lam = '\x1b[1;36m'
purple = '\\e[35m'
hong = '\x1b[1;95m'
do="\033[1;31m"
xanh="\033[1;36m"
thanh_xau="\033[1;31m[\033[1;37m=.=\033[1;31m] \033[1;37m=>  \033[1;32m"
thanh_dep="\033[1;31m[\033[1;37m=.=\033[1;31m] \033[1;37m=>  \033[1;32m"
thanh="\033[1;31m[\033[1;37m=.=\033[1;31m] \033[1;37m=>  \033[1;32m"
dem=0
def nghingoi(delay):
    value = delay  
    while value > 1:  
        value -= 0.123
        print(f'''{trang}[{do}NONE-CHUYENPR5{trang}]~[{do}DELAY{trang}]~[{luc}{str(value)[0:5]}{trang}]~>[{do}X    {trang}]''', '               ', end='\r')
        sleep(0.02)
        print(f'''{trang}[{hong}NONE-CHUYENPR5{trang}]~[{lam}DELAY{trang}]~[{luc}{str(value)[0:5]}{trang}]~>[ {tim}X   {trang}]''', '               ', end='\r')
        sleep(0.02)
        print(f'''{trang}[{do}NONE-CHUYENPR5{trang}]~[{luc}DELAY{trang}]~[{luc}{str(value)[0:5]}{trang}]~>[  {do}X  {trang}]''', '               ', end='\r')
        sleep(0.02)
        print(f'''{trang}[{hong}NONE-CHUYENPR5{trang}]~[{vang}DELAY{trang}]~[{luc}{str(value)[0:5]}{trang}]~>[   {tim}X {trang}]''', '               ', end='\r')
        sleep(0.02)
        print(f'''{trang}[{do}NONE-CHUYENPR5{trang}]~[{luc}DELAY{trang}]~[{luc}{str(value)[0:5]}{trang}]~>[    {do}X{trang}]''', '               ', end='\r')
        sleep(0.02)
def thanh(so):
	a= "\033[1;31m"+"────"*so
	for i in range(len(a)):
		sys.stdout.write(a[i])
		sys.stdout.flush()
		sleep(0.003)
	print()
class Facebook:
    def __init__(self, cookie, timeout=15):
        self.cookie = cookie
        self.timeout = timeout
        self.session = requests.Session()
        
        self.session_id = str(uuid.uuid4())
        self.fb_dtsg = ""
        self.jazoest = ""
        self.lsd = ""
        self.name = ""
        self.user_id = ""
        
        # Lấy user_id từ cookie
        i_user_match = re.search(r'i_user=(\d+)', cookie)
        if i_user_match:
            self.user_id = i_user_match.group(1)
        else:
            c_user_match = re.search(r'c_user=(\d+)', cookie)
            if c_user_match:
                self.user_id = c_user_match.group(1)
        
        self.headers = {
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
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "viewport-width": "1366",
            "Cookie": cookie
        }
    
    def get_thongtin(self):
        try:
            if not self.user_id:
                return {'success': False}
            
            # Request đầu tiên
            url = self.session.get(f"https://www.facebook.com/{self.user_id}", headers=self.headers, timeout=self.timeout).url
            response = self.session.get(url, headers=self.headers, timeout=self.timeout).text
            
            # Lấy fb_dtsg
            fb_token = re.findall(r'\["DTSGInitialData",\[\],\{"token":"(.*?)"\}', response)
            if fb_token:
                self.fb_dtsg = fb_token[0]
            
            # Lấy jazoest
            jazo = re.findall(r'jazoest=(.*?)\"', response)
            if jazo:
                self.jazoest = jazo[0]
            
            # Lấy lsd
            lsd_match = re.findall(r'"LSD",\[\],\{"token":"(.*?)"\}', response)
            if lsd_match:
                self.lsd = lsd_match[0]
            
            # Request đến /me
            get = self.session.get("https://www.facebook.com/me", headers=self.headers, timeout=self.timeout).url
            url = "https://www.facebook.com/" + get.split("%2F")[-2] + "/" if "next=" in get else get
            response = self.session.get(url, headers=self.headers, params={"locale": "vi_VN"}, timeout=self.timeout)
            
            # Parse JSON để lấy tên
            data_split = response.text.split('"CurrentUserInitialData",[],{')
            if len(data_split) > 1:
                json_data_raw = "{" + data_split[1].split("},")[0] + "}"
                parsed_data = json.loads(json_data_raw)
                self.user_id = parsed_data.get("USER_ID", self.user_id)
                self.name = parsed_data.get("NAME", "")
            else:
                name_match = re.search(r'<title>(.*?)</title>', response.text)
                if name_match:
                    title = name_match.group(1)
                    self.name = title.split(' | ')[0] if ' | ' in title else title
                else:
                    self.name = "Unknown"
            
            # Kiểm tra lỗi
            if self.user_id == "0" and self.name == "":
                return {'success': False}
            elif "828281030927956" in response.text:
                return {'success': False}
            elif "1501092823525282" in response.text:
                return {'success': False}
            elif "601051028565049" in response.text:
                return {'success': False}
            
            return {
                'success': True,
                'user_id': self.user_id,
                'fb_dtsg': self.fb_dtsg,
                'jazoest': self.jazoest,
                'lsd': self.lsd,
                'name': self.name,
                'session': self.session,
                'session_id': self.session_id,
                'cookie': self.cookie,
                'headers': self.headers
            }
        except Exception as e:
            return {'success': False}

    def get_pro5(self):
        headers={
           	     'authority': 'www.facebook.com',
            	    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
          	      'accept-language': 'vi',
       	         'cookie': self.cookie,
           	     'sec-ch-prefers-color-scheme': 'light',
            	    'sec-ch-ua': '"Chromium";v="106", "Google Chrome";v="106", "Not;A=Brand";v="99"',
            	    'sec-ch-ua-mobile': '?0',
          	      'sec-ch-ua-platform': '"Windows"',
          	      'sec-fetch-dest': 'document',
           	     'sec-fetch-mode': 'navigate',
           	     'sec-fetch-site': 'none',
           	     'sec-fetch-user': '?1',
             	   'upgrade-insecure-requests': '1',
           	     'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36',
            	    'viewport-width': '1366',
        }
        data ={
					'av':self.user_id,
					'fb_dtsg':self.fb_dtsg,
					'jazoest':self.jazoest,
					'fb_api_caller_class':'RelayModern',
					'fb_api_req_friendly_name':'CometSettingsDropdownListQuery',
					'variables':'{"fetchTestUserProfileListCell":false,"includeHorizBadging":false,"inProfileSwitcherEntry":false,"inSimpleHeaderEntry":true,"scale":2}',
					'server_timestamps':'true',
					'doc_id':'8179507702122101',
        }
        try:
            a=requests.post('https://www.facebook.com/api/graphql/', headers=headers,data=data).json()
            get = a['data']['viewer']['actor']['profile_switcher_eligible_profiles']
            tong = get['count']
            data_pro5 = get['nodes']
            print(f'{red}| {vang}{tong} {luc}Page Pro5')
            return data_pro5
        except:
            print(red+'\nKhông Get Được Page Pro5 ')
            return 0

    def chap_nhan(self, id_moi, id_page, name):
        headers = {
            "Host": "www.facebook.com",
            "content-length": "1368",
            "sec-ch-ua": "\"Chromium\";v\u003d\"107\", \"Not\u003dA?Brand\";v\u003d\"24\"",
            "sec-ch-ua-mobile": "?0",
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36",
            "viewport-width": "980",
            "content-type": "application/x-www-form-urlencoded",
            "x-fb-lsd": "DlCuUH2d6LEfs4R3HXWyCL",
            "x-fb-friendly-name": "ProfilePlusCometAcceptOrDeclineAdminInviteMutation",
            "sec-ch-prefers-color-scheme": "dark",
            "sec-ch-ua-platform": "\"Linux\"",
            "accept": "*/*",
            "origin": "https://www.facebook.com",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": "https://www.facebook.com/profile.php?id\u003d100087892570045\u0026notif_id\u003d1670335596145290\u0026notif_t\u003dprofile_plus_admin_invite\u0026ref\u003dnotif",
            "accept-language": "vi-VN,vi;q\u003d0.9,fr-FR;q\u003d0.8,fr;q\u003d0.7,en-US;q\u003d0.6,en;q\u003d0.5",
            "cookie": self.cookie
        }
        data = {
            'av': self.user_id,
            '__user': self.user_id,
            '__a': '1',
            '__dyn': '7AzHJ16UW5Eb8ng5K8G6EjBWobVo66u2i5U4e0ykdwSxucyUco5S3O2Saxa1NwJwpUe8hwaG0Z82_CxS320om78bbwto886C11xmfz81sbzoaEnxO0Bo7O2l2Utwwwi831wiEjwZwlo5qfK6E7e58jwGzE8FU5e7oqBwJK2W5olwUwgojUlDw-wUwxwjFovUy2a0SEuBwJCwLyESE2KwwwOg2cwMwhF8-4UdUcobUak1xwJwxw',
            '__csr': 'gjYmwDPV5kCL4_fcx5FjFbcwBRb4jIHiO_8zEAzFuCWSGtiSSCmyeLiSqqF6RiWAFKh5l4XQ9J29oFGVrKcKEnApUC9qCWUS-8ADhEO6ojxah3miez8XyEVa6p9FWDUPzECbCxC7rCwMwyy48CzobVofkueCwNBAx-8g6CEpguxC322e2qUbFEvypoW5Edozxm3O0y88EkxK9yE25Gmdwo88EaUrwJzU9U2mx66oSfxe6oJw0QRw0-ew0aou0vd04zw4Xw1h-0yE1XQ02ruu07jE0SwE06320l-1fg0wK0c_wpE2Gw7Kw',
            '__req': 'n',
            '__hs': '19332.HYP:comet_pkg.2.1.0.2.1',
            'dpr': '2',
            '__ccg': 'GOOD',
            '__rev': '1006690336',
            '__s': 'pg8xvj:d1f9pk:2fmmqb',
            '__hsi': '7174038987510665339',
            '__comet_req': '15',
            'fb_dtsg': self.fb_dtsg,
            'jazoest': self.jazoest,
            'lsd': 'DlCuUH2d6LEfs4R3HXWyCL',
            '__aaid': '775223720487728',
            '__spin_r': '1006690336',
            '__spin_b': 'trunk',
            '__spin_t': '1670336115',
            'fb_api_caller_class': 'RelayModern',
            'fb_api_req_friendly_name': 'ProfilePlusCometAcceptOrDeclineAdminInviteMutation',
            'variables': '{"input":{"client_mutation_id":"1","actor_id":"' + self.user_id + '","is_accept":true,"profile_admin_invite_id":"' + str(id_moi) + '","user_id":"' + id_page + '"},"scale":2}',
            'server_timestamps': 'true',
            'doc_id': '6535667269801310',
        }
        try:
            chapnhan = requests.post('https://www.facebook.com/api/graphql/', headers=headers, data=data).json()
            check = chapnhan['data']['accept_or_decline_profile_plus_admin_invite']['comet_profile_banner']['notice']['title']['text']
            print(f'{tim} ╰─> {lam}Chấp Nhận Quyền Quản Trị Thành Công')
        except:
            print(red + 'Chấp Nhận Quyền Quản Trị Thất Bại')

    def set_admin(self, id, mk, id_page, name):
        cookie = self.cookie
        ck_pro5 = cookie + '; i_user=' + id_page + ';'
        headers_1 = {
            'authority': 'www.facebook.com',
            'accept': '*/*',
            'accept-language': 'vi,fr-FR;q=0.9,fr;q=0.8,en-US;q=0.7,en;q=0.6',
            'origin': 'https://www.facebook.com',
            'referer': 'https://www.facebook.com/settings/?tab=profile_access',
            'sec-ch-prefers-color-scheme': 'light',
            'sec-ch-ua': '"Chromium";v="106", "Google Chrome";v="106", "Not;A=Brand";v="99"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36',
            'viewport-width': '1074',
            'x-fb-friendly-name': 'ProfilePlusMarkReauthedMutation',
            'x-fb-lsd': 'ywHjyvroP8nBIwLKTYWKxO',
            'cookie': ck_pro5,
        }
        data_1 = {
            'av': id_page,
            '__user': id_page,
            '__a': '1',
            '__dyn': '7AzHxqU5a5Q1ryUqxenFw9uu2i5U4e0ykdwSwAyUco2qwJxS1NwJwpUe8hw6vwb-q7oc81xoswaq221FwgolzUO0n2US2G5Usw9m1YwBgK7o884y0Mo5W3S1lwlE-UqwsUkxe2GewGwsoqBwJK2W5olwUwlu5o4q0GpovUaU3VBwJCwLyES0Io5d08O321bwzwTwNwLwFg667EW26',
            '__csr': 'nf1ld2JWTf4SHVBJ7m8V9fl7LV8WUGbjAHnAmFpKmGiCKrUB7yF8y4Hh4bBK8BDWUohbLBzkdxivUG2aQaBzEgF28hyp8zxi5E9EGcGp162a3eA2udwMzXzokyo7e2a1Rx62-3C4ocEhU6e5oC8yUK8Bws9E5S4Gwb21dwp8sw6gwvUbU2ew920LU1zo5m1fw0Fjw1n-2K00PtE0kIw1pha7A27g0udg04CR00wixW0oy15w7Sg0lPzEkG1zw1b102bE',
            '__req': 'm',
            '__hs': '19328.HYP:comet_plat_default_pkg.2.1.0.2.1',
            'dpr': '1',
            '__ccg': 'GOOD',
            '__rev': '1006673379',
            '__s': 'obqdxp:ldjxfi:qlyl0z',
            '__hsi': '7172443321293327429',
            '__comet_req': '1',
            'fb_dtsg': self.fb_dtsg,
            'jazoest': self.jazoest,
            'lsd': 'ywHjyvroP8nBIwLKTYWKxO',
            '__spin_r': '1006673379',
            '__spin_b': 'trunk',
            '__spin_t': '1669964595',
            'fb_api_caller_class': 'RelayModern',
            'fb_api_req_friendly_name': 'ProfilePlusMarkReauthedMutation',
            'variables': '{"input":{"password":{"sensitive_string_value":"' + str(mk) + '"},"actor_id":"' + str(id_page) + '","client_mutation_id":"1"}}',
            'server_timestamps': 'true',
            'doc_id': '5048033918567225',
        }
        try:
            nhap_mk = requests.post('https://www.facebook.com/api/graphql/', headers=headers_1, data=data_1).json()
            check = nhap_mk['data']['admin_management_mark_reauthed']['reauth_is_successful']
            if str(check) == 'True' or str(check) == 'true':
                pass
            else:
                print(red + 'Mật Khẩu Sai !!')
                return 0
        except:
            print(red + 'Xác Minh Mật Khẩu Thất Bại, Có Thể Bị Block Hãy Thử Lại Sau !!')
            return 0
        headers = {
            'Host': 'www.facebook.com',
            'sec-ch-ua': '"Chromium";v="107", "Not=A?Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36',
            'viewport-width': '980',
            'content-type': 'application/x-www-form-urlencoded',
            'x-fb-lsd': 'bTS-BmlWblhR0XQU4HNRbo',
            'x-fb-friendly-name': 'ProfilePlusCoreAppAdminInviteMutation',
            'sec-ch-ua-platform': '"Linux"',
            'sec-ch-prefers-color-scheme': 'dark',
            'accept': '*/*',
            'origin': 'https://www.facebook.com',
            'sec-fetch-site': 'same-origin',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://www.facebook.com/settings/?tab=profile_access',
            'accept-language': 'vi-VN,vi;q=0.9,fr-FR;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5',
            'cookie': ck_pro5
        }
        data = {
            'av': id_page,
            'fb_dtsg': self.fb_dtsg,
            'jazoest': self.jazoest,
            'fb_api_caller_class': 'RelayModern',
            'fb_api_req_friendly_name': 'ProfilePlusCoreAppAdminInviteMutation',
            'variables': '{"input":{"additional_profile_id":"' + id_page + '","admin_id":"' + id + '","admin_visibility":"Unspecified","grant_full_control":true,"actor_id":"' + id_page + '","client_mutation_id":"2"}}',
            'server_timestamps': 'true',
            'doc_id': '5632879080105060',
            'fb_api_analytics_tags': '["qpl_active_flow_ids=30605361"]'
        }
        try:
            set = requests.post('https://www.facebook.com/api/graphql/', headers=headers, data=data)
            # Ẩn phần print(set.text) để không hiển thị JSON rườm rà
            if id in set.text:
                data_id_moi = set.json()['data']['profile_plus_core_admin_invite']['profile_with_biz_tools']['outgoing_core_app_admin_invites']
                for x in data_id_moi:
                    id_admin = x['admin_profile']['id']
                    name_admin = x['admin_profile']['name']
                    if id_admin == id:
                        id_moi = x['profile_admin_invite_id']
                        break
                print(f'{vang}[{trang}{dem}{vang}] {luc}[{lam}{name} {red}| {trang}{id_page}{luc}]{red} => {luc}[{lam}{name_admin} {red}| {trang}{id}{luc}]{red} =>{luc} SUCCESS - FULL CONTROL')
                return id_moi
            else:
                print(f'{vang}[{trang}{dem}{vang}] {luc}[{lam}{name} {red}| {trang}{id_page}{luc}]{red} => {luc}[{lam}Admin {red}: {trang}{id}{luc}]{red} =>{red} ERROR')
        except:
            print(f'{vang}[{trang}{dem}{vang}] {luc}[{lam}{name} {red}| {trang}{id_page}{luc}]{red} => {luc}[{lam}Admin {red}: {trang}{id}{luc}]{red} =>{red} ERROR')
        return 'None'
os.system("cls" if os.name == "nt" else "clear")
banner()
while True:
    cookie = input(thanh_xau + luc + 'Nhập Cookie Nick Cầm Page Profile: ' + vang)
    mk = input(thanh_xau + luc + 'Nhập Mật Khẩu Nick Cầm Page Profile: ' + den)
    fb = Facebook(cookie)
    thanh(14)
    result = fb.get_thongtin()
    if not result['success']:
        print(red + 'Cookie lỗi hoặc không lấy được thông tin! Thử lại...' + den)
        continue
    print(luc + f'Đăng nhập thành công: {result["name"]} | ID: {result["user_id"]}' + den)
    data_pro5 = fb.get_pro5()
    thanh(14)
    if data_pro5 == 0 or data_pro5 == None:
        print(red + 'Không lấy được danh sách Page Profile! Thử lại...' + den)
        continue
    else:
        break

# Display list with numbers
for idx, item in enumerate(data_pro5, 1):
    profile = item.get('profile', {})
    page_id = profile.get('id', 'Unknown')
    page_name = profile.get('name', 'Unknown')
    print(f"{vang}[{trang}{idx}{vang}] {luc}{page_name} {trang}| {lam}ID: {page_id}")

thanh(14)
# Get user selection
selected_pages = []
while True:
    try:
        print(f'{thanh}{xanh}Co The Chon Nhieu Page (Cach Nhau Boi +, Vi Du: 1+2+3+...)')
        choice = input(f"{thanh_xau}{luc}Chọn STT Page Pro5 cần chuyển (1-{len(data_pro5)}): {vang}")
        
        if choice.lower() == 'all':
            selected_pages = data_pro5.copy()
            print(f"{luc} Đã chọn TẤT CẢ {len(selected_pages)} page{trang}")
            break
        else:
            choices = [int(x.strip()) - 1 for x in choice.split('+')]
            selected_pages = []
            for idx in choices:
                if 0 <= idx < len(data_pro5):
                    selected_pages.append(data_pro5[idx])
                else:
                    print(f"{red} Số thứ tự {idx+1} không hợp lệ!{trang}")
                    raise ValueError
            
            if selected_pages:
                print(f"{luc} Đã chọn {len(selected_pages)} page:{trang}")
                for page in selected_pages:
                    profile = page.get('profile', {})
                    print(f"   {vang}→{trang} {profile.get('name', 'Unknown')} | ID: {profile.get('id', 'Unknown')}")
                break
    except ValueError:
        print(f"{red} Vui lòng nhập số hợp lệ (VD: 1,2,3 hoặc 'all'){trang}")

data_pro5 = selected_pages

chon = input(thanh_xau + luc + 'Bạn Có Muốn Auto Chấp Nhận Quyền Quản Trị Không (y/n): ' + vang)
if chon.lower() == 'y':
    while True:
        cookie_nick = input(thanh_xau + luc + 'Nhập Cookie Nick Cần Set Admin: ' + vang)
        fb2 = Facebook(cookie_nick)
        thanh(14)
        result_nick = fb2.get_thongtin()
        if not result_nick['success']:
            print(red + 'Cookie lỗi! Thử lại...' + den)
            continue
        else:
            id_nick = result_nick['user_id']
            print(luc + f'Đã lấy ID: {id_nick}' + den)
            break
else:
    id_nick = input(thanh_xau + luc + 'Nhập ID Nick Cần Set Admin: ' + vang)

dl = int(input(thanh_xau + luc + 'Nhập Delay (' + vang + '50' + trang + '->' + vang + '100' + luc + '): ' + vang))

dem = 0
for x in data_pro5:
    id_page = x['profile']['id']
    name = x['profile']['name']
    dem += 1
    print(f"\n{luc}{'─'*40}{trang}")
    print(f"{vang}[{trang}{dem}/{len(data_pro5)}{vang}] Đang xử lý: {luc}{name}{trang}")
    id_moi = fb.set_admin(id_nick, mk, id_page, name)
    if id_moi == 0 or id_moi == 'None':
        print(f"{red}❌ Set admin thất bại cho {name}{trang}")
        continue
    if chon.lower() == 'y' and id_moi != 'None':
        fb2.chap_nhan(id_moi, id_page, name)
        nghingoi(dl)
