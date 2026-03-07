"""
启动脚本
用于启动IP定位API服务
"""

import subprocess
import sys
import os

def check_dependencies():
    """
    检查并安装依赖
    """
    try:
        import fastapi
        import uvicorn
        import ip2region
        print("✓ 依赖检查通过")
        return True
    except ImportError as e:
        print(f"✗ 缺少依赖: {e}")
        print("正在安装依赖...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        return True

def download_database():
    """
    下载IP数据库
    """
    db_path = os.path.join(os.path.dirname(__file__), "data", "ip2region.xdb")
    if os.path.exists(db_path):
        print(f"✓ 数据库已存在: {db_path}")
        return True
    
    print("正在下载IP数据库...")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    urls = [
        "https://github.com/lionsoul2014/ip2region/raw/master/data/ip2region.xdb",
        "https://gitee.com/lionsoul/ip2region/raw/master/data/ip2region.xdb",
    ]
    
    for url in urls:
        try:
            import urllib.request
            urllib.request.urlretrieve(url, db_path)
            print(f"✓ 数据库下载成功: {db_path}")
            return True
        except Exception as e:
            print(f"✗ 下载失败: {url} - {e}")
            continue
    
    print("✗ 数据库下载失败，请手动下载")
    return False

def main():
    """
    主函数
    """
    print("=" * 50)
    print("IP定位API服务启动器")
    print("=" * 50)
    
    if not check_dependencies():
        sys.exit(1)
    
    if not download_database():
        sys.exit(1)
    
    print("\n启动服务...")
    os.chdir(os.path.dirname(__file__))
    subprocess.run([
        sys.executable, "-m", "uvicorn",
        "ip_location_api.main:app",
        "--host", "0.0.0.0",
        "--port", "8000",
        "--reload"
    ])

if __name__ == "__main__":
    main()
