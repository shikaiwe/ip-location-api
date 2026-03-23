"""
日志核心模块
提供完善的日志记录机制，支持分级日志、结构化格式、日志轮转、敏感信息脱敏等功能
"""

import logging
import logging.handlers
import json
import os
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from functools import lru_cache
from contextvars import ContextVar
from dataclasses import dataclass, field


request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)


@dataclass
class LogConfig:
    """
    日志配置类
    
    Attributes:
        LOG_LEVEL: 日志级别
        LOG_DIR: 日志存储目录
        LOG_FILE_NAME: 日志文件名
        LOG_BACKUP_COUNT: 保留的日志文件数量（天数），默认365天（一年）
        LOG_FORMAT: 日志格式类型 (json/text)
        LOG_TO_CONSOLE: 是否输出到控制台
        LOG_TO_FILE: 是否输出到文件
        LOG_SENSITIVE_FIELDS: 敏感字段列表
    """
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR: str = os.getenv("LOG_DIR", "logs")
    LOG_FILE_NAME: str = os.getenv("LOG_FILE_NAME", "app.log")
    LOG_BACKUP_COUNT: int = int(os.getenv("LOG_BACKUP_COUNT", "365"))
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "json")
    LOG_TO_CONSOLE: bool = os.getenv("LOG_TO_CONSOLE", "true").lower() == "true"
    LOG_TO_FILE: bool = os.getenv("LOG_TO_FILE", "true").lower() == "true"
    LOG_SENSITIVE_FIELDS: list = field(default_factory=lambda: [
        "password", "passwd", "pwd", "secret", "token", "api_key", "apikey",
        "authorization", "auth", "credential", "private_key", "privatekey",
        "access_token", "refresh_token", "session_id", "sessionid",
        "credit_card", "creditcard", "ssn", "social_security"
    ])


log_config = LogConfig()


class SensitiveDataFilter:
    """
    敏感信息脱敏过滤器
    
    自动检测并脱敏日志中的敏感信息
    """
    
    SENSITIVE_PATTERNS = [
        (re.compile(r'(password["\s:=]+)["\']?([^"\s,}\]]+)["\']?', re.I), r'\1******'),
        (re.compile(r'(token["\s:=]+)["\']?([^"\s,}\]]+)["\']?', re.I), r'\1******'),
        (re.compile(r'(api_key["\s:=]+)["\']?([^"\s,}\]]+)["\']?', re.I), r'\1******'),
        (re.compile(r'(secret["\s:=]+)["\']?([^"\s,}\]]+)["\']?', re.I), r'\1******'),
        (re.compile(r'(authorization["\s:=]+)["\']?([^"\s,}\]]+)["\']?', re.I), r'\1******'),
    ]
    
    EMAIL_PATTERN = re.compile(r'([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})')
    PHONE_PATTERN = re.compile(r'(?:\+?86)?1[3-9]\d{9}')
    ID_CARD_PATTERN = re.compile(r'\d{17}[\dXx]')
    BANK_CARD_PATTERN = re.compile(r'\d{16,19}')
    IP_PATTERN = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
    
    @classmethod
    def mask_email(cls, email: str) -> str:
        """
        邮箱脱敏
        
        Args:
            email: 邮箱地址
            
        Returns:
            str: 脱敏后的邮箱
        """
        if '@' not in email:
            return email
        parts = email.split('@')
        if len(parts[0]) <= 2:
            return f"**@{parts[1]}"
        return f"{parts[0][:2]}***@{parts[1]}"
    
    @classmethod
    def mask_phone(cls, phone: str) -> str:
        """
        手机号脱敏
        
        Args:
            phone: 手机号
            
        Returns:
            str: 脱敏后的手机号
        """
        if len(phone) == 11:
            return f"{phone[:3]}****{phone[7:]}"
        return f"{phone[:3]}****{phone[-4:]}"
    
    @classmethod
    def mask_id_card(cls, id_card: str) -> str:
        """
        身份证号脱敏
        
        Args:
            id_card: 身份证号
            
        Returns:
            str: 脱敏后的身份证号
        """
        return f"{id_card[:6]}********{id_card[-4:]}"
    
    @classmethod
    def mask_bank_card(cls, card: str) -> str:
        """
        银行卡号脱敏
        
        Args:
            card: 银行卡号
            
        Returns:
            str: 脱敏后的银行卡号
        """
        return f"{card[:4]}****{card[-4:]}"
    
    @classmethod
    def mask_ip(cls, ip: str) -> str:
        """
        IP地址脱敏（可选，根据需求）
        
        Args:
            ip: IP地址
            
        Returns:
            str: 脱敏后的IP地址
        """
        parts = ip.split('.')
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.***.***"
        return ip
    
    @classmethod
    def filter_dict(cls, data: dict, sensitive_fields: list = None) -> dict:
        """
        过滤字典中的敏感信息
        
        Args:
            data: 原始数据字典
            sensitive_fields: 敏感字段列表
            
        Returns:
            dict: 脱敏后的字典
        """
        if not isinstance(data, dict):
            return data
        
        sensitive_fields = sensitive_fields or log_config.LOG_SENSITIVE_FIELDS
        result = {}
        
        for key, value in data.items():
            lower_key = key.lower()
            
            if any(field in lower_key for field in sensitive_fields):
                result[key] = "******"
            elif isinstance(value, dict):
                result[key] = cls.filter_dict(value, sensitive_fields)
            elif isinstance(value, list):
                result[key] = [
                    cls.filter_dict(item, sensitive_fields) if isinstance(item, dict) else item
                    for item in value
                ]
            elif isinstance(value, str):
                result[key] = cls.filter_string(value)
            else:
                result[key] = value
        
        return result
    
    @classmethod
    def filter_string(cls, text: str) -> str:
        """
        过滤字符串中的敏感信息
        
        Args:
            text: 原始字符串
            
        Returns:
            str: 脱敏后的字符串
        """
        if not isinstance(text, str):
            return text
        
        result = text
        
        for pattern, replacement in cls.SENSITIVE_PATTERNS:
            result = pattern.sub(replacement, result)
        
        return result


class StructuredFormatter(logging.Formatter):
    """
    结构化日志格式化器
    
    输出简洁的JSON格式日志
    """
    
    def __init__(self, fmt: str = None, datefmt: str = None, style: str = '%'):
        super().__init__(fmt, datefmt, style)
        self.sensitive_filter = SensitiveDataFilter()
    
    def format(self, record: logging.LogRecord) -> str:
        """
        格式化日志记录
        
        Args:
            record: 日志记录对象
            
        Returns:
            str: 格式化后的日志字符串
        """
        log_data = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": record.levelname,
            "logger": record.name.split(".")[-1] if "." in record.name else record.name,
            "msg": record.getMessage(),
        }
        
        request_id = request_id_var.get()
        if request_id:
            log_data["req"] = request_id[:8]
        
        if hasattr(record, 'extra_data') and record.extra_data:
            filtered_extra = self.sensitive_filter.filter_dict(record.extra_data)
            log_data.update(filtered_extra)
        
        if record.exc_info:
            log_data["error"] = str(record.exc_info[1]) if record.exc_info[1] else "Unknown error"
            log_data["trace"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """
    文本格式日志格式化器
    
    输出易读的文本格式日志
    """
    
    def __init__(self, fmt: str = None, datefmt: str = None):
        default_fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(module)s:%(funcName)s:%(lineno)d | %(message)s"
        super().__init__(fmt or default_fmt, datefmt or "%Y-%m-%d %H:%M:%S")
    
    def format(self, record: logging.LogRecord) -> str:
        request_id = request_id_var.get()
        if request_id:
            record.message = f"[{request_id}] {record.getMessage()}"
        else:
            record.message = record.getMessage()
        
        return super().format(record)


class LogLevel:
    """
    日志级别常量
    """
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    FATAL = logging.FATAL
    
    LEVEL_NAMES = {
        "DEBUG": DEBUG,
        "INFO": INFO,
        "WARN": WARNING,
        "WARNING": WARNING,
        "ERROR": ERROR,
        "FATAL": FATAL,
        "CRITICAL": FATAL
    }


class IPLogger(logging.Logger):
    """
    自定义日志器类
    
    扩展标准Logger，添加便捷方法和结构化日志支持
    """
    
    def _log_with_extra(
        self, 
        level: int, 
        msg: str, 
        args: tuple, 
        exc_info: bool = False,
        extra: dict = None,
        **kwargs
    ):
        """
        带额外数据的日志记录
        
        Args:
            level: 日志级别
            msg: 日志消息
            args: 消息参数
            exc_info: 是否包含异常信息
            extra: 额外数据
            **kwargs: 其他关键字参数
        """
        extra_data = extra or {}
        extra_data.update(kwargs)
        
        super()._log(level, msg, args, exc_info=exc_info, extra={"extra_data": extra_data})
    
    def debug_with_extra(self, msg: str, extra: dict = None, **kwargs):
        """
        记录DEBUG级别日志，支持额外数据
        
        Args:
            msg: 日志消息
            extra: 额外数据字典
            **kwargs: 其他关键字参数
        """
        self._log_with_extra(logging.DEBUG, msg, (), extra=extra, **kwargs)
    
    def info_with_extra(self, msg: str, extra: dict = None, **kwargs):
        """
        记录INFO级别日志，支持额外数据
        
        Args:
            msg: 日志消息
            extra: 额外数据字典
            **kwargs: 其他关键字参数
        """
        self._log_with_extra(logging.INFO, msg, (), extra=extra, **kwargs)
    
    def warning_with_extra(self, msg: str, extra: dict = None, **kwargs):
        """
        记录WARNING级别日志，支持额外数据
        
        Args:
            msg: 日志消息
            extra: 额外数据字典
            **kwargs: 其他关键字参数
        """
        self._log_with_extra(logging.WARNING, msg, (), extra=extra, **kwargs)
    
    def error_with_extra(self, msg: str, extra: dict = None, exc_info: bool = False, **kwargs):
        """
        记录ERROR级别日志，支持额外数据和异常堆栈
        
        Args:
            msg: 日志消息
            extra: 额外数据字典
            exc_info: 是否包含异常堆栈
            **kwargs: 其他关键字参数
        """
        self._log_with_extra(logging.ERROR, msg, (), exc_info=exc_info, extra=extra, **kwargs)
    
    def fatal_with_extra(self, msg: str, extra: dict = None, exc_info: bool = False, **kwargs):
        """
        记录FATAL级别日志，支持额外数据和异常堆栈
        
        Args:
            msg: 日志消息
            extra: 额外数据字典
            exc_info: 是否包含异常堆栈
            **kwargs: 其他关键字参数
        """
        self._log_with_extra(logging.FATAL, msg, (), exc_info=exc_info, extra=extra, **kwargs)
    
    def exception_with_extra(self, msg: str, extra: dict = None, **kwargs):
        """
        记录异常日志，自动包含异常堆栈
        
        Args:
            msg: 日志消息
            extra: 额外数据字典
            **kwargs: 其他关键字参数
        """
        self._log_with_extra(logging.ERROR, msg, (), exc_info=True, extra=extra, **kwargs)


class LoggerManager:
    """
    日志管理器
    
    统一管理所有日志器的创建和配置，支持按日期分隔和归档
    """
    
    _initialized = False
    _loggers = {}
    
    @classmethod
    def setup(cls, config: LogConfig = None):
        """
        初始化日志系统
        
        Args:
            config: 日志配置对象
        """
        if cls._initialized:
            return
        
        config = config or log_config
        
        logging.setLoggerClass(IPLogger)
        
        root_logger = logging.getLogger()
        root_logger.setLevel(LogLevel.LEVEL_NAMES.get(config.LOG_LEVEL.upper(), LogLevel.INFO))
        
        root_logger.handlers.clear()
        
        if config.LOG_TO_CONSOLE:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(LogLevel.LEVEL_NAMES.get(config.LOG_LEVEL.upper(), LogLevel.INFO))
            
            if config.LOG_FORMAT.lower() == "json":
                console_handler.setFormatter(StructuredFormatter())
            else:
                console_handler.setFormatter(TextFormatter())
            
            root_logger.addHandler(console_handler)
        
        if config.LOG_TO_FILE:
            log_dir = Path(config.LOG_DIR)
            log_dir.mkdir(parents=True, exist_ok=True)
            
            log_file = log_dir / config.LOG_FILE_NAME
            
            file_handler = logging.handlers.TimedRotatingFileHandler(
                filename=str(log_file),
                when="midnight",
                interval=1,
                backupCount=config.LOG_BACKUP_COUNT,
                encoding="utf-8"
            )
            file_handler.suffix = "%Y-%m-%d"
            file_handler.namer = cls._namer
            file_handler.rotator = cls._rotator
            file_handler.setLevel(LogLevel.LEVEL_NAMES.get(config.LOG_LEVEL.upper(), LogLevel.INFO))
            file_handler.setFormatter(StructuredFormatter())
            
            root_logger.addHandler(file_handler)
            
            error_log_file = log_dir / "error.log"
            error_handler = logging.handlers.TimedRotatingFileHandler(
                filename=str(error_log_file),
                when="midnight",
                interval=1,
                backupCount=config.LOG_BACKUP_COUNT,
                encoding="utf-8"
            )
            error_handler.suffix = "%Y-%m-%d"
            error_handler.namer = cls._namer
            error_handler.rotator = cls._rotator
            error_handler.setLevel(LogLevel.ERROR)
            error_handler.setFormatter(StructuredFormatter())
            
            root_logger.addHandler(error_handler)
        
        cls._initialized = True
    
    @staticmethod
    def _namer(default_name):
        """
        日志文件命名器
        
        将日志归档到 年份/月份/日期 目录结构
        
        Args:
            default_name: 默认文件名（如 logs/app.log.2026-03-24）
            
        Returns:
            str: 新的文件名（如 logs/2026/03/24/app.log）
        """
        dir_name, base_name = os.path.split(default_name)
        name, ext = os.path.splitext(base_name)
        
        date_match = None
        for part in name.split("."):
            if len(part) == 10 and "-" in part:
                try:
                    year, month, day = part.split("-")
                    if len(year) == 4 and len(month) == 2 and len(day) == 2:
                        date_match = (year, month, day)
                        name = name.replace(part, "").rstrip(".")
                        break
                except ValueError:
                    continue
        
        if date_match:
            year, month, day = date_match
            return os.path.join(dir_name, year, month, day, f"{name}{ext}")
        
        return os.path.join(dir_name, "archive", f"{name}{ext}")
    
    @staticmethod
    def _rotator(source, dest):
        """
        日志文件轮转器
        
        Args:
            source: 源文件路径
            dest: 目标文件路径
        """
        dest_dir = os.path.dirname(dest)
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
        
        if os.path.exists(source):
            if os.path.exists(dest):
                os.remove(dest)
            os.rename(source, dest)
    
    @classmethod
    def get_logger(cls, name: str) -> IPLogger:
        """
        获取指定名称的日志器
        
        Args:
            name: 日志器名称
            
        Returns:
            IPLogger: 日志器实例
        """
        if not cls._initialized:
            cls.setup()
        
        if name not in cls._loggers:
            cls._loggers[name] = logging.getLogger(name)
        
        return cls._loggers[name]


def get_logger(name: str = None) -> IPLogger:
    """
    获取日志器的便捷函数
    
    Args:
        name: 日志器名称，默认为调用模块名
        
    Returns:
        IPLogger: 日志器实例
    """
    if name is None:
        import inspect
        frame = inspect.currentframe()
        if frame and frame.f_back:
            name = frame.f_back.f_globals.get("__name__", "root")
        else:
            name = "root"
    
    return LoggerManager.get_logger(name)


def set_request_id(request_id: str):
    """
    设置当前请求ID
    
    Args:
        request_id: 请求ID
    """
    request_id_var.set(request_id)


def set_user_id(user_id: str):
    """
    设置当前用户ID
    
    Args:
        user_id: 用户ID
    """
    user_id_var.set(user_id)


def get_request_id() -> Optional[str]:
    """
    获取当前请求ID
    
    Returns:
        Optional[str]: 请求ID
    """
    return request_id_var.get()


def get_user_id() -> Optional[str]:
    """
    获取当前用户ID
    
    Returns:
        Optional[str]: 用户ID
    """
    return user_id_var.get()


def clear_context():
    """
    清除上下文变量
    """
    request_id_var.set(None)
    user_id_var.set(None)


class LogContext:
    """
    日志上下文管理器
    
    用于临时设置请求ID和用户ID
    """
    
    def __init__(self, request_id: str = None, user_id: str = None):
        """
        初始化上下文管理器
        
        Args:
            request_id: 请求ID
            user_id: 用户ID
        """
        self.request_id = request_id
        self.user_id = user_id
        self._old_request_id = None
        self._old_user_id = None
    
    def __enter__(self):
        """
        进入上下文
        """
        self._old_request_id = get_request_id()
        self._old_user_id = get_user_id()
        
        if self.request_id:
            set_request_id(self.request_id)
        if self.user_id:
            set_user_id(self.user_id)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        退出上下文
        """
        if self._old_request_id:
            set_request_id(self._old_request_id)
        else:
            request_id_var.set(None)
        
        if self._old_user_id:
            set_user_id(self._old_user_id)
        else:
            user_id_var.set(None)
        
        return False
