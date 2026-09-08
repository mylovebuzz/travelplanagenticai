from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
from langchain_core.tools import tool
#from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

class KnowledgeQueryInput(BaseModel):
    user_query: str = Field(description="关于旅游景点路线、交通方式、距离、时间等的自然语言问>题，例如：'从故宫到颐和园怎么走？'")

graph = Neo4jGraph(url="bolt://192.168.66.88:7687", username="neo4j", password="your_password", database="neo4j")
llm = ChatOllama(model="qwen2.5:7b", temperature=0.3, base_url="http://172.18.85.196:6666")
print("✅ qwen2.5:7b 模型4GraphCyperQAChain初始化成功")
cyper_chain = GraphCypherQAChain.from_llm(graph=graph, llm=llm, verbose=True, allow_dangerous_requests=True, return_intermediate_steps=True)

@tool(args_schema=KnowledgeQueryInput)
def query_travel_knowledge(user_query: str) -> str:
    """
    当你需要查询旅游景点之间的路线、距离、交通方式等结构化信息时使用此工具。
    输入是一个自然语言问题，如 "从故宫到颐和园怎么走？"
    """
    try:
        result = cypher_chain.invoke({"query": user_query})
        return result["result"]
    except Exception as e:
        return f"查询知识图谱时出错: {str(e)}"

@tool
def get_graph_schema() -> str:
    """获取 Neo4j 知识图谱的结构信息，包括节点类型和关系类型。"""
    return graph.get_schema
