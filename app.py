#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@file app.py
@description 菜单管理系统 - 启动入口
@version 1.0.0
@author Menu Cloud Team
@date 2026-07-29

本文件仅作为应用启动入口，所有业务逻辑在 create_app.py 中实现。
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from create_app import create_app
from utils.logger import log_config

app = create_app()

if __name__ == '__main__':
    logger = log_config()
    logger.info('--------应用启动--------')
    app.run(host='0.0.0.0', port=8080, debug=False)
