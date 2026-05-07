import os
from functools import partial
from langgraph.graph import START, END, StateGraph
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import ToolNode

from .graph_state import State
from .nodes import *
from .edges import *

def create_agent_graph(llm, tools_list):
    llm_with_tools = llm.bind_tools(tools_list)
    tool_node = ToolNode(tools_list)

    # Inicialización dinámica de la memoria de LangGraph (Checkpointer)
    DB_USER = os.environ.get("DB_USER")
    DB_PASS = os.environ.get("DB_PASS")
    DB_NAME = os.environ.get("DB_NAME")
    INSTANCE_CONNECTION_NAME = os.environ.get("INSTANCE_CONNECTION_NAME")

    checkpointer = InMemorySaver()

    if DB_USER and DB_PASS and DB_NAME:
        try:
            from psycopg_pool import ConnectionPool
            from langgraph.checkpoint.postgres import PostgresSaver

            # En Cloud Run, Google monta la base de datos como un Unix socket en /cloudsql/
            if INSTANCE_CONNECTION_NAME:
                conninfo = f"host=/cloudsql/{INSTANCE_CONNECTION_NAME} user={DB_USER} password={DB_PASS} dbname={DB_NAME}"
            else:
                db_host = os.environ.get("DB_HOST", "127.0.0.1")
                conninfo = f"host={db_host} user={DB_USER} password={DB_PASS} dbname={DB_NAME}"

            print("🔗 Conectando memoria persistente de LangGraph a PostgreSQL...")
            # Pool de conexiones psycopg3 compatible con LangGraph
            pool = ConnectionPool(conninfo=conninfo, max_size=5, min_size=1, kwargs={"autocommit": True})
            
            checkpointer = PostgresSaver(pool)
            # Crea las tablas internas de LangGraph automáticamente si no existen
            checkpointer.setup()
            print("✅ Memoria persistente conectada de forma segura a PostgreSQL.")
        except Exception as e:
            print(f"⚠️ No se pudo inicializar PostgresSaver (usando InMemorySaver de fallback): {e}")
            checkpointer = InMemorySaver()

    print("Compiling agent graph...")
    agent_builder = StateGraph(AgentState)
    agent_builder.add_node("orchestrator", partial(orchestrator, llm_with_tools=llm_with_tools))
    agent_builder.add_node("tools", tool_node)
    agent_builder.add_node("compress_context", partial(compress_context, llm=llm))
    agent_builder.add_node("fallback_response", partial(fallback_response, llm=llm))
    agent_builder.add_node(should_compress_context)
    agent_builder.add_node(collect_answer)

    agent_builder.add_edge(START, "orchestrator")
    agent_builder.add_conditional_edges("orchestrator", route_after_orchestrator_call, {"tools": "tools", "fallback_response": "fallback_response", "collect_answer": "collect_answer"})
    agent_builder.add_edge("tools", "should_compress_context")
    agent_builder.add_edge("compress_context", "orchestrator")
    agent_builder.add_edge("fallback_response", "collect_answer")
    agent_builder.add_edge("collect_answer", END)

    agent_subgraph = agent_builder.compile()

    graph_builder = StateGraph(State)
    graph_builder.add_node("summarize_history", partial(summarize_history, llm=llm))
    graph_builder.add_node("rewrite_query", partial(rewrite_query, llm=llm))
    graph_builder.add_node(request_clarification)
    graph_builder.add_node("agent", agent_subgraph)
    graph_builder.add_node("aggregate_answers", partial(aggregate_answers, llm=llm))

    graph_builder.add_edge(START, "summarize_history")
    graph_builder.add_edge("summarize_history", "rewrite_query")
    graph_builder.add_conditional_edges("rewrite_query", route_after_rewrite)
    graph_builder.add_edge("request_clarification", "rewrite_query")
    graph_builder.add_edge(["agent"], "aggregate_answers")
    graph_builder.add_edge("aggregate_answers", END)

    agent_graph = graph_builder.compile(checkpointer=checkpointer, interrupt_before=["request_clarification"])

    print("✓ Agent graph compiled successfully.")
    return agent_graph