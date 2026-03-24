"""
业务异常模块
定义所有业务相关的异常类
"""


class IPQueryException(Exception):
    """
    IP查询业务异常
    
    Attributes:
        code: 错误码
        message: 错误消息
        data: 附加数据
    """
    
    def __init__(self, code: int, message: str, data: dict = None):
        self.code = code
        self.message = message
        self.data = data
    
    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"
