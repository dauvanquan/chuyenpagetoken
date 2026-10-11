# -*- coding: utf-8 -*-
import requests
import json
import os

class Color:
    CYAN = '\033[1;96m'
    GREEN = '\033[1;92m'
    YELLOW = '\033[1;93m'
    RED = '\033[1;91m'
    MAGENTA = '\033[1;95m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def banner():
    print(f"""{Color.CYAN}{Color.BOLD}
╔══════════════════════════════════════════════════════════════╗
║             🚀 TOOL AUTO SCAN & ADD PAGE TO BM 🚀            ║
╚══════════════════════════════════════════════════════════════╝
{Color.ENDC}""")

def get_all_managed_pages(access_token):
    """Lấy tất cả page bằng cách phân trang"""
    all_pages = []
    url = "https://graph.facebook.com/v19.0/me/accounts"
    params = {'access_token': access_token, 'limit': 100}
    
    try:
        while url:
            response = requests.get(url, params=params)
            data = response.json()
            
            if 'data' in data:
                all_pages.extend(data['data'])
                print(f"{Color.CYAN}[📊] Đã quét {len(all_pages)} page...{Color.ENDC}")
            
            # Lấy URL trang tiếp theo
            url = data.get('paging', {}).get('next')
            params = None  # URL next đã có sẵn token
            
        return all_pages
    except Exception as e:
        print(f"{Color.RED}[❌] Lỗi kết nối: {e}{Color.ENDC}")
        return all_pages

def request_page_to_bm(business_id, page_id, access_token):
    url = f"https://graph.facebook.com/v19.0/{business_id}/owned_pages"
    payload = {
        'page_id': page_id,
        'access_token': access_token
    }
    try:
        response = requests.post(url, data=payload)
        return response.json()
    except Exception as e:
        return {"error": {"message": str(e)}}

def display_pages(pages):
    """Hiển thị danh sách các page với số thứ tự"""
    print(f"\n{Color.CYAN}{'='*60}{Color.ENDC}")
    print(f"{Color.BOLD}{'STT':<6} {'Page Name':<35} {'Page ID':<15}{Color.ENDC}")
    print(f"{Color.CYAN}{'-'*60}{Color.ENDC}")
    
    for idx, page in enumerate(pages, 1):
        page_name = page.get('name', 'Unknown')
        page_id = page.get('id', 'N/A')
        # Cắt tên nếu quá dài
        if len(page_name) > 34:
            page_name = page_name[:31] + '...'
        print(f"{idx:<6} {page_name:<35} {page_id:<15}")
    
    print(f"{Color.CYAN}{'='*60}{Color.ENDC}")

def get_user_selection(pages):
    """Cho phép người dùng chọn page cụ thể hoặc theo khoảng"""
    print(f"\n{Color.YELLOW}🔍 Chọn chế độ chuyển page:{Color.ENDC}")
    print(f"{Color.CYAN}1. {Color.ENDC}Chuyển TẤT CẢ page")
    print(f"{Color.CYAN}2. {Color.ENDC}Chuyển page theo STT (nhập số hoặc khoảng, VD: 1,3,5 hoặc 1-20)")
    print(f"{Color.CYAN}3. {Color.ENDC}Chuyển page theo ID (nhập ID cách nhau bởi dấu phẩy)")
    
    choice = input(f"\n{Color.YELLOW}👉 Nhập lựa chọn (1/2/3): {Color.ENDC}").strip()
    
    if choice == '1':
        return pages, "all"
    elif choice == '2':
        display_pages(pages)
        stt_input = input(f"\n{Color.YELLOW}📝 Nhập STT page (có thể nhập khoảng, VD: 1-20, 25, 30-40): {Color.ENDC}").strip()
        if not stt_input:
            print(f"{Color.RED}❌ Bạn chưa nhập STT nào!{Color.ENDC}")
            return [], "error"
        
        selected_pages = []
        seen_ids = set()
        parts = [p.strip() for p in stt_input.split(',') if p.strip()]
        
        for part in parts:
            if '-' in part:
                # Xử lý khoảng
                range_parts = part.split('-')
                if len(range_parts) != 2:
                    print(f"{Color.RED}⚠️ Khoảng không hợp lệ: {part}{Color.ENDC}")
                    continue
                start_str = range_parts[0].strip()
                end_str = range_parts[1].strip()
                try:
                    start = int(start_str)
                    end = int(end_str)
                except ValueError:
                    print(f"{Color.RED}⚠️ Khoảng không hợp lệ (phải là số): {part}{Color.ENDC}")
                    continue
                if start > end:
                    print(f"{Color.RED}⚠️ Khoảng không hợp lệ (start > end): {part}{Color.ENDC}")
                    continue
                if start < 1 or end > len(pages):
                    print(f"{Color.RED}⚠️ Khoảng vượt quá phạm vi (1-{len(pages)}): {part}{Color.ENDC}")
                    continue
                for stt in range(start, end + 1):
                    page = pages[stt - 1]
                    pid = page.get('id')
                    if pid not in seen_ids:
                        selected_pages.append(page)
                        seen_ids.add(pid)
            else:
                # Số đơn lẻ
                try:
                    stt = int(part)
                except ValueError:
                    print(f"{Color.RED}⚠️ STT không hợp lệ (phải là số): {part}{Color.ENDC}")
                    continue
                if 1 <= stt <= len(pages):
                    page = pages[stt - 1]
                    pid = page.get('id')
                    if pid not in seen_ids:
                        selected_pages.append(page)
                        seen_ids.add(pid)
                else:
                    print(f"{Color.RED}⚠️ STT {stt} không hợp lệ (phạm vi 1-{len(pages)}){Color.ENDC}")
        
        if selected_pages:
            return selected_pages, "selected"
        else:
            print(f"{Color.RED}❌ Không có page nào được chọn hợp lệ!{Color.ENDC}")
            return [], "error"
    elif choice == '3':
        id_input = input(f"\n{Color.YELLOW}📝 Nhập Page ID (VD: 123456789,987654321): {Color.ENDC}").strip()
        id_list = [x.strip() for x in id_input.split(',') if x.strip()]
        selected_pages = []
        for page_id in id_list:
            found = False
            for page in pages:
                if page.get('id') == page_id:
                    selected_pages.append(page)
                    found = True
                    break
            if not found:
                print(f"{Color.RED}⚠️ Không tìm thấy page với ID: {page_id}{Color.ENDC}")
        return selected_pages, "selected"
    else:
        print(f"{Color.RED}❌ Lựa chọn không hợp lệ!{Color.ENDC}")
        return [], "error"

def main():
    clear_screen()
    banner()
    
    access_token = input(f"{Color.YELLOW}🔑 Nhập Access Token (User Token): {Color.ENDC}").strip()
    business_id = input(f"{Color.YELLOW}🏢 Nhập ID Business Manager (BM ID) nhận Page: {Color.ENDC}").strip()
    
    clear_screen()
    banner()
    
    if not access_token or not business_id:
        print(f"{Color.RED}[⚠️] Token hoặc Business ID không được để trống!{Color.ENDC}")
        return

    print(f"{Color.YELLOW}[⏳] Đang quét danh sách các Page...{Color.ENDC}")
    pages = get_all_managed_pages(access_token)
    
    if not pages:
        print(f"{Color.RED}[❌] Không tìm thấy Page nào hoặc Token thiếu quyền.{Color.ENDC}")
        return

    # Hiển thị danh sách page
    display_pages(pages)
    
    print(f"\n{Color.GREEN}[✨] Tổng cộng: {len(pages)} Page đang được quản lý.{Color.ENDC}")
    
    # Chọn chế độ chuyển page
    selected_pages, mode = get_user_selection(pages)
    
    if mode == "error":
        return
    
    if not selected_pages:
        print(f"{Color.RED}[❌] Không có page nào được chọn!{Color.ENDC}")
        return
    
    # Hiển thị danh sách page sẽ được chuyển
    print(f"\n{Color.CYAN}📋 Danh sách {len(selected_pages)} page sẽ được chuyển:{Color.ENDC}")
    for page in selected_pages:
        print(f"{Color.YELLOW}• {page.get('name')} ({page.get('id')}){Color.ENDC}")
    
    confirm = input(f"\n{Color.YELLOW}❓ Bạn có muốn chạy tiến trình chuyển page không? (y/n): {Color.ENDC}").strip().lower()
    if confirm != 'y':
        print(f"{Color.RED}🛑 Đã hủy tiến trình.{Color.ENDC}")
        return

    print(f"\n{Color.YELLOW}[🚀] Bắt đầu tiến trình chuyển page vào BM {business_id}...{Color.ENDC}")
    success, fail = 0, 0

    for page in selected_pages:
        try:
            page_id = page.get('id')
            page_name = page.get('name')
            
            print(f"👉 Xử lý Page: {Color.BOLD}{page_name}{Color.ENDC} ({page_id})... ", end="", flush=True)
            result = request_page_to_bm(business_id, page_id, access_token)
            
            if ('success' in result and result['success']) or ('access_status' in result):
                print(f"{Color.GREEN}✅ THÀNH CÔNG{Color.ENDC}")
                success += 1
            else:
                err_detail = result.get('error', {})
                err_msg = err_detail.get('message', str(result))
                err_code = err_detail.get('code', '')
                print(f"{Color.RED}❌ THẤT BẠI (Mã lỗi: {err_code} - {err_msg}){Color.ENDC}")
                fail += 1
        except Exception as err:
            print(f"{Color.RED}❌ Lỗi ngoại lệ: {err}{Color.ENDC}")
            fail += 1

    print(f"\n{Color.CYAN}" + "=" * 40 + f"{Color.ENDC}")
    print(f"{Color.GREEN}[🎉] HOÀN TẤT! Thành công: {success} | Thất bại: {fail}{Color.ENDC}")
    print(f"{Color.CYAN}" + "=" * 40 + f"{Color.ENDC}")

if __name__ == "__main__":
    main()
