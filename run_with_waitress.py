from waitress import serve
from app import app  # 从你的 app.py 文件中导入 Flask 应用实例
import os
import sys
import yaml
import logging
import logging.handlers
if __name__ == '__main__':
    def load_config():
        """加载外部的 YAML 配置文件"""
        # 获取当前可执行文件的路径或脚本路径
        if getattr(sys, 'frozen', False):
            # 如果是打包后的exe
            base_path = os.path.dirname(sys.executable)
        else:
            # 如果是直接运行的脚本
            base_path = os.path.dirname(os.path.abspath(__file__))

        config_path = os.path.join(base_path, 'config.yaml')
        with open(config_path, 'r') as file:
            return yaml.safe_load(file)

    config = load_config()
    host = config['server']['host']
    port = config['server']['port']

    serve(app, host=host, port=port)