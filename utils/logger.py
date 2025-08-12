"""
Enhanced Logging System for Voice Assistant Application
Captures all logs including WebSocket messages, TTS operations, database operations, and errors
"""
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler
import json

# Create logs directory
LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Log file paths
ERROR_LOG_FILE = LOGS_DIR / "errors.log"
GENERAL_LOG_FILE = LOGS_DIR / "application.log"
WEBSOCKET_LOG_FILE = LOGS_DIR / "websocket.log"
TTS_LOG_FILE = LOGS_DIR / "tts.log"
DATABASE_LOG_FILE = LOGS_DIR / "database.log"
CALL_LOG_FILE = LOGS_DIR / "calls.log"

class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output"""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
        'RESET': '\033[0m'      # Reset
    }
    
    def format(self, record):
        # Add color to levelname
        if record.levelname in self.COLORS:
            record.levelname = f"{self.COLORS[record.levelname]}{record.levelname}{self.COLORS['RESET']}"
        
        return super().format(record)

class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def format(self, record):
        log_obj = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_obj['exception'] = self.formatException(record.exc_info)
            
        # Add extra fields if present
        if hasattr(record, 'call_sid'):
            log_obj['call_sid'] = record.call_sid
        if hasattr(record, 'session_id'):
            log_obj['session_id'] = record.session_id
        if hasattr(record, 'customer_id'):
            log_obj['customer_id'] = record.customer_id
            
        return json.dumps(log_obj)

def setup_logger(name, log_file, level=logging.INFO, max_bytes=10*1024*1024, backup_count=5):
    """Create a logger with file and console handlers"""
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_file, 
        maxBytes=max_bytes, 
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # Formatters
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_formatter = ColoredFormatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%H:%M:%S'
    )
    
    file_handler.setFormatter(file_formatter)
    console_handler.setFormatter(console_formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

def setup_json_logger(name, log_file, level=logging.INFO):
    """Create a JSON logger for structured logging"""
    
    logger = logging.getLogger(f"{name}_json")
    logger.setLevel(level)
    logger.handlers.clear()
    
    file_handler = RotatingFileHandler(
        log_file.with_suffix('.json'),
        maxBytes=10*1024*1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(JSONFormatter())
    
    logger.addHandler(file_handler)
    return logger

# Create specialized loggers
app_logger = setup_logger('voice_assistant', GENERAL_LOG_FILE)
error_logger = setup_logger('voice_assistant.errors', ERROR_LOG_FILE, level=logging.ERROR)
websocket_logger = setup_logger('voice_assistant.websocket', WEBSOCKET_LOG_FILE)
tts_logger = setup_logger('voice_assistant.tts', TTS_LOG_FILE)
database_logger = setup_logger('voice_assistant.database', DATABASE_LOG_FILE)
call_logger = setup_logger('voice_assistant.calls', CALL_LOG_FILE)

# JSON loggers for structured data
websocket_json_logger = setup_json_logger('websocket', WEBSOCKET_LOG_FILE)
call_json_logger = setup_json_logger('calls', CALL_LOG_FILE)

class VoiceAssistantLogger:
    """Main logger class for the voice assistant application"""
    
    def __init__(self):
        self.app = app_logger
        self.error = error_logger
        self.websocket = websocket_logger
        self.tts = tts_logger
        self.database = database_logger
        self.call = call_logger
        self.websocket_json = websocket_json_logger
        self.call_json = call_json_logger
    
    def log_websocket_message(self, message_type, data, call_sid=None, session_id=None):
        """Log WebSocket messages with structured data"""
        log_msg = f"[{message_type}] WebSocket message"
        
        # Console/file log
        self.websocket.info(log_msg, extra={
            'call_sid': call_sid,
            'session_id': session_id
        })
        
        # JSON log with full data
        self.websocket_json.info(log_msg, extra={
            'message_type': message_type,
            'data': data,
            'call_sid': call_sid,
            'session_id': session_id
        })
    
    def log_tts_operation(self, operation, text, language, status, error=None, call_sid=None):
        """Log TTS operations"""
        log_msg = f"[TTS] {operation}: {status}"
        
        if status == "success":
            self.tts.info(log_msg, extra={'call_sid': call_sid})
        else:
            self.tts.error(f"{log_msg} - {error}", extra={'call_sid': call_sid})
            self.error.error(f"TTS Error in {operation}: {error}", extra={'call_sid': call_sid})
    
    def log_database_operation(self, operation, table, status, details=None, error=None):
        """Log database operations"""
        log_msg = f"[DB] {operation} on {table}: {status}"
        
        if status == "success":
            self.database.info(log_msg)
        else:
            self.database.error(f"{log_msg} - {error}")
            self.error.error(f"Database Error in {operation}: {error}")
    
    def log_call_event(self, event, call_sid, customer_id=None, details=None):
        """Log call-related events"""
        log_msg = f"[CALL] {event} - CallSid: {call_sid}"
        
        self.call.info(log_msg, extra={
            'call_sid': call_sid,
            'customer_id': customer_id
        })
        
        # JSON log with full details
        self.call_json.info(log_msg, extra={
            'event': event,
            'call_sid': call_sid,
            'customer_id': customer_id,
            'details': details
        })
    
    def log_error(self, error_type, message, exception=None, call_sid=None, context=None):
        """Log errors with context"""
        log_msg = f"[ERROR] {error_type}: {message}"
        
        if exception:
            self.error.error(log_msg, exc_info=exception, extra={
                'call_sid': call_sid,
                'context': context
            })
        else:
            self.error.error(log_msg, extra={
                'call_sid': call_sid,
                'context': context
            })

# Global logger instance
logger = VoiceAssistantLogger()

def log_function_entry(func):
    """Decorator to log function entry and exit"""
    def wrapper(*args, **kwargs):
        logger.app.debug(f"Entering {func.__name__}")
        try:
            result = func(*args, **kwargs)
            logger.app.debug(f"Exiting {func.__name__}")
            return result
        except Exception as e:
            logger.error.error(f"Error in {func.__name__}: {str(e)}", exc_info=True)
            raise
    return wrapper

def setup_application_logging():
    """Setup logging for the entire application"""
    
    # Disable uvicorn's default logging to avoid duplication
    logging.getLogger("uvicorn.access").disabled = True
    
    # Create logs directory info file
    info_file = LOGS_DIR / "README.md"
    info_file.write_text(f"""# Voice Assistant Logs

## Log Files

- **application.log**: General application logs
- **errors.log**: Error logs only
- **websocket.log**: WebSocket communication logs
- **tts.log**: Text-to-speech operation logs
- **database.log**: Database operation logs
- **calls.log**: Call management and events logs

## JSON Logs

- **websocket.json**: Structured WebSocket message data
- **calls.json**: Structured call event data

## Log Rotation

All log files are rotated when they reach 10MB, keeping 5 backup files.

Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
""")
    
    logger.app.info("🎉 Logging system initialized")
    logger.app.info(f"📁 Logs directory: {LOGS_DIR.absolute()}")
    
    return logger

if __name__ == "__main__":
    # Test the logging system
    setup_application_logging()
    
    logger.app.info("Testing application logger")
    logger.error.error("Testing error logger")
    logger.websocket.info("Testing websocket logger")
    logger.tts.info("Testing TTS logger")
    logger.database.info("Testing database logger")
    logger.call.info("Testing call logger")
    
    print(f"\n✅ Logs created in: {LOGS_DIR.absolute()}")
