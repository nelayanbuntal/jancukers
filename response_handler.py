"""
Enhanced Response Handler System
==================================
Translates API responses to user-friendly messages
"""

# ==========================================
# REGION CODE MAPPING
# ==========================================
REGION_CODE_MAP = {
    'hk2': 'HK2',
    'hk': 'HK',
    'th': 'TH',
    'sg': 'SG',
    'tw': 'TW',
    'us': 'US'
}

# ==========================================
# API RESPONSE PARSER
# ==========================================
class ResponseParser:
    """Parse and translate API responses to user-friendly messages"""
    
    # Response patterns mapping (case-insensitive)
    RESPONSE_PATTERNS = {
        # Success patterns
        'assigned': 'berhasil ✅',
        'success': 'berhasil ✅',
        'successfully': 'berhasil ✅',
        
        # Invalid code patterns
        'invalid': 'kode tidak valid',
        'not found': 'kode tidak ditemukan',
        'not exist': 'kode tidak ada',
        'expired': 'kode expired',
        'used': 'sudah digunakan',
        'already used': 'sudah digunakan',
        'already redeemed': 'sudah di-redeem',
        
        # Device/inventory patterns
        'no device': 'device kosong',
        'device not available': 'device tidak tersedia',
        'no available device': 'device kosong',
        'device full': 'device penuh',
        'inventory full': 'inventory penuh',
        'insufficient': 'device kosong',
        
        # Rate limit patterns
        'rate limit': 'rate limit',
        'too many': 'terlalu banyak request',
        'try again': 'coba lagi',
        'please wait': 'silakan tunggu',
        'slow down': 'terlalu cepat',
        
        # Region/server patterns
        'region': 'region tidak tersedia',
        'server busy': 'server sibuk',
        'server error': 'server error',
        'unavailable': 'tidak tersedia',
        'maintenance': 'maintenance',
        
        # Network patterns
        'timeout': 'timeout',
        'connection': 'koneksi error',
        'network': 'network error',
        
        # Authentication patterns
        'unauthorized': 'tidak terautentikasi',
        'forbidden': 'akses ditolak',
        'session': 'sesi expired',
        
        # Other patterns
        'quota': 'kuota habis',
        'limit reached': 'limit tercapai',
        'not eligible': 'tidak memenuhi syarat',
    }
    
    @staticmethod
    def parse_response(response_msg):
        """
        Parse API response message to simple user-friendly message
        
        Args:
            response_msg (str): Raw API response message
            
        Returns:
            str: User-friendly message
        """
        if not response_msg:
            return "tidak ada respons"
        
        # Convert to lowercase for matching
        msg_lower = response_msg.lower()
        
        # Check each pattern
        for pattern, friendly_msg in ResponseParser.RESPONSE_PATTERNS.items():
            if pattern in msg_lower:
                return friendly_msg
        
        # If no pattern matches, return truncated original message
        # Remove common technical terms
        clean_msg = response_msg.replace('Error:', '').replace('error:', '')
        clean_msg = clean_msg.replace('Exception:', '').replace('exception:', '')
        clean_msg = clean_msg.strip()
        
        # Truncate if too long
        if len(clean_msg) > 30:
            return clean_msg[:27] + "..."
        
        return clean_msg if clean_msg else "respons tidak dikenali"
    
    @staticmethod
    def format_log_message(code, region_key, response_msg, attempt=None):
        """
        Format complete log message for user
        
        Args:
            code (str): Redeem code (will be masked)
            region_key (str): Region key (hk, sg, etc)
            response_msg (str): API response message
            attempt (int, optional): Attempt number
            
        Returns:
            str: Formatted log message
        """
        # Mask code (show first 4 and last 4 chars)
        if len(code) > 8:
            masked_code = f"{code[:4]}-****-{code[-4:]}"
        else:
            masked_code = f"{code[:4]}****"
        
        # Get region code
        region_code = REGION_CODE_MAP.get(region_key.lower(), region_key.upper())
        
        # Parse response
        friendly_msg = ResponseParser.parse_response(response_msg)
        
        # Format with attempt number if provided
        if attempt and attempt > 1:
            return f"Kode {masked_code} → {region_code} : {friendly_msg} (attempt #{attempt})"
        else:
            return f"Kode {masked_code} → {region_code} : {friendly_msg}"
    
    @staticmethod
    def get_emoji_for_response(response_msg):
        """
        Get appropriate emoji based on response type
        
        Args:
            response_msg (str): Response message
            
        Returns:
            str: Emoji
        """
        msg_lower = response_msg.lower()
        
        if any(word in msg_lower for word in ['success', 'assigned', 'berhasil']):
            return '✅'
        elif any(word in msg_lower for word in ['invalid', 'expired', 'used', 'tidak valid']):
            return '❌'
        elif any(word in msg_lower for word in ['rate limit', 'timeout', 'wait', 'busy']):
            return '⏱️'
        elif any(word in msg_lower for word in ['device', 'inventory', 'quota', 'kosong', 'penuh']):
            return '📦'
        elif any(word in msg_lower for word in ['error', 'connection', 'network']):
            return '⚠️'
        else:
            return '❓'

# ==========================================
# ENHANCED RESPONSE MESSAGES
# ==========================================
class ResponseMessages:
    """Collection of detailed response messages"""
    
    # Detailed explanations (for logs or admin)
    DETAILED_MESSAGES = {
        'device_empty': {
            'simple': 'device kosong',
            'detailed': 'Region ini tidak memiliki device yang tersedia saat ini',
            'suggestion': 'Mencoba region lain...'
        },
        'rate_limit': {
            'simple': 'rate limit',
            'detailed': 'Terlalu banyak request ke server',
            'suggestion': 'Menunggu beberapa detik...'
        },
        'invalid_code': {
            'simple': 'kode tidak valid',
            'detailed': 'Kode tidak ditemukan atau format salah',
            'suggestion': 'Kode akan di-skip'
        },
        'already_used': {
            'simple': 'sudah digunakan',
            'detailed': 'Kode ini sudah pernah di-redeem sebelumnya',
            'suggestion': 'Kode akan di-skip'
        },
        'network_error': {
            'simple': 'network error',
            'detailed': 'Koneksi ke server bermasalah',
            'suggestion': 'Mencoba ulang...'
        },
        'server_busy': {
            'simple': 'server sibuk',
            'detailed': 'Server CloudEmulator sedang sibuk',
            'suggestion': 'Mencoba ulang...'
        },
        'success': {
            'simple': 'berhasil ✅',
            'detailed': 'Kode berhasil di-redeem',
            'suggestion': 'Lanjut ke kode berikutnya'
        }
    }
    
    @staticmethod
    def get_suggestion(response_type):
        """Get suggestion based on response type"""
        return ResponseMessages.DETAILED_MESSAGES.get(
            response_type, 
            {}
        ).get('suggestion', 'Melanjutkan proses...')

# ==========================================
# RESPONSE CATEGORIZER
# ==========================================
class ResponseCategorizer:
    """Categorize responses for statistics and decision making"""
    
    CATEGORIES = {
        'SUCCESS': ['success', 'assigned', 'berhasil'],
        'INVALID_CODE': ['invalid', 'not found', 'expired', 'used', 'already'],
        'NO_DEVICE': ['device', 'inventory', 'quota', 'insufficient'],
        'RATE_LIMIT': ['rate limit', 'too many', 'slow down', 'wait'],
        'NETWORK_ERROR': ['timeout', 'connection', 'network'],
        'SERVER_ERROR': ['server', 'maintenance', 'busy', 'unavailable'],
        'AUTH_ERROR': ['unauthorized', 'forbidden', 'session'],
        'UNKNOWN': []
    }
    
    @staticmethod
    def categorize(response_msg):
        """
        Categorize response message
        
        Args:
            response_msg (str): Response message
            
        Returns:
            str: Category name
        """
        if not response_msg:
            return 'UNKNOWN'
        
        msg_lower = response_msg.lower()
        
        for category, keywords in ResponseCategorizer.CATEGORIES.items():
            if any(keyword in msg_lower for keyword in keywords):
                return category
        
        return 'UNKNOWN'
    
    @staticmethod
    def should_retry(category):
        """
        Determine if should retry based on category
        
        Args:
            category (str): Response category
            
        Returns:
            bool: True if should retry
        """
        # Retry for these categories
        retry_categories = ['RATE_LIMIT', 'NETWORK_ERROR', 'SERVER_ERROR', 'NO_DEVICE']
        return category in retry_categories
    
    @staticmethod
    def should_try_next_region(category):
        """
        Determine if should try next region
        
        Args:
            category (str): Response category
            
        Returns:
            bool: True if should try next region
        """
        # Try next region for these categories
        next_region_categories = ['NO_DEVICE', 'SERVER_ERROR', 'UNKNOWN']
        return category in next_region_categories

# ==========================================
# EXAMPLE USAGE
# ==========================================
if __name__ == "__main__":
    # Test cases
    test_responses = [
        ("The code has been assigned successfully", "sg", "ABC1-DEF2-GHI3"),
        ("No available devices in this region", "hk", "JKL4-MNO5-PQR6"),
        ("Invalid activation code", "tw", "STU7-VWX8-YZ90"),
        ("Rate limit exceeded, please try again later", "sg", "AAA1-BBB2-CCC3"),
        ("This code has already been used", "us", "DDD4-EEE5-FFF6"),
        ("Server is currently under maintenance", "hk2", "GGG7-HHH8-III9"),
    ]
    
    parser = ResponseParser()
    categorizer = ResponseCategorizer()
    
    print("="*60)
    print("RESPONSE PARSER TEST")
    print("="*60)
    
    for response, region, code in test_responses:
        # Format message
        formatted = parser.format_log_message(code, region, response)
        
        # Get category
        category = categorizer.categorize(response)
        
        # Get emoji
        emoji = parser.get_emoji_for_response(response)
        
        print(f"\n{emoji} {formatted}")
        print(f"   Category: {category}")
        print(f"   Should retry: {categorizer.should_retry(category)}")
        print(f"   Try next region: {categorizer.should_try_next_region(category)}")
    
    print("\n" + "="*60)