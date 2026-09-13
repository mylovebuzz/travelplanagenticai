from langchain_neo4j import Neo4jGraph, GraphCypherQAChain
from langchain_core.tools import tool
from langchain_core.prompts import PromptTemplate
#from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field

class KnowledgeQueryInput(BaseModel):
    user_query: str = Field(description="关于旅游景点路线、交通方式、距离、时间等的自然语言问>题，例如：'从故宫到颐和园怎么走？'")

graph = Neo4jGraph(url="bolt://192.168.66.88:7687", username="neo4j", password="your_password", database="neo4j")
llm = ChatOllama(model="qwen2.5:7b", temperature=0.3, base_url="http://172.18.85.196:6666")
print("✅ qwen2.5:7b模型 for Neo4j MCP tool 初始化成功")

CYPHER_GENERATION_TEMPLATE = """任务：根据用户问题生成 Neo4j Cypher 查询语句

图谱结构：
{schema}

重要规则：
1. 使用 MATCH 语句匹配节点和关系。
2. 必须在 MATCH 中给关系绑定变量，例如：[r:CONNECTED_BY]。
3. 在 RETURN 中直接引用已绑定的变量，不要重新定义关系。
4. 查询关系属性时使用 r.property_name 格式。
5. 如果用户问路线，返回起点、终点、交通方式和耗时

正确示例：
MATCH (a:Attraction {{name: '故宫'}})-[r:CONNECTED_BY]->(b:Attraction {{name: '颐和园'}})
RETURN a.name AS 起点, b.name AS 终点, r.transport AS 交通方式, r.duration AS 耗时

错误示例（不要这样写）：
MATCH (a)-[:CONNECTED_BY]->(b)
RETURN relationships(a)-[r:CONNECTED_BY]->(b)

用户问题：{question}
Cypher:"""

cypher_prompt = PromptTemplate(input_variables=["schema", "question"],
                               template=CYPHER_GENERATION_TEMPLATE,)
#cyper_chain = GraphCypherQAChain.from_llm(graph=graph, llm=llm, verbose=True, allow_dangerous_requests=True, return_intermediate_steps=True)
cypher_chain = GraphCypherQAChain.from_llm(graph=graph, llm=llm, verbose=True, allow_dangerous_requests=True, return_intermediate_steps=True, cypher_prompt=cypher_prompt,)

@tool #(args_schema=KnowledgeQueryInput)
def query_travel_knowledge(user_query: str) -> str:
    #"""当你需要查询旅游景点之间的路线、距离、交通方式等结构化信息时使用此工具。
    #输入是一个自然语言问题，如 "从故宫到颐和园的交通方式和耗时"
    #"""
    """查询旅游知识图谱，获取景点之间的路线、交通方式等结构化信息。"""
    try:
        result = cypher_chain.invoke({"query": user_query})
        return result["result"]
    except Exception as e:
        return f"查询知识图谱时出错: {str(e)}"

@tool
def get_graph_schema() -> str:
    """获取 Neo4j 知识图谱的结构信息，包括节点类型和关系类型。"""
    return graph.get_schema
