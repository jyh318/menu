#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@file routes_dish.py
@description 菜品管理API模块
@version 1.0.0
@author Menu Cloud Team
@date 2026-05-19

功能：
1. 获取菜品列表（支持分页和筛选）
2. 获取单个菜品详情
3. 新增菜品
4. 修改菜品信息
5. 删除菜品
"""

from flask import jsonify, request
import pymysql
from dataconf import get_db_connection, get_tag_caches, clear_dish_tags_cache, clear_tag_cache
from logconfig import log_config

logger = log_config()

# ==================== 辅助函数 ====================

def process_dish_tags(dish, tag_cache, dish_tags_map):
    """
    处理菜品的标签信息
    
    参数：
    - dish: 菜品字典
    - tag_cache: 标签缓存
    - dish_tags_map: 菜品标签映射
    
    返回：
    - 处理后的菜品字典
    """
    dish_id = dish['id']
    tags = []
    
    if 'detail_description' in dish and dish['detail_description']:
        dish['detail_desc'] = dish['detail_description']
    if 'method_desc' in dish and dish['method_desc']:
        dish['method'] = dish['method_desc']
    if 'ingredients_desc' in dish and dish['ingredients_desc']:
        dish['ingredients'] = dish['ingredients_desc']

    if dish_id in dish_tags_map:
        tags = dish_tags_map[dish_id]
    else:
        dish_tags_str = dish.get('tags', '')
        if dish_tags_str:
            for tag_name in dish_tags_str.split(','):
                tag_name = tag_name.strip()
                if tag_name and tag_name in tag_cache:
                    tags.append({
                        'name': tag_name,
                        'background_color': tag_cache[tag_name]['background_color'],
                        'text_color': tag_cache[tag_name]['text_color']
                    })

    dish['tags'] = ','.join([tag['name'] for tag in tags])
    dish['tag_details'] = tags
    
    return dish

# ==================== API路由函数 ====================

def get_dishes():
    """
    获取菜品列表（支持分页和筛选）
    
    请求参数：
    - tag: 标签筛选（可选）
    - search: 搜索关键词（匹配名称、描述、价格）
    - page: 页码（默认0）
    - page_size: 每页数量（默认12）
    
    返回：
    - dishes: 菜品列表
    - total: 总数
    - page: 当前页码
    - page_size: 每页数量
    - has_more: 是否还有更多
    """
    tag_filter = request.args.get('tag')
    search = request.args.get('search')
    page = request.args.get('page', 0, type=int)
    page_size = request.args.get('page_size', 12, type=int)

    logger.info(f"查询菜品列表 - 标签筛选: {tag_filter}, 搜索关键词: {search}, 页码: {page}, 每页数量: {page_size}")

    conn = get_db_connection()
    cursor = conn.cursor()

    # 构建基础查询条件
    query = 'SELECT * FROM dishes WHERE 1=1'
    params = []

    if search:
        query += ' AND (name LIKE %s OR description LIKE %s OR CAST(price AS CHAR) LIKE %s)'
        params.append(f'%{search}%')
        params.append(f'%{search}%')
        params.append(f'%{search}%')

    # 先查询总数
    count_query = query.replace('SELECT *', 'SELECT COUNT(*) as total', 1)
    cursor.execute(count_query, params)
    total_result = cursor.fetchone()
    total = total_result['total'] if total_result else 0
    
    # 如果有标签筛选，需要在内存中筛选
    if tag_filter:
        # 查询所有数据用于标签筛选
        cursor.execute(query, params)
        all_dishes = [dict(row) for row in cursor.fetchall()]
        
        tag_cache, dish_tags_map = get_tag_caches()
        for dish in all_dishes:
            process_dish_tags(dish, tag_cache, dish_tags_map)
        
        all_dishes = [dish for dish in all_dishes if tag_filter in dish['tags']]
        total = len(all_dishes)
        start = page * page_size
        end = start + page_size
        dishes = all_dishes[start:end]
    else:
        # 没有标签筛选时使用SQL分页
        start = page * page_size
        query += ' LIMIT %s OFFSET %s'
        params.append(page_size)
        params.append(start)
        
        cursor.execute(query, params)
        all_dishes = [dict(row) for row in cursor.fetchall()]
        
        tag_cache, dish_tags_map = get_tag_caches()
        for dish in all_dishes:
            process_dish_tags(dish, tag_cache, dish_tags_map)
        
        dishes = all_dishes
        start = page * page_size
        end = start + len(dishes)

    conn.close()

    has_more = end < total

    logger.info(f"查询菜品列表成功 - 总数: {total}, 返回数量: {len(dishes)}, 是否有更多: {has_more}")

    return jsonify({
        'dishes': dishes,
        'total': total,
        'page': page,
        'page_size': page_size,
        'has_more': has_more
    })

def get_dish(dish_id):
    """
    获取单个菜品详情
    
    请求参数：
    - dish_id: 菜品ID（URL参数）
    
    返回：
    - 菜品详细信息
    """
    logger.info(f"查询单个菜品 - 菜品ID: {dish_id}")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM dishes WHERE id = %s', (dish_id,))
    dish = cursor.fetchone()
    conn.close()

    if dish is None:
        logger.warning(f"查询菜品失败 - 菜品ID: {dish_id} 不存在")
        return jsonify({'error': '菜品不存在'}), 404

    dish = dict(dish)
    tag_cache, dish_tags_map = get_tag_caches()
    process_dish_tags(dish, tag_cache, dish_tags_map)

    logger.info(f"查询菜品成功 - 菜品ID: {dish_id}, 菜品名称: {dish.get('name')}")

    return jsonify(dish)

def create_dish():
    """
    新增菜品
    
    请求体：
    - name: 菜品名称（必填）
    - price: 价格（必填）
    - image: 图片URL（可选）
    - description: 简介（可选）
    - detail_desc: 详细描述（可选）
    - method: 制作方法（可选）
    - ingredients: 用料（可选）
    - tags: 标签（逗号分隔，可选）
    
    返回：
    - id: 新菜品ID
    - message: 成功消息
    """
    data = request.json
    
    logger.info(f"新增菜品 - 菜品名称: {data.get('name')}, 价格: {data.get('price')}")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('DESCRIBE dishes')
        dish_fields = [f['Field'] for f in cursor.fetchall()]
        
        # 处理 price 字段，确保是数字
        price_val = data.get('price')
        try:
            price_val = float(price_val) if price_val is not None else 0
        except (ValueError, TypeError):
            price_val = 0
        
        insert_fields = ['name', 'price']
        insert_values = [data.get('name'), price_val]
        
        if 'image' in dish_fields:
            insert_fields.append('image')
            insert_values.append(data.get('image', ''))
        if 'description' in dish_fields:
            insert_fields.append('description')
            insert_values.append(data.get('description', ''))
        if 'detail_description' in dish_fields:
            insert_fields.append('detail_description')
            insert_values.append(data.get('detail_desc', ''))
        if 'method' in dish_fields:
            insert_fields.append('method')
            insert_values.append(data.get('method', ''))
        if 'ingredients' in dish_fields:
            insert_fields.append('ingredients')
            insert_values.append(data.get('ingredients', ''))
        
        placeholders = ', '.join(['%s'] * len(insert_values))
        fields_str = ', '.join(insert_fields)
        
        cursor.execute(f'''
            INSERT INTO dishes ({fields_str})
            VALUES ({placeholders})
        ''', tuple(insert_values))

        dish_id = cursor.lastrowid
        
        new_tags_str = data.get('tags', '') or ''
        new_tags_set = set(t.strip() for t in new_tags_str.split(',') if t.strip())
        
        if new_tags_set:
            try:
                cursor.execute("SHOW TABLES LIKE 'taglink'")
                if cursor.fetchone():
                    cursor.execute("DESCRIBE taglink")
                    fields = [f['Field'] for f in cursor.fetchall()]
                    dish_field = next((fn for fn in fields if 'dish' in fn.lower()), None)
                    tag_field = next((fn for fn in fields if 'tag' in fn.lower()), None)
                    
                    if dish_field and tag_field:
                        cursor.execute('SELECT id, name FROM tags')
                        all_tags_in_db = cursor.fetchall()
                        tag_id_map = {tag['name']: tag['id'] for tag in all_tags_in_db}
                        
                        for tag_name in new_tags_set:
                            if tag_name in tag_id_map:
                                tag_id = tag_id_map[tag_name]
                                cursor.execute(f'INSERT INTO taglink ({dish_field}, {tag_field}) VALUES (%s, %s)', (dish_id, tag_id))
            except Exception as e:
                logger.error(f"新增菜品时关联标签失败: {e}")

        clear_dish_tags_cache()
        conn.commit()
        conn.close()

        logger.info(f"新增菜品成功 - 菜品ID: {dish_id}, 菜品名称: {data.get('name')}")
        return jsonify({'id': dish_id, 'message': '新增成功'}), 201
    except Exception as e:
        logger.error(f"新增菜品失败 - 菜品名称: {data.get('name')}, 错误: {e}, 完整数据: {data}")
        conn.close()
        import traceback
        return jsonify({'error': f'新增失败: {str(e)}'}), 500

def update_dish(dish_id):
    """
    修改菜品信息
    
    请求参数：
    - dish_id: 菜品ID（URL参数）
    
    请求体：
    - name: 菜品名称（可选）
    - price: 价格（可选）
    - image: 图片URL（可选）
    - description: 简介（可选）
    - detail_desc: 详细描述（可选）
    - method: 制作方法（可选）
    - ingredients: 用料（可选）
    - tags: 标签（逗号分隔，可选）
    
    返回：
    - message: 更新成功消息
    """
    data = request.json

    logger.info(f"修改菜品 - 菜品ID: {dish_id}, 数据: {data}")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM dishes WHERE id = %s', (dish_id,))
    if cursor.fetchone() is None:
        conn.close()
        logger.warning(f"修改菜品失败 - 菜品ID: {dish_id} 不存在")
        return jsonify({'error': '菜品不存在'}), 404

    cursor.execute('DESCRIBE dishes')
    dish_fields = [f['Field'] for f in cursor.fetchall()]
    
    update_fields = []
    update_values = []
    
    if 'name' in dish_fields:
        update_fields.append('name = %s')
        update_values.append(data.get('name'))
    if 'price' in dish_fields:
        update_fields.append('price = %s')
        price_val = data.get('price')
        # 尝试将 price 转换为数字
        try:
            price_val = float(price_val) if price_val is not None else 0
        except (ValueError, TypeError):
            price_val = 0
        update_values.append(price_val)
    if 'image' in dish_fields:
        update_fields.append('image = %s')
        update_values.append(data.get('image', ''))
    if 'description' in dish_fields:
        update_fields.append('description = %s')
        update_values.append(data.get('description', ''))
    if 'detail_description' in dish_fields:
        update_fields.append('detail_description = %s')
        update_values.append(data.get('detail_desc', ''))
    if 'method' in dish_fields:
        update_fields.append('method = %s')
        update_values.append(data.get('method', ''))
    elif 'method_desc' in dish_fields:
        update_fields.append('method_desc = %s')
        update_values.append(data.get('method', ''))
    if 'ingredients' in dish_fields:
        update_fields.append('ingredients = %s')
        update_values.append(data.get('ingredients', ''))
    elif 'ingredients_desc' in dish_fields:
        update_fields.append('ingredients_desc = %s')
        update_values.append(data.get('ingredients', ''))

    if update_fields:
        sql = f"UPDATE dishes SET {', '.join(update_fields)} WHERE id = %s"
        update_values.append(dish_id)
        cursor.execute(sql, tuple(update_values))

    new_tags_str = data.get('tags', '') or ''
    new_tags_set = set(t.strip() for t in new_tags_str.split(',') if t.strip())
    
    tags_changed = False
    try:
        cursor.execute("SHOW TABLES LIKE 'taglink'")
        if cursor.fetchone():
            cursor.execute("DESCRIBE taglink")
            fields = [f['Field'] for f in cursor.fetchall()]
            dish_field = next((fn for fn in fields if 'dish' in fn.lower()), None)
            tag_field = next((fn for fn in fields if 'tag' in fn.lower()), None)
            
            if dish_field and tag_field:
                cursor.execute(f'''
                    SELECT t.name FROM taglink tl 
                    JOIN tags t ON tl.{tag_field} = t.id 
                    WHERE tl.{dish_field} = %s
                ''', (dish_id,))
                old_tags_list = cursor.fetchall()
                old_tags_set = set(t['name'] for t in old_tags_list)
                
                if old_tags_set != new_tags_set:
                    tags_changed = True
                
                if tags_changed:
                    cursor.execute(f'DELETE FROM taglink WHERE {dish_field} = %s', (dish_id,))
                    logger.info(f"删除菜品 {dish_id} 的所有标签关联")
                    
                    cursor.execute('SELECT id, name FROM tags')
                    all_tags_in_db = cursor.fetchall()
                    tag_id_map = {tag['name']: tag['id'] for tag in all_tags_in_db}
                    
                    for tag_name in new_tags_set:
                        if tag_name in tag_id_map:
                            tag_id = tag_id_map[tag_name]
                            cursor.execute(f'INSERT INTO taglink ({dish_field}, {tag_field}) VALUES (%s, %s)', (dish_id, tag_id))
                    
                    logger.info(f"菜品 {dish_id} 标签已更新，同步操作 taglink 表")
    except Exception as e:
        logger.error(f"更新 taglink 失败: {e}")

    if tags_changed:
        clear_tag_cache()
    
    conn.commit()
    conn.close()

    logger.info(f"修改菜品成功 - 菜品ID: {dish_id}")
    return jsonify({'message': '更新成功'})

def delete_dish(dish_id):
    """
    删除菜品
    
    请求参数：
    - dish_id: 菜品ID（URL参数）
    
    返回：
    - message: 删除成功消息
    """
    logger.info(f"删除菜品 - 菜品ID: {dish_id}")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM dishes WHERE id = %s', (dish_id,))
    dish = cursor.fetchone()
    if dish is None:
        conn.close()
        logger.warning(f"删除菜品失败 - 菜品ID: {dish_id} 不存在")
        return jsonify({'error': '菜品不存在'}), 404

    dish_name = dish.get('name', '未知')
    
    cursor.execute('DELETE FROM taglink WHERE dish_id = %s', (dish_id,))
    cursor.execute('DELETE FROM dishes WHERE id = %s', (dish_id,))
    clear_dish_tags_cache()
    conn.commit()
    conn.close()

    logger.info(f"删除菜品成功 - 菜品ID: {dish_id}, 菜品名称: {dish_name}")
    return jsonify({'message': '删除成功'})

# ==================== 注册路由 ====================

def register_dish_routes(app):
    """
    注册菜品管理相关路由
    
    参数：
    - app: Flask应用实例
    """
    app.route('/api/dishes', methods=['GET'])(get_dishes)
    app.route('/api/dishes/<int:dish_id>', methods=['GET'])(get_dish)
    app.route('/api/dishes', methods=['POST'])(create_dish)
    app.route('/api/dishes/<int:dish_id>', methods=['PUT'])(update_dish)
    app.route('/api/dishes/<int:dish_id>', methods=['DELETE'])(delete_dish)
