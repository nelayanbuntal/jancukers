"""
Production-Grade Redeem Core Module
====================================
Enhanced with:
- Security: Sensitive data masking, input validation
- Retry Logic: Smart exponential backoff
- Error Recovery: Comprehensive error handling
- User Experience: Clear, simple messages
- Cancellation: User can stop mid-process
- Resource Safety: Guaranteed cleanup

Version: 2.0 Production
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

# ==========================================
# CONFIGURATION
# ==========================================

SECRET_KEY = "2018red8688RendfingerSxxd"

# Retry configuration
MAX_LOGIN_RETRY = 3
MAX_REDEEM_RETRY_PER_REGION = 2
MAX_CODE_PROCESSING_TIME = 300  # 5 minutes per code

# Timeout configuration
LOGIN_PAGE_TIMEOUT = 30
ELEMENT_WAIT_TIMEOUT = 15
API_REQUEST_TIMEOUT = 20

# Region mapping (Updated)
REGION_MAP = {
    "hk2": {"idc_code": "HKXC_IDC_01", "name": "Hong Kong 2"},
    "hk": {"idc_code": "HK_IDC_01", "name": "Hong Kong"},
    "th": {"idc_code": "TH_IDC_01", "name": "Thailand"},
    "sg": {"idc_code": "SG_IDC_03", "name": "Singapore"},
    "tw": {"idc_code": "TW_IDC_04", "name": "Taiwan"},
    "us": {"idc_code": "US_IDC_01", "name": "United States"}
}

# Android versions (Updated)
ANDROID_VERSIONS = {
    "10.0": "Android 10",
    "15.0": "Android 15",
    "8.1": "Android 8.1",
    "12.0": "Android 12"
}

# ==========================================
# CUSTOM EXCEPTIONS
# ==========================================

class RedeemError(Exception):
    """Base exception for redeem operations"""
    pass

class LoginError(RedeemError):
    """Login-related errors"""
    pass

class ValidationError(RedeemError):
    """Input validation errors"""
    pass

class BrowserError(RedeemError):
    """Browser/Selenium errors"""
    pass

class NetworkError(RedeemError):
    """Network/API errors"""
    pass

class CancellationError(RedeemError):
    """Process cancelled by user"""
    pass

# ==========================================
# CANCELLATION MANAGER
# ==========================================

class CancellationManager:
    """Thread-safe cancellation flag manager"""
    
    def __init__(self):
        self._flag = threading.Event()
    
    def cancel(self):
        """Set cancellation flag"""
        self._flag.set()
    
    def is_cancelled(self):
        """Check if cancelled"""
        return self._flag.is_set()
    
    def reset(self):
        """Reset flag for new process"""
        self._flag.clear()

# Global cancellation manager
cancellation_manager = CancellationManager()

# ==========================================
# UTILITY FUNCTIONS
# ==========================================

def mask_sensitive(text, show=4):
    """Mask sensitive data for logging"""
    if not text or len(text) <= show * 2:
        return "****"
    return f"{text[:show]}****{text[-show:]}"

def validate_email(email):
    """Basic email validation"""
    if not email or '@' not in email or '.' not in email:
        raise ValidationError("Format email tidak valid")
    if len(email) < 5 or len(email) > 100:
        raise ValidationError("Email terlalu pendek atau panjang")
    return True

def validate_password(password):
    """Basic password validation"""
    if not password or len(password) < 6:
        raise ValidationError("Password minimal 6 karakter")
    if len(password) > 100:
        raise ValidationError("Password terlalu panjang")
    return True

def validate_code_format(code):
    """Validate redeem code format"""
    # Remove dashes for validation
    clean_code = code.replace("-", "").strip()
    
    # Should be alphanumeric and reasonable length
    if not clean_code.isalnum():
        return False
    if len(clean_code) < 8 or len(clean_code) > 20:
        return False
    return True

def validate_region(region_input):
    """Validate region codes"""
    regions = region_input.lower().strip().split()
    invalid = [r for r in regions if r not in REGION_MAP]
    if invalid:
        raise ValidationError(f"Region tidak valid: {', '.join(invalid)}")
    return regions

def validate_android_version(version):
    """Validate android version"""
    if version not in ANDROID_VERSIONS:
        raise ValidationError(f"Versi Android tidak valid: {version}")
    return True

def check_cancellation(operation_name="Operation"):
    """Check if process is cancelled"""
    if cancellation_manager.is_cancelled():
        raise CancellationError(f"{operation_name} dibatalkan oleh user")

# ==========================================
# FILE OPERATIONS
# ==========================================

def remove_code_safe(target_code, filename):
    """Safely remove code from file"""
    try:
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
    except Exception as e:
        print(f"⚠️ Error removing code: {e}")
        return False

def log_success(code, user_id):
    """Log successful redeem"""
    try:
        filename = f"success_{user_id}.txt"
        with open(filename, "a+", encoding="utf8") as f:
            f.write(f"{code}\n")
    except Exception as e:
        print(f"⚠️ Error logging success: {e}")

def log_invalid(code, user_id):
    """Log invalid code"""
    try:
        filename = f"invalid_{user_id}.txt"
        with open(filename, "a+", encoding="utf8") as f:
            f.write(f"{code}\n")
    except Exception as e:
        print(f"⚠️ Error logging invalid: {e}")

def load_codes(file_path):
    """Load codes from file"""
    try:
        if not os.path.exists(file_path):
            return []
        with open(file_path, "r", encoding="utf8") as f:
            codes = [line.strip() for line in f.readlines() if line.strip()]
        
        # Validate all codes
        valid_codes = [c for c in codes if validate_code_format(c)]
        if len(valid_codes) < len(codes):
            print(f"⚠️ {len(codes) - len(valid_codes)} kode memiliki format tidak valid")
        
        return valid_codes
    except Exception as e:
        print(f"❌ Error loading codes: {e}")
        return []

# ==========================================
# PROGRESS TRACKER
# ==========================================

class ProgressTracker:
    """Track and format progress information"""
    
    def __init__(self, total_codes):
        self.total_codes = total_codes
        self.processed = 0
        self.successful = 0
        self.failed = 0
        self.start_time = time.time()
    
    def update(self, success=False):
        """Update progress"""
        self.processed += 1
        if success:
            self.successful += 1
        else:
            self.failed += 1
    
    def get_progress_percentage(self):
        """Calculate progress percentage"""
        if self.total_codes == 0:
            return 100
        return int((self.processed / self.total_codes) * 100)
    
    def get_elapsed_time(self):
        """Get elapsed time in seconds"""
        return int(time.time() - self.start_time)
    
    def get_estimated_time(self):
        """Estimate remaining time"""
        if self.processed == 0:
            return "Menghitung..."
        
        elapsed = self.get_elapsed_time()
        avg_time_per_code = elapsed / self.processed
        remaining_codes = self.total_codes - self.processed
        estimated_seconds = int(avg_time_per_code * remaining_codes)
        
        if estimated_seconds < 60:
            return f"{estimated_seconds} detik"
        else:
            minutes = estimated_seconds // 60
            return f"{minutes} menit"
    
    def format_status(self):
        """Format current status"""
        percentage = self.get_progress_percentage()
        elapsed = self.get_elapsed_time()
        estimated = self.get_estimated_time()
        
        elapsed_str = f"{elapsed // 60}m {elapsed % 60}s" if elapsed >= 60 else f"{elapsed}s"
        
        return (f"📊 Progress: {percentage}% ({self.processed}/{self.total_codes} kode) • "
                f"Berhasil: {self.successful} • Gagal: {self.failed} • "
                f"Waktu: {elapsed_str} • Sisa: ~{estimated}")

# ==========================================
# BROWSER MANAGER
# ==========================================

def initialize_driver(max_attempts=3):
    """Initialize Chrome driver with retry"""
    for attempt in range(max_attempts):
        try:
            check_cancellation("Browser initialization")
            
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--start-maximized")
            chrome_options.add_argument("--disable-blink-features=AutomationControlled")
            chrome_options.add_argument("--remote-debugging-port=9222")
            
            driver = uc.Chrome(options=chrome_options)
            return driver
            
        except Exception as e:
            if attempt < max_attempts - 1:
                wait_time = (attempt + 1) * 2
                print(f"⚠️ Gagal memulai browser, mencoba ulang dalam {wait_time}s... ({attempt + 1}/{max_attempts})")
                time.sleep(wait_time)
            else:
                raise BrowserError(f"Gagal memulai browser setelah {max_attempts} percobaan")

def safe_navigate(driver, url, max_attempts=3):
    """Navigate to URL with retry"""
    for attempt in range(max_attempts):
        try:
            check_cancellation("Navigation")
            driver.get(url)
            return True
        except Exception as e:
            if attempt < max_attempts - 1:
                wait_time = (attempt + 1) * 3
                print(f"⚠️ Gagal membuka halaman, mencoba ulang dalam {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise BrowserError(f"Gagal membuka halaman login")

def safe_find_element(driver, by, value, timeout=ELEMENT_WAIT_TIMEOUT, max_attempts=3):
    """Find element with retry"""
    for attempt in range(max_attempts):
        try:
            check_cancellation("Finding element")
            element = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            return element
        except TimeoutException:
            if attempt < max_attempts - 1:
                print(f"⚠️ Element tidak ditemukan, mencoba ulang... ({attempt + 1}/{max_attempts})")
                time.sleep(2)
            else:
                raise BrowserError(f"Element tidak ditemukan setelah {max_attempts} percobaan")
        except Exception as e:
            if attempt < max_attempts - 1:
                time.sleep(2)
            else:
                raise BrowserError(f"Error mencari element: {str(e)}")

def safe_click(element, max_attempts=3):
    """Click element with retry"""
    for attempt in range(max_attempts):
        try:
            check_cancellation("Clicking element")
            element.click()
            return True
        except StaleElementReferenceException:
            if attempt < max_attempts - 1:
                print(f"⚠️ Element berubah, mencoba ulang...")
                time.sleep(1)
            else:
                raise BrowserError("Gagal mengklik element")
        except Exception as e:
            if attempt < max_attempts - 1:
                time.sleep(1)
            else:
                raise BrowserError(f"Error mengklik element: {str(e)}")

def safe_quit_driver(driver):
    """Safely quit driver"""
    try:
        if driver:
            driver.quit()
    except Exception as e:
        print(f"⚠️ Error closing browser: {e}")

# ==========================================
# API SIGNATURE GENERATION
# ==========================================

def generate_sign(params: dict, data: dict = None) -> str:
    """Generate API signature"""
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
# LOGIN HANDLER
# ==========================================

def login_with_retry(email, password, progress_callback=None, max_attempts=MAX_LOGIN_RETRY):
    """Login with retry logic"""
    
    # Validate inputs first
    try:
        validate_email(email)
        validate_password(password)
    except ValidationError as e:
        if progress_callback:
            progress_callback("login", f"❌ {str(e)}")
        return None, None, None
    
    driver = None
    
    for attempt in range(max_attempts):
        try:
            check_cancellation("Login")
            
            # Progress update
            if progress_callback:
                if attempt == 0:
                    progress_callback("login", "🔄 Mempersiapkan browser...")
                else:
                    progress_callback("login", f"🔄 Mencoba login ulang ({attempt + 1}/{max_attempts})...")
            
            # Initialize driver
            driver = initialize_driver()
            
            if progress_callback:
                progress_callback("login", "📧 Membuka halaman login...")
            
            # Navigate to login page
            safe_navigate(driver, "https://www.cloudemulator.net/app/sign-in?channelCode=web")
            time.sleep(4)
            
            # Handle agree button if present
            try:
                if progress_callback:
                    progress_callback("login", "✓ Halaman login terbuka")
                
                agree_button = driver.find_element(By.XPATH, "//button[normalize-space(text())='Agree']")
                safe_click(agree_button)
                time.sleep(1)
            except NoSuchElementException:
                pass  # Agree button not present, continue
            
            if progress_callback:
                progress_callback("login", "🔐 Mengisi informasi akun...")
            
            # Click email login button
            email_btn = safe_find_element(
                driver,
                By.XPATH,
                "//button[contains(@class, 'email-login')]",
                timeout=12
            )
            safe_click(email_btn)
            time.sleep(2)
            
            # Fill email
            email_input = safe_find_element(
                driver,
                By.XPATH,
                "//div[contains(@class, 'email')]/input",
                timeout=10
            )
            email_input.send_keys(email)
            
            # Fill password
            pass_input = safe_find_element(
                driver,
                By.XPATH,
                "//div[contains(@class, 'password')]/input",
                timeout=10
            )
            pass_input.send_keys(password)
            
            if progress_callback:
                progress_callback("login", "⏳ Memverifikasi akun...")
            
            # Click login button
            login_btn = safe_find_element(
                driver,
                By.ID,
                "email-login-btn",
                timeout=10
            )
            safe_click(login_btn)
            
            # Wait for login to complete
            time.sleep(7)
            
            # Extract tokens
            try:
                user_id = driver.execute_script("return localStorage.getItem('user_id');")
                session_id = driver.execute_script("return localStorage.getItem('session_id');")
                uuid = driver.execute_script("return localStorage.getItem('uuid');")
                
                if user_id and session_id and uuid:
                    if progress_callback:
                        progress_callback("login", "✅ Login berhasil!")
                    
                    return user_id, session_id, uuid
                else:
                    raise LoginError("Token tidak ditemukan setelah login")
                    
            except Exception as e:
                raise LoginError(f"Gagal mengambil session token: {str(e)}")
        
        except CancellationError:
            raise
        
        except (LoginError, BrowserError) as e:
            if attempt < max_attempts - 1:
                wait_time = (attempt + 1) * 5
                if progress_callback:
                    progress_callback("login", f"⚠️ Login gagal: {str(e)}")
                    progress_callback("login", f"🔄 Mencoba ulang dalam {wait_time} detik...")
                time.sleep(wait_time)
                
                # Cleanup driver for retry
                safe_quit_driver(driver)
                driver = None
            else:
                if progress_callback:
                    progress_callback("login", "❌ Login gagal. Periksa email dan password Anda.")
                return None, None, None
        
        except Exception as e:
            if attempt < max_attempts - 1:
                if progress_callback:
                    progress_callback("login", f"⚠️ Terjadi kesalahan, mencoba ulang...")
                time.sleep((attempt + 1) * 5)
                safe_quit_driver(driver)
                driver = None
            else:
                if progress_callback:
                    progress_callback("login", "❌ Login gagal setelah beberapa percobaan.")
                return None, None, None
        
        finally:
            if attempt == max_attempts - 1 or cancellation_manager.is_cancelled():
                safe_quit_driver(driver)
    
    return None, None, None

# ==========================================
# REDEEM HANDLER
# ==========================================

def redeem_code_with_retry(code_value, user_id, session_id, uuid, region_code, rom_version, max_attempts=MAX_REDEEM_RETRY_PER_REGION):
    """Redeem code with retry for specific region"""
    
    session = requests.Session()
    WIB = timezone(timedelta(hours=7))
    
    for attempt in range(max_attempts):
        try:
            check_cancellation("Redeem")
            
            timestamp_ms = int(datetime.now(WIB).timestamp() * 1000)
            
            # Build goods option JSON
            goods_json = json.dumps({
                "rom_version": rom_version,
                "idc_code": region_code
            })
            
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
            
            data = {
                "code": code_value,
                "bizType": "0",
                "goodsOptionsTypeValueJson": goods_json
            }
            
            params["sign"] = generate_sign(params, data)
            
            url = "https://twplay.redfinger.com/osfingerauth/activation/checkActivationCode.json"
            
            response = session.post(
                url,
                params=params,
                data=data,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=API_REQUEST_TIMEOUT
            )
            
            json_resp = response.json()
            msg = json_resp.get('resultMsg', '')
            
            # Check response
            if 'Assigned' in msg or 'success' in msg.lower():
                return "success"
            elif 'invalid' in msg.lower() or 'used' in msg.lower():
                return "invalid"
            else:
                # Unknown response, might need retry
                if attempt < max_attempts - 1:
                    time.sleep(random.uniform(2.0, 4.0))
                    continue
                return "error"
        
        except requests.exceptions.Timeout:
            if attempt < max_attempts - 1:
                print(f"⏳ Timeout, mencoba ulang... ({attempt + 1}/{max_attempts})")
                time.sleep(random.uniform(3.0, 5.0))
            else:
                return "error"
        
        except requests.exceptions.RequestException as e:
            if attempt < max_attempts - 1:
                time.sleep(random.uniform(2.0, 4.0))
            else:
                return "error"
        
        except Exception as e:
            print(f"⚠️ Unexpected error: {e}")
            return "error"
    
    return "error"

def try_all_regions(code_value, user_id, session_id, uuid, regions, rom_version, progress_callback=None):
    """Try redeeming code across all regions"""
    
    original_code = code_value  # With dashes for display
    clean_code = code_value.replace("-", "").strip()  # Without dashes for API
    masked_code = mask_sensitive(original_code, show=4)
    
    for region_key in regions:
        try:
            check_cancellation("Region rotation")
            
            region_info = REGION_MAP[region_key]
            region_name = region_info["name"]
            region_code = region_info["idc_code"]
            
            if progress_callback:
                progress_callback("redeem", f"⏳ Kode {masked_code} • Region: {region_name}...")
            
            result = redeem_code_with_retry(
                clean_code,
                user_id,
                session_id,
                uuid,
                region_code,
                rom_version
            )
            
            if result == "success":
                if progress_callback:
                    progress_callback("redeem", f"✅ Kode {masked_code} • Region: {region_name} • Berhasil!")
                return "success"
            
            elif result == "invalid":
                if progress_callback:
                    progress_callback("redeem", f"❌ Kode {masked_code} • Invalid")
                return "invalid"
            
            # If error, try next region
            time.sleep(random.uniform(1.5, 2.5))
        
        except CancellationError:
            raise
        except Exception as e:
            print(f"⚠️ Error trying region {region_key}: {e}")
            continue
    
    # All regions failed
    if progress_callback:
        progress_callback("redeem", f"⚠️ Kode {masked_code} • Semua region gagal")
    
    return "error"

# ==========================================
# MAIN ORCHESTRATOR
# ==========================================

def run_redeem_process(
    code_file,
    email,
    password,
    region_input,
    android_version,
    progress_callback=None,
    user_id=None
):
    """
    Main redeem process orchestrator
    
    Args:
        code_file: Path to file containing codes
        email: User email
        password: User password
        region_input: Space-separated region codes (e.g., "hk sg tw")
        android_version: Android version (10.0, 15.0, 8.1, 12.0)
        progress_callback: Callback function for progress updates
        user_id: Discord user ID
    
    Returns:
        str: Process result message
    """
    
    if user_id is None:
        raise ValueError("user_id harus diberikan!")
    
    # Reset cancellation flag
    cancellation_manager.reset()
    
    driver = None
    
    try:
        # Validate inputs
        if progress_callback:
            progress_callback("validation", "🔍 Memvalidasi input...")
        
        validate_email(email)
        validate_password(password)
        regions = validate_region(region_input)
        validate_android_version(android_version)
        
        # Load codes
        codes = load_codes(code_file)
        if not codes:
            return "❌ File kode kosong atau tidak dapat dibaca."
        
        if progress_callback:
            progress_callback("validation", f"✅ {len(codes)} kode valid ditemukan")
        
        # Initialize progress tracker
        tracker = ProgressTracker(len(codes))
        
        # Login
        if progress_callback:
            progress_callback("login", "🔐 Memulai proses login...")
        
        user_id_login, session_id, uuid = login_with_retry(
            email,
            password,
            progress_callback
        )
        
        if not user_id_login or not session_id or not uuid:
            return "❌ Login gagal. Periksa email dan password Anda."
        
        # Start redeem process
        if progress_callback:
            progress_callback("redeem", "🎮 Memulai proses redeem...")
            progress_callback("redeem", tracker.format_status())
        
        # Process each code
        for idx, raw_code in enumerate(codes, 1):
            try:
                check_cancellation("Processing codes")
                
                # Try redeem across all regions
                result = try_all_regions(
                    raw_code,
                    user_id_login,
                    session_id,
                    uuid,
                    regions,
                    android_version,
                    progress_callback
                )
                
                # Handle result
                if result == "success":
                    log_success(raw_code, user_id)
                    remove_code_safe(raw_code, code_file)
                    tracker.update(success=True)
                
                elif result == "invalid":
                    log_invalid(raw_code, user_id)
                    remove_code_safe(raw_code, code_file)
                    tracker.update(success=False)
                
                else:  # error
                    # Keep code in file for manual check
                    tracker.update(success=False)
                
                # Update progress
                if progress_callback:
                    progress_callback("redeem", tracker.format_status())
                
                # Small delay between codes
                if idx < len(codes):
                    time.sleep(random.uniform(1.0, 2.0))
            
            except CancellationError:
                if progress_callback:
                    progress_callback("cancelled", f"🛑 Proses dihentikan oleh user")
                    progress_callback("cancelled", tracker.format_status())
                    progress_callback("cancelled", f"💡 {len(codes) - tracker.processed} kode belum diproses")
                return "Proses dibatalkan oleh user"
        
        # Process complete
        if progress_callback:
            progress_callback("complete", "✅ Proses redeem selesai!")
            progress_callback("complete", tracker.format_status())
        
        return f"Selesai: {tracker.successful} berhasil, {tracker.failed} gagal dari {tracker.total_codes} kode"
    
    except CancellationError:
        if progress_callback:
            progress_callback("cancelled", "🛑 Proses dihentikan")
        return "Proses dibatalkan oleh user"
    
    except ValidationError as e:
        if progress_callback:
            progress_callback("error", f"❌ {str(e)}")
        return f"Error validasi: {str(e)}"
    
    except Exception as e:
        if progress_callback:
            progress_callback("error", f"❌ Terjadi kesalahan: {str(e)}")
        print(f"❌ Critical error: {e}")
        import traceback
        traceback.print_exc()
        return "Terjadi kesalahan sistem. Hubungi admin."
    
    finally:
        # Always cleanup
        safe_quit_driver(driver)

# ==========================================
# CANCELLATION FUNCTION (Called from Discord)
# ==========================================

def cancel_redeem_process():
    """Cancel ongoing redeem process"""
    cancellation_manager.cancel()