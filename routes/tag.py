#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@file tag.py
@description 标签管理API模块
@version 1.0.0
@author Menu Cloud Team
@date 2026-05-19

功能：
1. 获取所有标签列表
2. 创建新标签
3. 删除标签
"""

from flask import jsonify, request
import pymysql
from dbconfig.database import get_db_connection, clear_tag_cache, get_tag_caches
from utils.logger import log_config

logger = log_config()

# ==================== API路由函数 ====================

def get_tags():
    """
    获取所有标签列表
    
    返回：
    - 标签列表
    """
    logger.info('查询标签列表')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM tags ORDER BY name')
    tags = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    logger.info(f"查询标签列表成功 - 标签数量: {len(tags)}")
    return jsonify(tags)

def create_tag():
    """
    创建新标签
    
    请求体：
    - name: 标签名称（必填）
    - category: 分类（可选）
    - color: 颜色（可选，默认#7A77B9）
    
    返回：
    - id: 标签ID
    - message: 创建成功消息
    """
    data = request.json

    if 'name' not in data:
        logger.warning('创建标签失败 - 标签名称为空')
        return jsonify({'error': '标签名称不能为空'}), 400

    logger.info(f"创建标签 - 标签名称: {data.get('name')}, 分类: {data.get('category')}, 颜色: {data.get('color')}")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('''
            INSERT INTO tags (name, category, color)
            VALUES (%s, %s, %s)
        ''', (
            data.get('name'),
            data.get('category', ''),
            data.get('color', '#7A77B9')
        ))

        tag_id = cursor.lastrowid
        clear_tag_cache()
        conn.commit()
        conn.close()

        logger.info(f"创建标签成功 - 标签ID: {tag_id}, 标签名称: {data.get('name')}")
        return jsonify({'id': tag_id, 'message': '标签创建成功'}), 201
    except pymysql.IntegrityError:
        conn.close()
        logger.warning(f"创建标签失败 - 标签名称: {data.get('name')} 已存在")
        return jsonify({'error': '标签已存在'}), 400

def delete_tag(tag_id):
    """
    删除标签
    
    请求参数：
    - tag_id: 标签ID（URL参数）
    
    返回：
    - message: 删除成功消息
    """
    logger.info(f"删除标签 - 标签ID: {tag_id}")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM tags WHERE id = %s', (tag_id,))
    tag = cursor.fetchone()
    
    if tag is None:
        conn.close()
        logger.warning(f"删除标签失败 - 标签ID: {tag_id} 不存在")
        return jsonify({'error': '标签不存在'}), 404

    tag_name = tag.get('name', '未知')
    
    cursor.execute('DELETE FROM tags WHERE id = %s', (tag_id,))
    clear_tag_cache()
    conn.commit()
    conn.close()

    logger.info(f"删除标签成功 - 标签ID: {tag_id}, 标签名称: {tag_name}")
    return jsonify({'message': '标签删除成功'})

def refresh_cache():
    """
    手动刷新缓存
    
    返回：
    - message: 缓存刷新成功消息
    """
    logger.info('手动刷新缓存')
    
    clear_tag_cache()
    get_tag_caches()
    
    logger.info('缓存刷新成功')
    return jsonify({'message': '缓存已刷新'})

# ==================== 注册路由 ====================

def register_tag_routes(app):
    """
    注册标签管理相关路由
    
    参数：
    - app: Flask应用实例
    """
    app.route('/api/tags', methods=['GET'])(get_tags)
    app.route('/api/tags', methods=['POST'])(create_tag)
    app.route('/api/tags/<int:tag_id>', methods=['DELETE'])(delete_tag)
    app.route('/api/cache/refresh', methods=['POST'])(refresh_cache)
