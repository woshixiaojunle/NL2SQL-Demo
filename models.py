"""
数据库实体类（对应 初始化表.sql 中的表结构）
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional


@dataclass
class CoreTable:
    """元数据 - 表信息"""
    id: Optional[int] = None
    ds_id: Optional[int] = None
    checked: bool = False
    table_name: Optional[str] = None
    table_comment: Optional[str] = None
    custom_comment: Optional[str] = None
    embedding: Optional[str] = None


@dataclass
class CoreField:
    """元数据 - 字段信息"""
    id: Optional[int] = None
    ds_id: Optional[int] = None
    table_id: Optional[int] = None
    checked: bool = False
    field_name: Optional[str] = None
    field_type: Optional[str] = None
    field_comment: Optional[str] = None
    custom_comment: Optional[str] = None
    field_index: Optional[int] = None


@dataclass
class Order:
    """订单主表"""
    order_id: str = ""
    customer_name: str = ""
    customer_phone: Optional[str] = None
    order_amount: Decimal = Decimal("0")
    actual_amount: Optional[Decimal] = None
    discount_amount: Decimal = Decimal("0")
    order_status: str = "pending"       # pending/paid/shipped/completed/cancelled
    payment_status: str = "unpaid"      # unpaid/paid/refunded
    delivery_status: str = "pending"    # pending/delivering/delivered
    order_date: Optional[date] = None
    order_datetime: Optional[datetime] = None
    payment_time: Optional[datetime] = None
    delivery_time: Optional[datetime] = None
    complete_time: Optional[datetime] = None
    payment_method: Optional[str] = None   # alipay/wechat/cash/card
    delivery_address: Optional[str] = None
    remark: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class OrderItem:
    """订单明细表"""
    item_id: Optional[int] = None
    order_id: str = ""
    product_name: str = ""
    product_category: Optional[str] = None
    product_brand: Optional[str] = None
    product_spec: Optional[str] = None
    unit_price: Decimal = Decimal("0")
    quantity: int = 1
    subtotal: Optional[Decimal] = None   # 数据库计算列，只读
    discount: Decimal = Decimal("0")
    remark: Optional[str] = None
