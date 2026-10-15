"""Define logging constants, result categories and CSV column translations.

Localized result values and column labels are part of the report format.
"""
from enum import Enum

class LogLevel:
    """String constants accepted by the application logging setup."""
    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'
    CRITICAL = 'CRITICAL'

class ResponseCode:
    """HTTP-style status constants available to callers."""
    SUCCESS = 200
    BAD_REQUEST = 400
    REQUEST_TIMEOUT = 408
    INTERNAL_SERVER_ERROR = 500

class ResultCode(Enum):
    """Localized event classifications persisted in crawl reports."""
    Normal = "無法選位"
    Computer = "電腦自動選位"
    VIP = "VIP 座位"
    DISABLE = "身障座位"
    MESSAGEBOX = "反爬蟲驗證-訊息視窗"
    STANDING = "站位"
    RECAPCHA = "反爬蟲驗證-圖片驗證"
    REGISTRATION_TIMEOUT = "選位流程逾時"
    Complete = "完整爬取"

class ResultColumn(Enum):
    """Map internal PageResult field names to localized CSV headings."""
    URL = ("url", "網址")
    TITLE = ("title", "活動標題")
    SCHEDULE = ("schedule", "活動時間")
    LOCATION = ("location", "活動地點")
    ORGANIZER = ("organizer", "主辦單位")
    BOOKING_START_TIME = ("booking_start_time", "開放訂票時間")
    BOOKING_END_TIME = ("booking_end_time", "結束訂票時間")
    ELAPSED_TIME = ("elapsed_time", "耗時(秒)")
    EVENT_TYPE = ("event_type", "活動類型")
    TICKETS = ("tickets", "票券資訊")
    SEAT_STATS = ("seat_stats", "座位統計")
    SEAT_TOTAL = ("seat_total", "總座位數")
    SEAT_AVL = ("seat_avl", "可售座位")
    SEAT_UNAVL = ("seat_unavl", "已售座位")

    @property
    def en(self):
        """Return the internal field name."""
        return self.value[0]

    @property
    def zh(self):
        """Return the Chinese report heading."""
        return self.value[1]
