"""
    为问数表结构提供向量初始化
"""
from langchain_community.chat_models import ChatZhipuAI
# from langchain_community.embeddings import DashScopeEmbeddings
import os
import dashscope


# 强烈建议通过环境变量设置你的API Key，替换"your-api-key"为真实值
dashscope.api_key = "xxxx"


# 文本向量化
def embedding_str(query_text: str)-> str:
    """
        将文本向量化，返回向量列表

        Args:
            query_text: 待向量化的文本

        Returns:
            list: 向量列表，例如 [0.001, -0.002, ...]
        """
    input_data = [{'text': query_text}]
    resp = dashscope.MultiModalEmbedding.call(
        model="qwen3-vl-embedding",
        input=input_data
    )

    # 提取向量
    embedding_vector = resp['output']['embeddings'][0]['embedding']

    print(f"当前文本: {query_text}")
    print(f"向量维度: {len(embedding_vector)}")

    return embedding_vector



# 目标表（从这两张业务表读取结构）
TARGET_TABLES = ["orders", "order_items"]

# Postgres 连接配置
POSTGRES_SERVER = "localhost"
POSTGRES_PORT = 5432
POSTGRES_DB = "demo01"
POSTGRES_USER = "root"
POSTGRES_PASSWORD = "Password123@pg"


def _get_conn():
    import psycopg2
    return psycopg2.connect(
        host=POSTGRES_SERVER,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )


def _fetch_table_comment(cur, table_name: str) -> str:
    """从 pg_catalog 读取表注释"""
    cur.execute(
        """
        SELECT obj_description(c.oid, 'pg_class')
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = %s AND n.nspname = 'public'
        """,
        (table_name,),
    )
    row = cur.fetchone()
    return (row[0] or table_name) if row else table_name


def _fetch_fields(cur, table_name: str) -> list[dict]:
    """从 information_schema 读取字段信息（含注释）"""
    cur.execute(
        """
        SELECT
            a.attnum          AS field_index,
            a.attname         AS field_name,
            pg_catalog.format_type(a.atttypid, a.atttypmod) AS field_type,
            col_description(a.attrelid, a.attnum)            AS field_comment
        FROM pg_catalog.pg_attribute a
        JOIN pg_catalog.pg_class c ON c.oid = a.attrelid
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = %s
          AND n.nspname = 'public'
          AND a.attnum > 0
          AND NOT a.attisdropped
        ORDER BY a.attnum
        """,
        (table_name,),
    )
    return [
        {
            "field_index": row[0],
            "field_name": row[1],
            "field_type": row[2],
            "field_comment": row[3] or row[1],
        }
        for row in cur.fetchall()
    ]


def init_embbeding_table(cur, table_name: str) -> int:
    """
    为表初始化 core_table，返回插入后的 id
    checked 默认 true
    table_name 表名称
    table_comment 表备注
    custom_comment 默认等于 table_comment
    embedding   向量值 custom_comment的向量值
    """
    table_comment = _fetch_table_comment(cur, table_name)
    embedding_vector = embedding_str(table_comment)

    # 若已存在则更新，否则插入
    cur.execute("SELECT id FROM core_table WHERE table_name = %s", (table_name,))
    existing = cur.fetchone()
    if existing:
        cur.execute(
            """
            UPDATE core_table
            SET checked = TRUE, table_comment = %s, custom_comment = %s, embedding = %s
            WHERE id = %s
            """,
            (table_comment, table_comment, str(embedding_vector), existing[0]),
        )
        print(f"[core_table] 更新: {table_name}")
        return existing[0]
    else:
        cur.execute(
            """
            INSERT INTO core_table (checked, table_name, table_comment, custom_comment, embedding)
            VALUES (TRUE, %s, %s, %s, %s)
            RETURNING id
            """,
            (table_name, table_comment, table_comment, str(embedding_vector)),
        )
        new_id = cur.fetchone()[0]
        print(f"[core_table] 插入: {table_name}  id={new_id}")
        return new_id


def init_embbeding_table_feild(cur, table_name: str, table_id: int):
    """
    为表字段初始化 core_field
    table_id core_table的id
    checked 默认 true
    field_name 字段名称
    field_type 字段类型如：varchar(128)
    field_comment 字段备注
    custom_comment 默认等于 field_comment
    field_index   序号
    """
    fields = _fetch_fields(cur, table_name)
    for f in fields:
        cur.execute(
            "SELECT id FROM core_field WHERE table_id = %s AND field_name = %s",
            (table_id, f["field_name"]),
        )
        existing = cur.fetchone()
        if existing:
            cur.execute(
                """
                UPDATE core_field
                SET checked = TRUE, field_type = %s, field_comment = %s,
                    custom_comment = %s, field_index = %s
                WHERE id = %s
                """,
                (
                    f["field_type"], f["field_comment"],
                    f["field_comment"], f["field_index"], existing[0],
                ),
            )
            print(f"  [core_field] 更新: {f['field_name']}")
        else:
            cur.execute(
                """
                INSERT INTO core_field
                    (ds_id, table_id, checked, field_name, field_type, field_comment, custom_comment, field_index)
                VALUES (NULL, %s, TRUE, %s, %s, %s, %s, %s)
                """,
                (
                    table_id, f["field_name"], f["field_type"],
                    f["field_comment"], f["field_comment"], f["field_index"],
                ),
            )
            print(f"  [core_field] 插入: {f['field_name']}")


if __name__ == "__main__":
    conn = _get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                for tbl in TARGET_TABLES:
                    print(f"\n>>> 处理表: {tbl}")
                    table_id = init_embbeding_table(cur, tbl)
                    init_embbeding_table_feild(cur, tbl, table_id)
        print("\n初始化完成")
    finally:
        conn.close()
