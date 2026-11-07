#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@file database.py
@description 数据库配置和缓存管理模块
@version 1.0.0
@author Menu Cloud Team
@date 2026-05-19

功能：
1. 数据库连接配置
2. 标签缓存管理
3. 菜品标签映射
"""

import pymysql
import os
import time
from dotenv import load_dotenv
from utils.logger import log_config

load_dotenv()

logger = log_config()

# ==================== 数据库配置 ====================

DB_CONFIG = {
    'host': os.getenv('DB_HOST', '127.0.0.1'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': os.getenv('DB_USER', 'menu'),
    'password': os.getenv('DB_PASSWORD', 'menu.123'),
    'db': os.getenv('DB_NAME', 'menu'),
    'charset': os.getenv('DB_CHARSET', 'utf8mb4'),
    'cursorclass': pymysql.cursors.DictCursor,
    'use_unicode': True,
    # 会话时区固定为东八区，保证 NOW() / CURRENT_TIMESTAMP 生成北京时间
    'init_command': "SET NAMES utf8mb4, time_zone = '+8:00'"
}

def get_db_connection():
    """
    获取数据库连接
    返回一个MySQL连接对象
    """
    conn = pymysql.connect(**DB_CONFIG)
    # 显式设置会话时区为东八区（双保险，不依赖 init_command 是否生效）
    with conn.cursor() as cursor:
        cursor.execute("SET time_zone = '+8:00'")
    return conn

# ==================== 缓存变量 ====================

_tag_cache = None
_dish_tags_cache = None
_cache_timestamp = 0

CACHE_EXPIRE_SECONDS = 30

# ==================== 缓存管理函数 ====================

def get_all_tags_cache():
    """
    获取所有标签的缓存数据
    返回字典格式：{标签名: {background_color, text_color}}
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT name, background_color, text_color FROM tags')
    tags = cursor.fetchall()
    conn.close()
    return {tag['name']: {'background_color': tag['background_color'], 'text_color': tag['text_color']} for tag in tags}

def get_dish_tags_mapping():
    """
    获取菜品与标签的映射关系
    返回字典格式：{菜品ID: [{name, background_color, text_color}, ...]}
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES LIKE 'taglink'")
    if not cursor.fetchone():
        conn.close()
        return {}
    try:
        cursor.execute("DESCRIBE taglink")
        fields = [f['Field'] for f in cursor.fetchall()]
        dish_field = next((fn for fn in fields if 'dish' in fn.lower()), None)
        tag_field = next((fn for fn in fields if 'tag' in fn.lower()), None)
        if not dish_field or not tag_field:
            conn.close()
            return {}
        cursor.execute(f'SELECT tl.{dish_field} as dish_id, t.name, t.background_color, t.text_color FROM taglink tl JOIN tags t ON tl.{tag_field} = t.id')
        results = cursor.fetchall()
        conn.close()
        mapping = {}
        for r in results:
            if r['dish_id'] not in mapping:
                mapping[r['dish_id']] = []
            mapping[r['dish_id']].append({'name': r['name'], 'background_color': r['background_color'], 'text_color': r['text_color']})
        return mapping
    except Exception as e:
        logger.error(f"获取菜品标签映射失败: {e}")
        conn.close()
        return {}

def get_tag_caches():
    """
    获取标签缓存（带自动刷新机制）
    如果缓存不存在或已过期，则重新从数据库加载
    返回元组：(标签缓存, 菜品标签映射)
    """
    global _tag_cache, _dish_tags_cache, _cache_timestamp
    current_time = time.time()
    if _tag_cache is None or (current_time - _cache_timestamp) > CACHE_EXPIRE_SECONDS:
        _tag_cache = get_all_tags_cache()
        _dish_tags_cache = get_dish_tags_mapping()
        _cache_timestamp = current_time
        Time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(current_time))
        logger.info(f"缓存刷新: {Time}")
    return _tag_cache, _dish_tags_cache

def clear_tag_cache():
    """
    清除标签缓存
    """
    global _tag_cache, _dish_tags_cache
    _tag_cache = None
    _dish_tags_cache = None

def clear_dish_tags_cache():
    """
    清除菜品标签映射缓存
    """
    global _tag_cache, _dish_tags_cache
    _tag_cache = None
    _dish_tags_cache = None
