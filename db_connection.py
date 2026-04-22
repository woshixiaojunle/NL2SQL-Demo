"""
PostgreSQL 数据库连接池管理
"""
from psycopg2 import pool
from contextlib import contextmanager

# 数据库配置
POSTGRES_SERVER = "localhost"
POSTGRES_PORT = 5432
POSTGRES_DB = "demo01"
POSTGRES_USER = "root"
POSTGRES_PASSWORD = "Password123@pg"

# 连接池（懒加载单例）
_connection_pool: pool.ThreadedConnectionPool | None = None


def get_pool() -> pool.ThreadedConnectionPool:
    """获取连接池（首次调用时初始化）"""
    global _connection_pool
    if _connection_pool is None or _connection_pool.closed:
        _connection_pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            host=POSTGRES_SERVER,
            port=POSTGRES_PORT,
            dbname=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
        )
    return _connection_pool


@contextmanager
def get_connection():
    """从连接池获取连接，使用完自动归还"""
    conn_pool = get_pool()
    conn = conn_pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn_pool.putconn(conn)


@contextmanager
def get_cursor():
    """直接获取游标，适合快速查询"""
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            yield cursor
        finally:
            cursor.close()


def execute_query(sql: str, params: tuple = None) -> list[dict]:
    """
    执行查询并返回字典列表
    :param sql: SQL 语句
    :param params: 参数化查询参数
    :return: 查询结果列表
    """
    with get_cursor() as cursor:
        cursor.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def close_pool():
    """关闭连接池（程序退出时调用）"""
    global _connection_pool
    if _connection_pool and not _connection_pool.closed:
        _connection_pool.closeall()
        _connection_pool = None


# 简单测试
if __name__ == "__main__":
    results = execute_query("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    print("当前数据库表：")
    for row in results:
        print(" -", row["table_name"])
    close_pool()
