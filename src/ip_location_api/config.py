"""
配置模块
管理应用程序的所有配置项
"""

import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """
    应用配置类
    
    Attributes:
        HOST: 服务监听地址
        PORT: 服务监听端口
        WORKERS: 工作进程数
        DB_PATH: IP数据库文件路径
    """
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    WORKERS: int = int(os.getenv("WORKERS", "4"))
    
    BASE_DIR: Path = Path(__file__).parent.parent.parent
    DB_PATH: Path = BASE_DIR / "data" / "ip2region.xdb"
    
    def __post_init__(self):
        """
        初始化后处理，确保数据库路径存在
        """
        if not self.DB_PATH.exists():
            alt_path = self.BASE_DIR / "data" / "ip2region_v4.xdb"
            if alt_path.exists():
                self.DB_PATH = alt_path


config = Config()
