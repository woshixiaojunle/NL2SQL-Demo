CREATE TABLE core_table (
	id int8 NOT NULL GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START 1 CACHE 1 NO CYCLE),
	ds_id int8 NULL,
	checked bool NOT NULL,
	table_name text NULL,
	table_comment text NULL,
	custom_comment text NULL,
	embedding text NULL,
	CONSTRAINT core_table_pkey PRIMARY KEY (id)
);

CREATE table core_field (
	id int8 NOT NULL GENERATED ALWAYS AS IDENTITY( INCREMENT BY 1 MINVALUE 1 MAXVALUE 9223372036854775807 START 1 CACHE 1 NO CYCLE),
	ds_id int8 NULL,
	table_id int8 NULL,
	checked bool NOT NULL,
	field_name text NULL,
	field_type varchar(128) NULL,
	field_comment text NULL,
	custom_comment text NULL,
	field_index int8 NULL,
	CONSTRAINT core_field_pkey PRIMARY KEY (id)
);

CREATE TABLE orders (
    -- 主键
    order_id VARCHAR(32) PRIMARY KEY,  -- 订单号，格式：DDD+年月日+流水号，如：DDD202410210001

    -- 业务字段
    customer_name VARCHAR(100) NOT NULL,  -- 客户姓名，如：张三、李四
    customer_phone VARCHAR(20),  -- 客户电话，如：13800138000
    order_amount DECIMAL(12,2) NOT NULL,  -- 订单总金额（元），正数，如：299.99
    actual_amount DECIMAL(12,2),  -- 实付金额（元），考虑优惠后的实际支付金额
    discount_amount DECIMAL(12,2) DEFAULT 0,  -- 优惠金额（元），默认0

    -- 状态字段
    order_status VARCHAR(20) DEFAULT 'pending',  -- 订单状态：pending(待支付)/paid(已支付)/shipped(已发货)/completed(已完成)/cancelled(已取消)
    payment_status VARCHAR(20) DEFAULT 'unpaid',  -- 支付状态：unpaid(未支付)/paid(已支付)/refunded(已退款)
    delivery_status VARCHAR(20) DEFAULT 'pending',  -- 发货状态：pending(待发货)/delivering(配送中)/delivered(已送达)

    -- 时间字段（重要：用于时间范围查询）
    order_date DATE NOT NULL,  -- 订单日期，格式：YYYY-MM-DD，如：2024-10-21
    order_datetime TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 订单创建精确时间
    payment_time TIMESTAMP,  -- 支付完成时间
    delivery_time TIMESTAMP,  -- 发货时间
    complete_time TIMESTAMP,  -- 订单完成时间

    -- 其他字段
    payment_method VARCHAR(20),  -- 支付方式：alipay(支付宝)/wechat(微信)/cash(现金)/card(银行卡)
    delivery_address TEXT,  -- 收货地址，如：北京市朝阳区xxx路xx号
    remark TEXT,  -- 订单备注

    -- 审计字段
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 添加表注释
-- 表注释
COMMENT ON TABLE orders IS '订单主表';

-- 字段注释
COMMENT ON COLUMN orders.order_id IS '订单号';
COMMENT ON COLUMN orders.customer_name IS '客户姓名';
COMMENT ON COLUMN orders.customer_phone IS '客户电话';
COMMENT ON COLUMN orders.order_amount IS '订单总金额';
COMMENT ON COLUMN orders.actual_amount IS '实付金额';
COMMENT ON COLUMN orders.discount_amount IS '优惠金额';
COMMENT ON COLUMN orders.order_status IS '订单状态：pending待支付/paid已支付/shipped已发货/completed已完成/cancelled已取消';
COMMENT ON COLUMN orders.payment_status IS '支付状态：unpaid未支付/paid已支付/refunded已退款';
COMMENT ON COLUMN orders.delivery_status IS '发货状态：pending待发货/delivering配送中/delivered已送达';
COMMENT ON COLUMN orders.order_date IS '订单日期';
COMMENT ON COLUMN orders.order_datetime IS '订单创建时间';
COMMENT ON COLUMN orders.payment_time IS '支付时间';
COMMENT ON COLUMN orders.delivery_time IS '发货时间';
COMMENT ON COLUMN orders.complete_time IS '订单完成时间';
COMMENT ON COLUMN orders.payment_method IS '支付方式：alipay支付宝/wechat微信/cash现金/card银行卡';
COMMENT ON COLUMN orders.delivery_address IS '收货地址';
COMMENT ON COLUMN orders.remark IS '订单备注';


CREATE TABLE order_items (
    -- 主键
    item_id SERIAL PRIMARY KEY,                            -- 明细ID

    -- 关联字段
    order_id VARCHAR(32) NOT NULL,                         -- 订单号

    -- 商品信息
    product_name VARCHAR(200) NOT NULL,                    -- 商品名称
    product_category VARCHAR(50),                          -- 商品分类
    product_brand VARCHAR(50),                             -- 商品品牌
    product_spec VARCHAR(100),                             -- 商品规格
    unit_price DECIMAL(10,2) NOT NULL,                     -- 单价
    quantity INT NOT NULL DEFAULT 1,                       -- 数量
    subtotal DECIMAL(12,2) GENERATED ALWAYS AS (unit_price * quantity) STORED,  -- 小计金额

    -- 其他字段
    discount DECIMAL(10,2) DEFAULT 0,                      -- 单品优惠
    remark TEXT                                          -- 明细备注

);

-- 表注释
COMMENT ON TABLE order_items IS '订单明细表';

-- 字段注释
COMMENT ON COLUMN order_items.item_id IS '明细ID';
COMMENT ON COLUMN order_items.order_id IS '订单号';
COMMENT ON COLUMN order_items.product_name IS '商品名称';
COMMENT ON COLUMN order_items.product_category IS '商品分类';
COMMENT ON COLUMN order_items.product_brand IS '商品品牌';
COMMENT ON COLUMN order_items.product_spec IS '商品规格';
COMMENT ON COLUMN order_items.unit_price IS '单价';
COMMENT ON COLUMN order_items.quantity IS '数量';
COMMENT ON COLUMN order_items.subtotal IS '小计金额';
COMMENT ON COLUMN order_items.discount IS '单品优惠';
COMMENT ON COLUMN order_items.remark IS '明细备注';


-- 测试数据
-- 插入订单
INSERT INTO orders (order_id, customer_name, order_amount, actual_amount, order_status, payment_status, order_date) VALUES
('ORD001', '张三', 8999.00, 8999.00, 'completed', 'paid', '2024-10-21'),
('ORD002', '李四', 599.00, 599.00, 'paid', 'paid', '2024-10-21'),
('ORD003', '王芳', 3299.00, 3099.00, 'shipped', 'paid', '2024-10-22');

-- 插入明细
INSERT INTO order_items (order_id, product_name, product_category, unit_price, quantity) VALUES
('ORD001', 'iPhone 15', '手机', 8999.00, 1),
('ORD002', '小米手环', '智能穿戴', 299.00, 2),
('ORD003', '华为平板', '平板电脑', 3299.00, 1);