"""
高性能响应模块
使用 orjson 替代标准 JSON 序列化，提升 API 响应性能
"""

import orjson
from fastapi.responses import JSONResponse
from typing import Any, Dict


def orjson_default(obj: Any) -> Any:
    """
    orjson 默认序列化处理函数
    
    Args:
        obj: 待序列化的对象
        
    Returns:
        Any: 序列化后的对象
    """
    if hasattr(obj, 'model_dump'):
        return obj.model_dump()
    if hasattr(obj, 'to_dict'):
        return obj.to_dict()
    if hasattr(obj, '__dict__'):
        return obj.__dict__
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


class ORJSONResponse(JSONResponse):
    """
    基于 orjson 的高性能 JSON 响应类
    
    相比标准 json.dumps:
    - 序列化速度提升 3-10x
    - 内存占用更低
    - 支持更多数据类型
    """
    
    def render(self, content: Any) -> bytes:
        """
        渲染响应内容为 JSON 字节串
        
        Args:
            content: 响应内容
            
        Returns:
            bytes: JSON 格式的字节串
        """
        return orjson.dumps(
            content,
            default=orjson_default,
            option=orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY
        )
