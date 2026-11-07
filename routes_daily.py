#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
@file routes_daily.py
@description 每日推荐菜品API模块
@version 1.0.0
@author Menu Cloud Team
@date 2026-07-26

功能：
1. 获取某日每日推荐菜品
2. 设置/更新某日每日推荐菜品
3. 删除某日每日推荐菜品（恢复随机）
4. 获取每日推荐历史列表
"""

from flask import jsonify, request
import pymysql
from dataconf import get_db_connection, get_tag_caches
from logconfig import log_config

logger = log_config()


# ==================== 辅助函数 ====================

def _process_dish(dish, tag_cache, dish_tags_map):
    """
    处理菜品的标签信息（与 routes_dish.py 保持一致）
    """
    if not dish:
        return None

    if 'detail_description' in dish and dish['detail_description']:
        dish['detail_desc'] = dish['detail_description']
    if 'method_desc' in dish and dish['method_desc']:
        dish['method'] = dish['method_desc']
    if 'ingredients_desc' in dish and dish['ingredients_desc']:
        dish['ingredients'] = dish['ingredients_desc']

    dish_id = dish.get('id')
    tags = []
    if dish_id and dish_id in dish_tags_map:
        tags = dish_tags_map[dish_id]
    else:
        tags_str = dish.get('tags', '')
        if tags_str:
            for tag_name in tags_str.split(','):
                tag_name = tag_name.strip()
                if tag_name and tag_name in tag_cache:
                    tags.append({
                        'name': tag_name,
                        'background_color': tag_cache[tag_name]['background_color'],
                        'text_color': tag_cache[tag_name]['text_color']
                    })

    dish['tags'] = ','.join([t['name'] for t in tags])
    dish['tag_details'] = tags
    return dish


def _fetch_dish_by_id(conn, dish_id, tag_cache, dish_tags_map):
    """
    根据菜品ID获取菜品详情（含标签信息）
    """
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT id, name, price, image, description, detail_description,
                       method, ingredients
                FROM dishes
                WHERE id = %s
            """
            cursor.execute(sql, (dish_id,))
            dish = cursor.fetchone()
            if dish:
                # 类型转换
                if 'price' in dish and dish['price'] is not None:
                    dish['price'] = str(dish['price'])
                if 'id' in dish:
                    dish['id'] = int(dish['id'])

                # 从 dish_tags 表取标签（如果存在），否则用 dish 表的 tags 字段
                tags = []
                if dish_id in dish_tags_map:
                    tags = dish_tags_map[dish_id]
                else:
                    tags_str = dish.get('tags', '') or ''
                    if tags_str:
                        for tag_name in tags_str.split(','):
                            tag_name = tag_name.strip()
                            if tag_name and tag_name in tag_cache:
                                tags.append({
                                    'name': tag_name,
                                    'background_color': tag_cache[tag_name]['background_color'],
                                    'text_color': tag_cache[tag_name]['text_color']
                                })

                # 字段兼容（与 process_dish_tags 保持一致）
                if dish.get('detail_description'):
                    dish['detail_desc'] = dish['detail_description']
                if dish.get('method'):
                    dish['method_desc'] = dish['method']
                if dish.get('ingredients'):
                    dish['ingredients_desc'] = dish['ingredients']

                dish['tags'] = ','.join([t['name'] for t in tags])
                dish['tag_details'] = tags
                return dish
    except Exception as e:
        logger.error(f"查询菜品失败: {e}")
    return None


# ==================== API路由函数 ====================

def get_daily_recommend():
    """
    获取某日每日推荐菜品

    请求参数（query）:
    - date: 推荐日期 (YYYY-MM-DD)，默认今天

    返回:
    - date: 推荐日期
    - dish: 菜品详情（含 tags / tag_details）
    - set_by: 设置人
    - is_manual: 是否手动设置（false 表示使用日期 hash 随机）
    - state: 状态（1=生效，0=历史）
    """
    date_str = request.args.get('date')
    if not date_str:
        from datetime import date
        date_str = date.today().strftime('%Y-%m-%d')

    conn = None
    try:
        conn = get_db_connection()
        tag_cache, dish_tags_map = get_tag_caches()

        with conn.cursor() as cursor:
            # 只查询 state=1 的生效推荐
            # 多个版本时按 updated_at 倒序，取最新一条
            sql = """
                SELECT dr.dish_id, dr.set_by, dr.note, dr.state, dr.updated_at
                FROM daily_recommend dr
                WHERE dr.recommend_date = %s AND dr.state = 1
                ORDER BY dr.updated_at DESC
                LIMIT 1
            """
            cursor.execute(sql, (date_str,))
            row = cursor.fetchone()

            if row:
                dish = _fetch_dish_by_id(conn, row['dish_id'], tag_cache, dish_tags_map)
                if dish:
                    return jsonify({
                        'success': True,
                        'date': date_str,
                        'dish': dish,
                        'set_by': row['set_by'],
                        'note': row['note'],
                        'state': row['state'],
                        'is_manual': True
                    }), 200
                else:
                    # 菜品已被删除，标记为停用
                    cursor.execute(
                        "UPDATE daily_recommend SET state = 0 WHERE recommend_date = %s AND state = 1",
                        (date_str,)
                    )
                    conn.commit()
                    logger.warning(f"每日推荐菜品 {row['dish_id']} 已被删除，已停用 {date_str} 的记录")

            return jsonify({
                'success': True,
                'date': date_str,
                'dish': None,
                'is_manual': False,
                'message': '当日未设置推荐，前端应使用日期 hash 随机'
            }), 200

    except Exception as e:
        logger.error(f"获取每日推荐失败: {e}")
        return jsonify({'success': False, 'message': f'获取失败: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()


def set_daily_recommend():
    """
    设置/更新某日每日推荐菜品

    业务逻辑：
    1. 将当日所有已有记录 state 设为 0（停用历史）
    2. 插入新记录，state=1（最新生效）

    请求体（JSON）:
    - date: 推荐日期 (YYYY-MM-DD)，默认今天
    - dish_id: 菜品ID（必填）
    - set_by: 设置人（可选，默认 'admin'）
    - note: 备注（可选）

    返回:
    - success: 是否成功
    - message: 提示信息
    - dish_id: 生效的菜品ID
    - previous_dish_id: 之前的菜品ID（如有）
    """
    data = request.get_json(silent=True) or {}
    if not data and request.data:
        try:
            import json as _json
            data = _json.loads(request.data.decode('utf-8'))
        except Exception:
            pass
    dish_id = data.get('dish_id')
    if not dish_id:
        return jsonify({'success': False, 'message': '缺少菜品ID'}), 400

    date_str = data.get('date')
    if not date_str:
        from datetime import date
        date_str = date.today().strftime('%Y-%m-%d')

    set_by = data.get('set_by', 'admin')
    note = data.get('note', '')

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 检查菜品是否存在
            cursor.execute("SELECT id FROM dishes WHERE id = %s", (dish_id,))
            if not cursor.fetchone():
                return jsonify({'success': False, 'message': f'菜品 {dish_id} 不存在'}), 404

            # 1. 找出之前的生效推荐（用于返回）
            cursor.execute("""
                SELECT dish_id FROM daily_recommend
                WHERE recommend_date = %s AND state = 1
                ORDER BY updated_at DESC LIMIT 1
            """, (date_str,))
            prev_row = cursor.fetchone()
            previous_dish_id = prev_row['dish_id'] if prev_row else None

            # 2. 关键步骤：将当日所有已有记录 state 设为 0
            cursor.execute("""
                UPDATE daily_recommend
                SET state = 0
                WHERE recommend_date = %s AND state = 1
            """, (date_str,))
            disabled_count = cursor.rowcount

            # 3. 插入新记录，state=1
            cursor.execute("""
                INSERT INTO daily_recommend (recommend_date, dish_id, state, set_by, note)
                VALUES (%s, %s, 1, %s, %s)
            """, (date_str, dish_id, set_by, note))
            new_id = cursor.lastrowid

            conn.commit()

            logger.info(
                f"每日推荐已更新: {date_str} -> 菜品 {dish_id} (id={new_id}) by {set_by}, "
                f"停用历史 {disabled_count} 条"
            )
            return jsonify({
                'success': True,
                'message': '每日推荐已更新',
                'date': date_str,
                'dish_id': dish_id,
                'previous_dish_id': previous_dish_id,
                'disabled_count': disabled_count
            }), 200

    except Exception as e:
        logger.error(f"设置每日推荐失败: {e}")
        if conn:
            conn.rollback()
        return jsonify({'success': False, 'message': f'设置失败: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()


def delete_daily_recommend():
    """
    停用某日每日推荐菜品（恢复为随机推荐）
    实际是只把当日所有生效记录 state 改为 0，保留历史

    请求参数（query）:
    - date: 推荐日期 (YYYY-MM-DD)，默认今天

    返回:
    - success: 是否成功
    - message: 提示信息
    """
    date_str = request.args.get('date')
    if not date_str:
        from datetime import date
        date_str = date.today().strftime('%Y-%m-%d')

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 将当日所有生效记录 state=0（停用），保留历史
            cursor.execute("""
                UPDATE daily_recommend
                SET state = 0
                WHERE recommend_date = %s AND state = 1
            """, (date_str,))
            affected = cursor.rowcount
            conn.commit()
            logger.info(f"停用每日推荐: {date_str}, 影响行数: {affected}")
            return jsonify({
                'success': True,
                'message': '每日推荐已清除，将恢复随机推荐' if affected else '当日没有推荐记录',
                'date': date_str,
                'affected': affected
            }), 200

    except Exception as e:
        logger.error(f"删除每日推荐失败: {e}")
        if conn:
            conn.rollback()
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()


def list_daily_recommend_history():
    """
    获取每日推荐历史列表（含 state 状态）

    请求参数（query）:
    - limit: 返回数量（默认 30）
    - offset: 偏移量（默认 0）
    - state: 状态筛选（可选，0=历史，1=生效，不传则全部）
    - date: 日期筛选（可选，YYYY-MM-DD）

    返回:
    - items: 列表
    - total: 总数
    """
    limit = request.args.get('limit', 30, type=int)
    offset = request.args.get('offset', 0, type=int)
    state = request.args.get('state', type=int)
    date_str = request.args.get('date')
    limit = min(max(1, limit), 100)
    offset = max(0, offset)

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 动态构建 WHERE
            where_clauses = []
            where_values = []
            if state is not None:
                where_clauses.append("dr.state = %s")
                where_values.append(state)
            if date_str:
                where_clauses.append("dr.recommend_date = %s")
                where_values.append(date_str)
            where_sql = ('WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''

            # 总数
            cursor.execute(f"SELECT COUNT(*) AS cnt FROM daily_recommend dr {where_sql}", tuple(where_values))
            total = cursor.fetchone()['cnt']

            # 列表（关联菜品表）
            sql = f"""
                SELECT dr.id, dr.recommend_date, dr.dish_id, dr.state, dr.set_by, dr.note,
                       dr.created_at, dr.updated_at,
                       d.name AS dish_name, d.image, d.price
                FROM daily_recommend dr
                LEFT JOIN dishes d ON dr.dish_id = d.id
                {where_sql}
                ORDER BY dr.recommend_date DESC, dr.state DESC, dr.updated_at DESC
                LIMIT %s OFFSET %s
            """
            cursor.execute(sql, tuple(where_values) + (limit, offset))
            rows = cursor.fetchall()

            # 转换字段
            items = []
            for row in rows:
                item = {
                    'id': row['id'],
                    'date': row['recommend_date'].strftime('%Y-%m-%d') if row.get('recommend_date') else None,
                    'dish_id': row['dish_id'],
                    'state': row['state'],
                    'state_label': '生效中' if row['state'] == 1 else '已停用',
                    'dish_name': row['dish_name'],
                    'dish_image': row.get('image'),
                    'dish_price': str(row['price']) if row.get('price') is not None else None,
                    'set_by': row['set_by'],
                    'note': row['note'],
                    'created_at': row['created_at'].strftime('%Y-%m-%d %H:%M:%S') if row.get('created_at') else None,
                    'updated_at': row['updated_at'].strftime('%Y-%m-%d %H:%M:%S') if row.get('updated_at') else None
                }
                items.append(item)

            return jsonify({
                'success': True,
                'items': items,
                'total': total,
                'limit': limit,
                'offset': offset
            }), 200

    except Exception as e:
        logger.error(f"获取每日推荐历史失败: {e}")
        return jsonify({'success': False, 'message': f'获取失败: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()


# ==================== 路由注册 ====================

def register_daily_routes(app):
    """
    注册每日推荐相关路由
    """
    app.add_url_rule('/api/daily-recommend', view_func=get_daily_recommend, methods=['GET'])
    app.add_url_rule('/api/daily-recommend', view_func=set_daily_recommend, methods=['POST'])
    app.add_url_rule('/api/daily-recommend', view_func=delete_daily_recommend, methods=['DELETE'])
    app.add_url_rule('/api/daily-recommend/history', view_func=list_daily_recommend_history, methods=['GET'])
    logger.info('每日推荐路由注册完成')
