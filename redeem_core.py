"""
Simplified Redeem Core Module v2.3
===================================
Enhanced with:
- User-friendly messages
- Production logging
- Better error handling

Version: 2.3 (Production Ready)
"""

import time
import random
import json
import hashlib
import requests
import os
import threading
from datetime import datetime, timedelta, timezone
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    StaleElementReferenceException,
    WebDriverException
)
import undetected_chromedriver as uc

# Configuration
import config

# Import logger
try:
    from logger import logger, ErrorCategory
except ImportError:
    # Fallback if logger not available
    class FallbackLogger:
        def info(self, msg, **kwargs): print(f"ℹ️ {msg}")
        def warning(self, msg, **kwargs): print(f"⚠️ {msg}")
        def error(self, msg, **kwargs): print(f"❌ {msg}")
        def debug(self, msg, **kwargs): pass
        def log_login_attempt(self, *args, **kwargs): pass
        def log_redeem_attempt(self, *args, **kwargs): pass
    logger = FallbackLogger()
    ErrorCategory = None

# ==========================================
# CONSTANTS
# ==========================================

SECRET_KEY = "2018red8688RendfingerSxxd"

# Region mapping
REGION_MAP = {
    "hk2": {"name": "Hong Kong 2", "idc_code": "HKXC_IDC_01"},
    "hk": {"name": "Hong Kong", "idc_code": "HK_IDC_01"},
    "th": {"name": "Thailand", "idc_code": "TH_IDC_01"},
    "sg": {"name": "Singapore", "idc_code": "SG_IDC_03"},
    "tw": {"name": "Taiwan", "idc_code": "TW_IDC_04"},
    "us": {"name": "United States", "idc_code": "US_IDC_01"}
}

# Android versions
ANDROID_VERSIONS = {
    1: "8.1",
    2: "10.0",
    3: "12.0",
    4: "15.0"
}

# ==========================================
# UTILITY FUNCTIONS
# ==========================================

def mask_sensitive(text, show=4):
    """Mask sensitive data showing only first/last N characters"""
    if not config.ENABLE_SENSITIVE_DATA_MASKING:
        return text
    
    if len(text) <= show * 2:
        return text
    
    return f"{text[:show]}****{text[-show:]}"

def remove_code_safe(target_code, filename):
    """Safely remove code from file"""
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

def log_success(code, success_file):
    """Log successful code"""
    with open(success_file, "a+", encoding="utf8") as f:
        f.write(f"{code}\n")

def log_invalid(code, invalid_file):
    """Log invalid code"""
    with open(invalid_file, "a+", encoding="utf8") as f:
        f.write(f"{code}\n")

def load_codes(file_path):
    """Load codes from file"""
    if not os.path.exists(file_path):
        return []
    with open(file_path, "r", encoding="utf8") as f:
        return [line.strip() for line in f.readlines() if line.strip()]

def generate_sign(params: dict, data: dict = None) -> str:
    """Generate MD5 signature for API request"""
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

# ==========================================
# PROGRESS TRACKER
# ==========================================

class ProgressTracker:
    """Track redeem progress"""
    def __init__(self, total_codes):
        self.total_codes = total_codes
        self.success_count = 0
        self.failed_count = 0
        self.lock = threading.Lock()
    
    def update(self, success=True):
        """Update counters"""
        with self.lock:
            if success:
                self.success_count += 1
            else:
                self.failed_count += 1
    
    def format_status(self):
        """Format current status"""
        processed = self.success_count + self.failed_count
        return (
            f"📊 Progress: {processed}/{self.total_codes} • "
            f"✅ {self.success_count} success • "
            f"❌ {self.failed_count} failed"
        )

# ==========================================
# LOGIN FUNCTION (USER-FRIENDLY VERSION)
# ==========================================

def login(email, password, progress_callback=None, user_id=None):
    """
    Login to CloudEmulator and get credentials
    Returns: (user_id, session_id, uuid) or (None, None, None) on failure
    """
    def update_status(step, is_error=False):
        if progress_callback:
            progress_callback("login", step)
        
        # Log to system
        if is_error:
            logger.error(step, user_id=user_id)
        else:
            logger.debug(step, user_id=user_id)

    # USER-FRIENDLY: Simple progress messages
    update_status("🔐 Memverifikasi akun CloudEmulator...")
    logger.info(f"Login attempt for: {mask_sensitive(email, 3)}", user_id=user_id)

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
        logger.debug("Starting Chrome browser", user_id=user_id)
        driver = uc.Chrome(options=chrome_options)

        update_status("🔐 Membuka halaman login...")
        driver.get("https://www.cloudemulator.net/app/sign-in?channelCode=web")
        time.sleep(4)

        # Handle Agree button
        try:
            agree_button = driver.find_element(By.XPATH, "//button[normalize-space(text())='Agree']")
            agree_button.click()
            logger.debug("Clicked Agree button", user_id=user_id)
        except Exception:
            logger.debug("No Agree button found", user_id=user_id)

        time.sleep(2)
        
        # Click email login button
        try:
            update_status("🔐 Mengisi informasi login...")
            email_btn = WebDriverWait(driver, 12).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'email-login')]"))
            )
            email_btn.click()
            logger.debug("Clicked email login button", user_id=user_id)
        except Exception as e:
            logger.error(f"Email login button not found: {e}", user_id=user_id)
            update_status("❌ Tidak dapat membuka form login", is_error=True)
            return None, None, None

        time.sleep(2)
        
        # Fill email
        try:
            email_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'email')]/input"))
            )
            email_input.send_keys(email)
            logger.debug("Email filled", user_id=user_id)
        except Exception as e:
            logger.error(f"Cannot fill email: {e}", user_id=user_id)
            update_status("❌ Gagal mengisi email", is_error=True)
            return None, None, None

        # Fill password
        try:
            pass_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'password')]/input"))
            )
            pass_input.send_keys(password)
            logger.debug("Password filled", user_id=user_id)
        except Exception as e:
            logger.error(f"Cannot fill password: {e}", user_id=user_id)
            update_status("❌ Gagal mengisi password", is_error=True)
            return None, None, None

        # Click sign in
        try:
            update_status("🔐 Memverifikasi kredensial...")
            login_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "email-login-btn"))
            )
            login_btn.click()
            logger.debug("Clicked sign in button", user_id=user_id)
        except Exception as e:
            logger.error(f"Sign in button not found: {e}", user_id=user_id)
            update_status("❌ Tombol login tidak ditemukan", is_error=True)
            return None, None, None

        update_status("🔐 Menunggu konfirmasi login...")
        time.sleep(7)

        # Read localStorage
        try:
            user_id_result = driver.execute_script("return localStorage.getItem('user_id');")
            session_id = driver.execute_script("return localStorage.getItem('session_id');")
            uuid = driver.execute_script("return localStorage.getItem('uuid');")
            
            if user_id_result and session_id and uuid:
                update_status("✅ Login berhasil! Mempersiapkan proses redeem...")
                logger.log_login_attempt(email, True, user_id=user_id)
                logger.info(f"Login successful for: {mask_sensitive(email, 3)}", user_id=user_id)
                return user_id_result, session_id, uuid
            else:
                update_status("❌ Login gagal. Periksa email dan password Anda.", is_error=True)
                logger.log_login_attempt(email, False, user_id=user_id)
                logger.warning(f"Login failed - credentials not found", user_id=user_id)
                return None, None, None
                
        except Exception as e:
            logger.error(f"Error reading credentials: {e}", user_id=user_id)
            update_status("❌ Tidak dapat membaca data login", is_error=True)
            return None, None, None

    except Exception as e:
        logger.error(f"Critical login error: {e}", user_id=user_id, exc_info=True)
        update_status("❌ Terjadi kesalahan sistem saat login", is_error=True)
        return None, None, None

    finally:
        try:
            if driver:
                driver.quit()
                logger.debug("Chrome closed", user_id=user_id)
        except:
            pass

# ==========================================
# REDEEM FUNCTION (SINGLE API CALL)
# ==========================================

def redeem_code(code_value, user_id_login, session_id, uuid, goods_json, user_id=None):
    """
    Single API call to redeem code
    
    Returns:
        "success" - Code redeemed successfully
        "invalid" - Code is invalid/already used
        "error" - Network/timeout error (should retry same region)
        str - Other response message (should try next region)
    """
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
        "userId": user_id_login,
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
        start_time = time.time()
        response = session.post(
            url, params=params, data=data,
            headers={"User-Agent": "Mozilla/5.0"}, 
            timeout=config.API_REQUEST_TIMEOUT
        )
        response_time = time.time() - start_time
        
        logger.log_api_call(url, response.status_code, response_time, user_id=user_id)
        
        json_resp = response.json()
        msg = json_resp.get('resultMsg', '')
        
        # Check for success
        if 'Assigned' in msg or 'success' in msg.lower():
            return "success"
        
        # Check for invalid
        if 'invalid' in msg.lower() or 'used' in msg.lower():
            return "invalid"
        
        # Return actual message for unknown responses
        return msg if msg else "unknown_response"
    
    except requests.exceptions.Timeout:
        logger.warning(f"API timeout for code: {mask_sensitive(code_value, 4)}", user_id=user_id)
        return "error"
    except requests.exceptions.RequestException as e:
        logger.warning(f"API request error: {e}", user_id=user_id)
        return "error"
    except Exception as e:
        logger.error(f"Unexpected error in redeem_code: {e}", user_id=user_id)
        return "error"

# ==========================================
# MAIN REDEEM PROCESS (USER-FRIENDLY VERSION)
# ==========================================

def run_redeem_process(
    code_file, 
    email, 
    password, 
    region_input, 
    android_version,
    progress_callback=None, 
    user_id=None,
    session_files=None
):
    """
    Main redeem process with user-friendly messages
    
    Args:
        code_file: Path to file containing codes
        email: CloudEmulator email
        password: CloudEmulator password
        region_input: Space-separated region codes (e.g. "hk sg tw")
        android_version: Android version string or number
        progress_callback: Callback function for progress updates
        user_id: Discord user ID for logging
        session_files: Dict with session file paths
    
    Returns:
        dict: Result with success/failed counts
    """
    if user_id is None:
        logger.error("run_redeem_process called without user_id")
        return {
            'success': 0,
            'failed': 0,
            'total': 0,
            'message': 'Error: user_id required'
        }

    logger.info(f"=== Starting redeem process ===", user_id=user_id)

    # Setup session files
    if session_files is None:
        import time as time_module
        timestamp = int(time_module.time())
        session_files = {
            'success': f"success_{user_id}_{timestamp}.txt",
            'invalid': f"invalid_{user_id}_{timestamp}.txt",
            'code_temp': code_file,
            'timestamp': timestamp
        }
    
    success_file = session_files['success']
    invalid_file = session_files['invalid']

    # Load codes
    codes = load_codes(code_file)
    if not codes:
        logger.warning(f"No codes found in {code_file}", user_id=user_id)
        return {
            'success': 0,
            'failed': 0,
            'total': 0,
            'message': 'File kosong atau tidak ditemukan'
        }
    
    logger.info(f"Loaded {len(codes)} codes", user_id=user_id)

    # Handle android version
    if isinstance(android_version, int) or (isinstance(android_version, str) and android_version.isdigit()):
        android_choice = int(android_version)
        if android_choice not in ANDROID_VERSIONS:
            logger.error(f"Invalid android version number: {android_choice}", user_id=user_id)
            return {
                'success': 0,
                'failed': 0,
                'total': 0,
                'message': f'Invalid android version number: {android_choice}. Use 1-4.'
            }
        android_version_str = ANDROID_VERSIONS[android_choice]
    else:
        android_version_str = android_version
        if android_version_str not in config.SUPPORTED_ANDROID_VERSIONS:
            logger.error(f"Invalid android version: {android_version_str}", user_id=user_id)
            return {
                'success': 0,
                'failed': 0,
                'total': 0,
                'message': f'Invalid android version: {android_version}'
            }

    # Parse regions
    region_keys = region_input.lower().split()
    regions = []
    goods_json_list = []
    
    for key in region_keys:
        if key not in REGION_MAP:
            logger.error(f"Invalid region: {key}", user_id=user_id)
            return {
                'success': 0,
                'failed': 0,
                'total': 0,
                'message': f'Invalid region: {key}'
            }
        
        regions.append(key)
        region_info = REGION_MAP[key]
        goods_json = json.dumps({
            "rom_version": android_version_str,
            "idc_code": region_info["idc_code"]
        })
        goods_json_list.append(goods_json)

    logger.info(f"Regions: {', '.join([REGION_MAP[k]['name'] for k in regions])}", user_id=user_id)
    logger.info(f"Android: {android_version_str}", user_id=user_id)

    # Login phase
    if progress_callback:
        progress_callback("login", "🔐 Memulai proses login...")
    
    user_id_login, session_id, uuid = login(email, password, progress_callback, user_id)
    
    if not user_id_login or not session_id or not uuid:
        logger.error("Login failed", user_id=user_id)
        return {
            'success': 0,
            'failed': 0,
            'total': len(codes),
            'message': 'Login gagal. Periksa email/password.'
        }
    
    logger.info(f"Login successful", user_id=user_id)

    # Initialize tracker
    tracker = ProgressTracker(len(codes))
    
    # Spinner for visual feedback
    SPINNER = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]

    # Process each code
    logger.info(f"Starting to process {len(codes)} codes", user_id=user_id)
    
    if progress_callback:
        progress_callback("redeem", f"🎮 Memproses {len(codes)} kode redeem...")

    for idx, raw_code in enumerate(codes):
        clean_code = raw_code.replace("-", "").strip()
        masked_code = mask_sensitive(raw_code, 4)
        
        logger.debug(f"Processing code {idx+1}/{len(codes)}: {masked_code}", user_id=user_id)
        
        region_index = 0
        attempt = 0
        spinner_index = 0
        
        # UNLIMITED RETRY LOOP
        while True:
            attempt += 1
            region_key = regions[region_index]
            region_name = REGION_MAP[region_key]["name"]
            goods_json = goods_json_list[region_index]
            
            # USER-FRIENDLY: Simple progress message
            if progress_callback:
                spinner_symbol = SPINNER[spinner_index % len(SPINNER)]
                progress_callback("redeem", 
                    f"- Kode {raw_code} → {region_name}..."
                )
            
            # Single API call
            result = redeem_code(clean_code, user_id_login, session_id, uuid, goods_json, user_id)
            
            # Log attempt
            logger.log_redeem_attempt(clean_code, region_name, attempt, result, user_id=user_id)
            
            # Handle result
            if result == "success":
                logger.info(f"SUCCESS: {masked_code} on {region_name} (attempt {attempt})", user_id=user_id)
                log_success(raw_code, success_file)
                remove_code_safe(raw_code, code_file)
                tracker.update(success=True)
                
                if progress_callback:
                    progress_callback("redeem", 
                        f"✅ Kode {masked_code} berhasil di-redeem!"
                    )
                break
            
            elif result == "invalid":
                logger.warning(f"INVALID: {masked_code} (attempt {attempt})", user_id=user_id)
                log_invalid(raw_code, invalid_file)
                remove_code_safe(raw_code, code_file)
                tracker.update(success=False)
                
                if progress_callback:
                    progress_callback("redeem", 
                        f"❌ Kode {masked_code} tidak valid atau sudah digunakan"
                    )
                break
            
            elif result == "error":
                logger.warning(f"Network error on {region_name}, retrying", user_id=user_id)
                
                if progress_callback:
                    progress_callback("redeem", 
                        f"⚠️ Koneksi bermasalah, mencoba ulang..."
                    )
                
                if not config.SPEED_MODE:
                    time.sleep(random.uniform(2.0, 4.0))
                
                continue
            
            else:
                logger.debug(f"Unknown response on {region_name}: {result[:50]}", user_id=user_id)
                
                # Rotate to next region
                region_index = (region_index + 1) % len(regions)
                
                if region_index == 0:
                    logger.debug(f"All regions tried for {masked_code}, cycling again", user_id=user_id)
                
                if not config.SPEED_MODE:
                    time.sleep(random.uniform(1.5, 3.5))
                
                spinner_index += 1
                continue
        
        # Update progress
        if progress_callback:
            progress_callback("redeem", tracker.format_status())
        
        # Delay between codes
        if idx < len(codes) - 1 and not config.SPEED_MODE:
            time.sleep(random.uniform(1.0, 2.0))
    
    # Process completed
    logger.info(f"=== Redeem completed: Success={tracker.success_count}, Failed={tracker.failed_count} ===", user_id=user_id)

    return {
        'success': tracker.success_count,
        'failed': tracker.failed_count,
        'total': len(codes),
        'message': 'Process completed successfully'
    }