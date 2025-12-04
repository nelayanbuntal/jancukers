import time
import random
import json
import hashlib
import requests
import os
from datetime import datetime, timedelta, timezone
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
import undetected_chromedriver as uc

def remove_code_safe(target_code, filename):
    target_code = target_code.strip()
    if not os.path.exists(filename):
        return False

    with open(filename, "r", encoding="utf8") as f:
        codes = [c.strip() for c in f.readlines()]

    if target_code not in codes:
        return False

    new_codes = [c for c in codes if c != target_code]
    with open(filename, "w", encoding="utf8") as f:
        f.write("\n".join(new_codes) + ("\n" if new_codes else ""))

    return True

def log_success(code, user_id):
    filename = f"success_{user_id}.txt"
    with open(filename, "a+", encoding="utf8") as f:
        f.write(f"{code}\n")

def log_invalid(code, user_id):
    filename = f"invalid_{user_id}.txt"
    with open(filename, "a+", encoding="utf8") as f:
        f.write(f"{code}\n")

def load_codes(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf8") as f:
        return [line.strip() for line in f.readlines() if line.strip()]

def generate_goods_options(android_choice: int, region_input: str):
    android_versions = {1: "8.1", 2: "10.0", 3: "12.0"}
    if android_choice not in android_versions:
        raise ValueError(f"Invalid android version: {android_choice}")

    rom_version = android_versions[android_choice]
    region_map = {
        "sg": "SG_IDC_03",
        "hk": "HK_IDC_01",
        "us": "US_IDC_01",
        "tw": "TW_IDC_04",
        "th": "TH_IDC_01"
    }

    region_codes = region_input.lower().split()
    json_list = []

    for code in region_codes:
        if code not in region_map:
            raise ValueError(f"Invalid region code '{code}'")
        obj = {"rom_version": rom_version, "idc_code": region_map[code]}
        json_list.append(json.dumps(obj))

    return json_list

SECRET_KEY = "2018red8688RendfingerSxxd"

def generate_sign(params: dict, data: dict = None) -> str:
    items = []
    for k, v in params.items():
        if v:
            items.append((k, str(v)))
    if data:
        for k, v in data.items():
            if v:
                items.append((k, str(v)))
    items.sort(key=lambda x: x[0])
    final_string = "&".join([f"{k}={v}" for k, v in items])
    md5_input = (final_string + SECRET_KEY).encode("utf-8")
    return hashlib.md5(md5_input).hexdigest()

def login(email, password, progress_callback=None):
    def update_status(step):
        if progress_callback:
            progress_callback("login", step)
        print(step)

    update_status("=== LOGIN DEBUG MODE ===")

    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--remote-debugging-port=9222")

    driver = None
    try:
        update_status("[1] Starting Chrome...")
        driver = uc.Chrome(options=chrome_options)

        update_status("[2] Opening login page...")
        driver.get("https://www.cloudemulator.net/app/sign-in?channelCode=web")
        time.sleep(4)
        update_status("[2] Page loaded.")

        try:
            update_status("[3] Checking for Agree button...")
            agree_button = driver.find_element(By.XPATH, "//button[normalize-space(text())='Agree']")
            agree_button.click()
            update_status("[3] Agree clicked.")
        except Exception as e:
            update_status(f"[3] Agree button NOT found: {e}")

        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        time.sleep(2)
        try:
            update_status("[4] Waiting for email login button...")
            email_btn = WebDriverWait(driver, 12).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'email-login')]"))
            )
            email_btn.click()
            update_status("[4] Email login button clicked.")
        except Exception as e:
            update_status(f"[4] ERROR: {e}")
            return None, None, None

        time.sleep(2)
        try:
            update_status("[5] Waiting for email input...")
            email_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'email')]/input"))
            )
            email_input.send_keys(email)
            update_status("[5] Email filled.")
        except Exception as e:
            update_status(f"[5] ERROR: {e}")
            return None, None, None

        try:
            update_status("[6] Waiting for password input...")
            pass_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'password')]/input"))
            )
            pass_input.send_keys(password)
            update_status("[6] Password filled.")
        except Exception as e:
            update_status(f"[6] ERROR: {e}")
            return None, None, None

        try:
            update_status("[7] Waiting for SIGN IN button...")
            login_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "email-login-btn"))
            )
            login_btn.click()
            update_status("[7] SIGN IN clicked.")
        except Exception as e:
            update_status(f"[7] ERROR: {e}")
            return None, None, None

        update_status("[8] Waiting for login result...")
        time.sleep(7)

        try:
            update_status("[9] Reading localStorage tokens...")
            user_id = driver.execute_script("return localStorage.getItem('user_id');")
            session_id = driver.execute_script("return localStorage.getItem('session_id');")
            uuid = driver.execute_script("return localStorage.getItem('uuid');")
            update_status(f"[9] user_id: {user_id}, session_id: {session_id}, uuid: {uuid}")
            return user_id, session_id, uuid
        except Exception as e:
            update_status(f"[9] ERROR reading localStorage: {e}")
            return None, None, None

    except Exception as e:
        update_status(f"CRITICAL LOGIN ERROR: {e}")
        return None, None, None

    finally:
        try:
            if driver:
                update_status("[10] Closing Chrome...")
                driver.quit()
        except:
            pass
        update_status("=== LOGIN DEBUG END ===")

def redeem_code(code_value, user_id, session_id, uuid, goods_json):
    session = requests.Session()
    WIB = timezone(timedelta(hours=7))
    timestamp_ms = int(datetime.now(WIB).timestamp() * 1000)

    params = {
        "lang": "en_US",
        "client": "web",
        "uuid": uuid,
        "versionName": "2.48.20",
        "versionCode": "200480020",
        "languageType": "en_US",
        "sessionId": session_id,
        "userId": user_id,
        "channelCode": "web",
        "serverNode": "tw",
        "timestamp": str(timestamp_ms),
        "userSource": "web",
        "medium": "organic",
        "campaign": "organic"
    }

    data = {"code": code_value, "bizType": "0", "goodsOptionsTypeValueJson": goods_json}
    params["sign"] = generate_sign(params, data)

    url = "https://twplay.redfinger.com/osfingerauth/activation/checkActivationCode.json"

    try:
        response = session.post(
            url, params=params, data=data,
            headers={"User-Agent": "Mozilla/5.0"}, timeout=15
        )
        json_resp = response.json()
        msg = json_resp.get('resultMsg', '')
        if 'Assigned' in msg:
            return "success"
        if 'invalid' in msg:
            return "invalid"
        return msg
    except:
        return "error"

def run_redeem_process(code_file, email, password, region_input, android_choice, progress_callback=None, user_id=None):
    if user_id is None:
        raise ValueError("user_id harus diberikan!")

    log_output = []

    codes = load_codes(code_file)
    if not codes:
        return "File code.txt kosong atau tidak ditemukan."

    goods_json_list = generate_goods_options(android_choice, region_input)

    user_id_login, session_id, uuid = login(email, password, progress_callback)
    if not user_id_login or not session_id or not uuid:
        return "Login gagal. Periksa email/password."

    regions = region_input.split()
    SPINNER = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]

    for raw_code in codes:
        code_value = raw_code.replace("-", "").strip()
        spinner_index = 0
        log_output.append(f"\n=== Memproses kode: {raw_code} ===")
        region_index = 0

        while True:
            region_name = regions[region_index]
            goods_json = goods_json_list[region_index]

            if progress_callback:
                spinner_symbol = SPINNER[spinner_index % len(SPINNER)]
                progress_callback(code_value, f"{spinner_symbol} Memproses kode [{raw_code}] → region {region_name}...")

            result = redeem_code(code_value, user_id_login, session_id, uuid, goods_json)

            if progress_callback:
                spinner_symbol = SPINNER[spinner_index % len(SPINNER)]
                progress_callback(code_value, f"{spinner_symbol} Kode [{raw_code}] → region {region_name}: {result}")

            if result == "success":
                log_success(raw_code, user_id)
                remove_code_safe(raw_code, code_file)
                break

            if result == "invalid":
                log_invalid(raw_code, user_id)
                remove_code_safe(raw_code, code_file)
                break

            if result == "error":
                time.sleep(random.uniform(2.0, 4.0))
                continue

            region_index = (region_index + 1) % len(goods_json_list)
            if region_index == 0:
                log_output.append(f"[{raw_code}] Semua region gagal → ulangi dari region pertama.")

            spinner_index += 1
            time.sleep(random.uniform(1.5, 3.5))

    return "\n".join(log_output)
