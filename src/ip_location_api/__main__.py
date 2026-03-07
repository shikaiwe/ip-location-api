"""
命令行入口
支持直接运行启动服务
"""

import uvicorn
from ip_location_api.config import config


def main():
    """
    启动IP定位API服务
    """
    uvicorn.run(
        "ip_location_api.main:app",
        host=config.HOST,
        port=config.PORT,
        workers=1,
        reload=False,
    )


if __name__ == "__main__":
    main()
