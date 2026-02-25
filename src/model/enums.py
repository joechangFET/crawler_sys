from enum import Enum

class LogLevel:
    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'
    CRITICAL = 'CRITICAL'

class ResponseCode:
    SUCCESS = 200
    BAD_REQUEST = 400
    REQUEST_TIMEOUT = 408
    INTERNAL_SERVER_ERROR = 500

class ResultCode(Enum):
    Normal = "Normal"
    Computer = "Computer"
    VIP = "VIP Seat"
    DISABLE = "Disable Seat"
    MESSAGEBOX = "MessageBox"
    STANDING = "Standing Seat"
    RECAPCHA = "Recaptcha"
    Complete = "Complete"