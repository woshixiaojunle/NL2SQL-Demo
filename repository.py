"""
数据库查询方法（基于 db_connection 连接池）
"""
from datetime import date
from decimal import Decimal
from typing import Optional
from db_connection import execute_query, get_connection
from models import CoreTable, CoreField, Order, OrderItem


# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────

def _row_to_order(row: dict) -> Order:
    return Order(**{k: row[k] for k in row})


def _row_to_order_item(row: dict) -> OrderItem:
    return OrderItem(**{k: row[k] for k in row})


def _row_to_core_table(row: dict) -> CoreTable:
    return CoreTable(**{k: row[k] for k in row})


def _row_to_core_field(row: dict) -> CoreField:
    return CoreField(**{k: row[k] for k in row})


# ─────────────────────────────────────────────
# CoreTable 查询
# ─────────────────────────────────────────────

def get_all_core_tables(checked_only: bool = False) -> list[CoreTable]:
    """获取所有表元数据，可过滤只返回已勾选的"""
    sql = "SELECT * FROM core_table"
    if checked_only:
        sql += " WHERE checked = TRUE"
    sql += " ORDER BY id"
    return [_row_to_core_table(r) for r in execute_query(sql)]


def get_core_table_by_name(table_name: str) -> Optional[CoreTable]:
    """按表名查询元数据"""
    rows = execute_query("SELECT * FROM core_table WHERE table_name = %s", (table_name,))
    return _row_to_core_table(rows[0]) if rows else None


# ─────────────────────────────────────────────
# CoreField 查询
# ─────────────────────────────────────────────

def get_fields_by_table_id(table_id: int, checked_only: bool = False) -> list[CoreField]:
    """获取某张表的所有字段元数据"""
    sql = "SELECT * FROM core_field WHERE table_id = %s"
    params = [table_id]
    if checked_only:
        sql += " AND checked = TRUE"
    sql += " ORDER BY field_index"
    return [_row_to_core_field(r) for r in execute_query(sql, tuple(params))]


# ─────────────────────────────────────────────
# Order 查询
# ─────────────────────────────────────────────

def get_order_by_id(order_id: str) -> Optional[Order]:
    """按订单号查询"""
    rows = execute_query("SELECT * FROM orders WHERE order_id = %s", (order_id,))
    return _row_to_order(rows[0]) if rows else None


def get_orders_by_customer(customer_name: str) -> list[Order]:
    """按客户姓名查询订单"""
    rows = execute_query(
        "SELECT * FROM orders WHERE customer_name = %s ORDER BY order_date DESC",
        (customer_name,)
    )
    return [_row_to_order(r) for r in rows]


def get_orders_by_status(order_status: str) -> list[Order]:
    """按订单状态查询（pending/paid/shipped/completed/cancelled）"""
    rows = execute_query(
        "SELECT * FROM orders WHERE order_status = %s ORDER BY order_date DESC",
        (order_status,)
    )
    return [_row_to_order(r) for r in rows]


def get_orders_by_date_range(start: date, end: date) -> list[Order]:
    """按订单日期范围查询"""
    rows = execute_query(
        "SELECT * FROM orders WHERE order_date BETWEEN %s AND %s ORDER BY order_date",
        (start, end)
    )
    return [_row_to_order(r) for r in rows]


def get_orders_by_payment_method(payment_method: str) -> list[Order]:
    """按支付方式查询（alipay/wechat/cash/card）"""
    rows = execute_query(
        "SELECT * FROM orders WHERE payment_method = %s ORDER BY order_date DESC",
        (payment_method,)
    )
    return [_row_to_order(r) for r in rows]


def get_orders_amount_gt(amount: Decimal) -> list[Order]:
    """查询订单金额大于指定值的订单"""
    rows = execute_query(
        "SELECT * FROM orders WHERE order_amount > %s ORDER BY order_amount DESC",
        (amount,)
    )
    return [_row_to_order(r) for r in rows]


def get_order_stats_by_date(start: date, end: date) -> list[dict]:
    """按日期统计订单数量和金额汇总"""
    return execute_query(
        """
        SELECT
            order_date,
            COUNT(*) AS order_count,
            SUM(order_amount) AS total_amount,
            SUM(actual_amount) AS total_actual,
            SUM(discount_amount) AS total_discount
        FROM orders
        WHERE order_date BETWEEN %s AND %s
        GROUP BY order_date
        ORDER BY order_date
        """,
        (start, end)
    )


# ─────────────────────────────────────────────
# OrderItem 查询
# ─────────────────────────────────────────────

def get_items_by_order_id(order_id: str) -> list[OrderItem]:
    """获取订单的所有明细"""
    rows = execute_query(
        "SELECT * FROM order_items WHERE order_id = %s ORDER BY item_id",
        (order_id,)
    )
    return [_row_to_order_item(r) for r in rows]


def get_items_by_category(category: str) -> list[OrderItem]:
    """按商品分类查询明细"""
    rows = execute_query(
        "SELECT * FROM order_items WHERE product_category = %s ORDER BY item_id",
        (category,)
    )
    return [_row_to_order_item(r) for r in rows]


def get_items_by_brand(brand: str) -> list[OrderItem]:
    """按商品品牌查询明细"""
    rows = execute_query(
        "SELECT * FROM order_items WHERE product_brand = %s ORDER BY item_id",
        (brand,)
    )
    return [_row_to_order_item(r) for r in rows]


def get_order_with_items(order_id: str) -> Optional[dict]:
    """获取订单及其所有明细（聚合结果）"""
    order = get_order_by_id(order_id)
    if not order:
        return None
    return {
        "order": order,
        "items": get_items_by_order_id(order_id)
    }


def get_top_products(limit: int = 10) -> list[dict]:
    """销量 Top N 商品统计"""
    return execute_query(
        """
        SELECT
            product_name,
            product_category,
            SUM(quantity) AS total_quantity,
            SUM(subtotal) AS total_revenue
        FROM order_items
        GROUP BY product_name, product_category
        ORDER BY total_quantity DESC
        LIMIT %s
        """,
        (limit,)
    )


# ─────────────────────────────────────────────
# 简单测试
# ─────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import date
    from db_connection import close_pool

    print("=== 订单查询 ===")
    order = get_order_by_id("ORD001")
    print(order)

    print("\n=== 订单明细 ===")
    items = get_items_by_order_id("ORD001")
    for item in items:
        print(item)

    print("\n=== 日期范围统计 ===")
    stats = get_order_stats_by_date(date(2024, 10, 1), date(2024, 10, 31))
    for s in stats:
        print(s)

    print("\n=== Top 商品 ===")
    for p in get_top_products(5):
        print(p)

    close_pool()
