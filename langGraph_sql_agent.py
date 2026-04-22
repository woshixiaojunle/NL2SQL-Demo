"""
NL2SQL 问数场景 — LangGraph 主流程
步骤：
  1. 用户提问
  2. embed_query       向量化用户问题
  3. retrieve_tables   余弦相似度匹配 TopN 表
  4. build_db_schema   拼装 CREATE TABLE 风格 schema
  5. build_prompt      组装 LLM 消息
  6. generate_sql      调用 glm-4 生成 SQL
  7. execute_sql       执行 SQL（失败自动重试 ≤2 次）
  8. format_result     格式化输出
"""
import ast
import os
import re
import uuid

import dashscope
import numpy as np
from langchain_community.chat_models import ChatZhipuAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from db_connection import close_pool, execute_query

# ─────────────────────────────────────────────
# API Keys
# ─────────────────────────────────────────────
dashscope.api_key = "xxxx"
os.environ["ZHIPUAI_API_KEY"] = "xxxx"

# ─────────────────────────────────────────────
# 配置
# ─────────────────────────────────────────────
TOP_N = 3               # 最多匹配几张表
SIM_THRESHOLD = 0.5     # 余弦相似度阈值
MAX_RETRY = 2           # SQL 执行失败最大重试次数

# LLM
llm = ChatZhipuAI(model="glm-4", temperature=0.5)


# ─────────────────────────────────────────────
# GraphState
# ─────────────────────────────────────────────
class GraphState(TypedDict):
    question: str           # 用户原始问题
    query_vector: list      # 问题向量
    matched_tables: list    # [{"id", "table_name", "table_comment", "similarity"}]
    db_schema: str          # 拼装好的 schema 文本
    messages: list          # 本轮 LLM 消息（每次重新构建，不累积）
    sql: str                # LLM 生成的 SQL
    result: list            # 查询结果 list[dict]
    error: str              # 执行错误信息
    retry_count: int        # SQL 重试次数
    match_status: str       # ok / no_match
    exec_status: str        # pending / success / error / max_retry


# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────
def embedding_str(query_text: str) -> list:
    """调用 DashScope 将文本向量化"""
    resp = dashscope.MultiModalEmbedding.call(
        model="qwen3-vl-embedding",
        input=[{"text": query_text}],
    )
    return resp["output"]["embeddings"][0]["embedding"]


def cosine_similarity(a: list, b: list) -> float:
    """计算两个向量的余弦相似度"""
    va, vb = np.array(a, dtype=float), np.array(b, dtype=float)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    return float(np.dot(va, vb) / denom) if denom > 0 else 0.0


def extract_sql(text: str) -> str:
    """从 LLM 输出中提取 SQL：优先匹配代码块，其次找 SELECT 语句"""
    # 匹配 ```sql ... ``` 或 ``` ... ```
    block = re.search(r"```(?:sql)?\s*([\s\S]+?)```", text, re.IGNORECASE)
    if block:
        return block.group(1).strip()
    # 匹配裸 SQL（SELECT / WITH / INSERT / UPDATE / DELETE 开头）
    bare = re.search(r"((?:SELECT|WITH|INSERT|UPDATE|DELETE)[\s\S]+?;)", text, re.IGNORECASE)
    if bare:
        return bare.group(1).strip()
    return text.strip()


# ─────────────────────────────────────────────
# Node 1 — embed_query
# ─────────────────────────────────────────────
def embed_query(state: GraphState) -> dict:
    """将用户问题向量化"""
    print(f"\n[1] 向量化问题: {state['question']}")
    vector = embedding_str(state["question"])
    return {
        "query_vector": vector,
        "match_status": "",
        "exec_status": "pending",
        "error": "",
        "sql": "",
        "result": [],
        "matched_tables": [],
        "db_schema": "",
    }


# ─────────────────────────────────────────────
# Node 2 — retrieve_tables
# ─────────────────────────────────────────────
def retrieve_tables(state: GraphState) -> dict:
    """余弦相似度匹配 core_table，取 TopN"""
    print("[2] 匹配相关表...")
    rows = execute_query(
        "SELECT id, table_name, table_comment, embedding FROM core_table WHERE checked = TRUE"
    )

    scored = []
    for row in rows:
        if not row["embedding"]:
            continue
        try:
            emb = ast.literal_eval(row["embedding"])
        except Exception:
            continue
        sim = cosine_similarity(state["query_vector"], emb)
        scored.append({
            "id": row["id"],
            "table_name": row["table_name"],
            "table_comment": row["table_comment"],
            "similarity": sim,
        })

    # 按相似度降序，取 TopN 且高于阈值
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    matched = [t for t in scored[:TOP_N] if t["similarity"] >= SIM_THRESHOLD]

    if not matched:
        print(f"  ⚠️  未找到相似度 >= {SIM_THRESHOLD} 的表")
        return {"match_status": "no_match", "matched_tables": []}

    for t in matched:
        print(f"  ✓ {t['table_name']}  相似度={t['similarity']:.4f}")
    return {"match_status": "ok", "matched_tables": matched}


# ─────────────────────────────────────────────
# Node 3 — build_db_schema
# ─────────────────────────────────────────────
def build_db_schema(state: GraphState) -> dict:
    """根据匹配的表查询字段，拼装 schema 文本"""
    print("[3] 拼装 DB Schema...")
    schema_parts = []

    for table in state["matched_tables"]:
        fields = execute_query(
            """
            SELECT field_name, field_type, custom_comment
            FROM core_field
            WHERE table_id = %s AND checked = TRUE
            ORDER BY field_index
            """,
            (table["id"],),
        )
        comment = table.get("table_comment") or table["table_name"]
        lines = [f"-- {comment}", f"CREATE TABLE {table['table_name']} ("]
        field_lines = []
        for f in fields:
            col_comment = f"  -- {f['custom_comment']}" if f["custom_comment"] else ""
            field_lines.append(f"  {f['field_name']} {f['field_type']}{col_comment}")
        lines.append(",\n".join(field_lines))
        lines.append(");")
        schema_parts.append("\n".join(lines))

    db_schema = "\n\n".join(schema_parts)
    print(db_schema)
    return {"db_schema": db_schema}


# ─────────────────────────────────────────────
# Node 4 — build_prompt
# ─────────────────────────────────────────────
def build_prompt(state: GraphState) -> dict:
    """组装本轮 LLM 消息，每次重新构建不累积"""
    print("[4] 组装 Prompt...")
    system_content = (
        "你是一个 PostgreSQL SQL 生成专家。\n"
        "规则：\n"
        "1. 只输出 SQL，不要任何解释或注释\n"
        "2. 使用标准 PostgreSQL 语法\n"
        "3. 字段名和表名使用双引号\n"
        "4. 当前日期函数使用 CURRENT_DATE\n"
        "5. 输出的 SQL 必须以分号结尾"
    )

    human_content = f"数据库表结构如下：\n\n{state['db_schema']}\n\n用户问题：{state['question']}"

    # 若上次 SQL 执行出错，将错误信息带入让 LLM 修正
    if state.get("error"):
        human_content += (
            f"\n\n上次生成的 SQL：\n{state['sql']}"
            f"\n执行报错：{state['error']}"
            f"\n请根据错误信息修正 SQL。"
        )

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=human_content),
    ]
    return {"messages": messages}


# ─────────────────────────────────────────────
# Node 5 — generate_sql
# ─────────────────────────────────────────────
def generate_sql(state: GraphState) -> dict:
    """调用 LLM 生成 SQL"""
    print("[5] 生成 SQL...")
    response = llm.invoke(state["messages"])
    sql = extract_sql(response.content)
    print(f"  生成 SQL:\n  {sql}")
    return {"sql": sql, "error": ""}


# ─────────────────────────────────────────────
# Node 6 — execute_sql
# ─────────────────────────────────────────────
def execute_sql(state: GraphState) -> dict:
    """执行 SQL，失败时记录错误供重试"""
    print(f"[6] 执行 SQL (retry={state['retry_count']})...")
    try:
        result = execute_query(state["sql"])
        print(f"  ✓ 查询成功，返回 {len(result)} 行")
        return {"result": result, "exec_status": "success", "error": ""}
    except Exception as e:
        err = str(e)
        print(f"  ✗ 执行失败: {err}")
        new_retry = state["retry_count"] + 1
        if new_retry <= MAX_RETRY:
            return {"error": err, "exec_status": "error", "retry_count": new_retry}
        else:
            return {"error": err, "exec_status": "max_retry", "retry_count": new_retry}


# ─────────────────────────────────────────────
# Node 7 — format_result
# ─────────────────────────────────────────────
def format_result(state: GraphState) -> dict:
    """格式化输出查询结果"""
    print("\n" + "=" * 60)
    print(f"执行 SQL:\n{state['sql']}\n")

    if state["exec_status"] == "max_retry":
        print(f"❌ SQL 执行失败（已重试 {MAX_RETRY} 次）")
        print(f"最后错误：{state['error']}")
        return {}

    result = state.get("result", [])
    if not result:
        print("查询结果为空")
        return {}

    # 打印表格
    headers = list(result[0].keys())
    col_widths = [max(len(str(h)), max(len(str(r[h])) for r in result)) for h in headers]
    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    header_row = "| " + " | ".join(str(h).ljust(col_widths[i]) for i, h in enumerate(headers)) + " |"

    print(sep)
    print(header_row)
    print(sep)
    for row in result:
        print("| " + " | ".join(str(row[h]).ljust(col_widths[i]) for i, h in enumerate(headers)) + " |")
    print(sep)
    print(f"\n共 {len(result)} 行")
    return {}


# ─────────────────────────────────────────────
# 条件边
# ─────────────────────────────────────────────
def route_after_retrieve(state: GraphState) -> str:
    return "build_db_schema" if state["match_status"] == "ok" else END


def route_after_execute(state: GraphState) -> str:
    """出错且未超重试上限 → 回 build_prompt；否则 → format_result"""
    if state["exec_status"] == "error":
        return "build_prompt"
    return "format_result"


# ─────────────────────────────────────────────
# 构建 Graph
# ─────────────────────────────────────────────
def build_graph():
    builder = StateGraph(GraphState)

    builder.add_node("embed_query", embed_query)
    builder.add_node("retrieve_tables", retrieve_tables)
    builder.add_node("build_db_schema", build_db_schema)
    builder.add_node("build_prompt", build_prompt)
    builder.add_node("generate_sql", generate_sql)
    builder.add_node("execute_sql", execute_sql)
    builder.add_node("format_result", format_result)

    builder.set_entry_point("embed_query")
    builder.add_edge("embed_query", "retrieve_tables")
    builder.add_conditional_edges("retrieve_tables", route_after_retrieve)
    builder.add_edge("build_db_schema", "build_prompt")
    builder.add_edge("build_prompt", "generate_sql")
    builder.add_edge("generate_sql", "execute_sql")
    builder.add_conditional_edges("execute_sql", route_after_execute)
    builder.add_edge("format_result", END)

    memory = MemorySaver()
    return builder.compile(checkpointer=memory)


# ─────────────────────────────────────────────
# 多轮 REPL 入口
# ─────────────────────────────────────────────
def run_repl():
    graph = build_graph()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print("=" * 60)
    print("NL2SQL 问数助手（输入 q 退出）")
    print("=" * 60)

    while True:
        try:
            question = input("\n请输入问题: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if question.lower() == "q":
            break
        if not question:
            continue

        initial_state: GraphState = {
            "question": question,
            "query_vector": [],
            "matched_tables": [],
            "db_schema": "",
            "messages": [],
            "sql": "",
            "result": [],
            "error": "",
            "retry_count": 0,
            "match_status": "",
            "exec_status": "pending",
        }

        result = graph.invoke(initial_state, config)

        # no_match：提示用户换个描述，用同一 thread 重新跑
        if result.get("match_status") == "no_match":
            print("\n⚠️  未找到相关表，请换个描述方式重新输入")

    close_pool()
    print("\n再见！")


if __name__ == "__main__":
    run_repl()
