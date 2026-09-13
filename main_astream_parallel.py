from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.tools import StructuredTool
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langgraph.checkpoint.neo4j import Neo4jSaver
from langgraph.graph import StateGraph, MessagesState
from langchain_neo4j import Neo4jGraph
from neo4j import GraphDatabase

from fastmcp import Client
from typing import Literal, Any
import os
import sys
from pathlib import Path

#import json
import asyncio
import uuid
from datetime import datetime

from memory_manager import get_memory
from cache_manager import get_cache
from parallel_tools import ParallelToolNode
from async_neo4j_saver import AsyncNeo4jSaver
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print("✅ 已加载 .env 文件")
except ImportError:
    print("⚠️ python-dotenv 未安装，跳过 .env 加载")

def setup_deepseek_env():
    api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("=" * 60)
        print("❌ 错误: 未找到 API Key")
        print("=" * 60)
        print("\n请设置 API Key，方法如下:")
        print("  1. 在终端执行: export OPENAI_API_KEY='your-key-here'")
        print("  2. 或创建 .env 文件并添加: OPENAI_API_KEY=your-key-here")
        print("  3. 或直接在代码中设置（不推荐）")
        print("\n获取 API Key: https://platform.deepseek.com/")
        print("=" * 60)
        sys.exit(1)
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_BASE_URL"] = "https://api.deepseek.com/v1"
    print(f"✅ API Key 已配置: {api_key[:10]}...")
    print(f"✅ Base URL: {os.environ['OPENAI_BASE_URL']}")

setup_deepseek_env()

#model = ChatOpenAI(model="deepseek-chat", api_key=os.environ.get("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com/v1", temperature=0.7)
#model = ChatOpenAI(model="deepseek-free", temperature=0.7)
#model = ChatOllama(model="deepseek-r1:7b", temperature=0.7, base_url="http://localhost:11434")
#model = ChatOllama(model="deepseek-r1:7b", temperature=0.7, base_url="http://192.168.66.88:6666")
model = ChatOllama(model="qwen2.5:7b", temperature=0.3, base_url="http://192.168.66.88:6666")
print("✅ DeepSeek 模型初始化成功")

memory = get_memory()
cache = get_cache()
#driver = GraphDatabase.driver("bolt://192.168.66.88:7687", auth=("neo4j", "your_password"))
#checkpointer = Neo4jSaver(driver)
#checkpoint = AsyncNeo4jSaver(url="bolt://192.168.66.88:7687", username="neo4j", password="your_password")
saver = AsyncNeo4jSaver(url="bolt://192.168.66.88:7687", username="neo4j", password="your_password")
#checkpointer = Neo4jSaver.from_conn_string(uri="bolt://192.168.66.88:7687", user="neo4j", password="your-password")
#must in function await checkpointer.setup()
#checkpoint.setup()

def convert_mcp_tool_to_langchain_bak(mcp_tool: Any, client: Client) -> StructuredTool:
    tool_name = mcp_tool.name
    tool_description = mcp_tool.description or f"Tool: {tool_name}"
    async def call_mcp_tool_with_cache(**kwargs):
        print(f"🔧 包装函数收到的参数: {kwargs}")
        if not kwargs:
            return "❌ 错误：没有传入任何参数。"
        cached_result = cache.get(tool_name, kwargs)
        if cached_result:
            return cached_result
        try:
            result = await client.call_tool(tool_name, arguments=kwargs)
            result_text = result.content[0].text if result.content else str(result)
            ttl = 3600 if tool_name == "get_route" else 1800
            cache.set(tool_name, kwargs, result_text, ttl)
            return result_text
        except Exception as e:
            return f"工具调用失败: {str(e)}"

    async def call_mcp_tool(**kwargs):
        try:
            result = await client.call_tool(tool_name, arguments=kwargs)
            return result.content[0].text if result.content else str(result)
        except Exception as e:
            return f"工具调用失败: {str(e)}"
    #return StructuredTool.from_function(coroutine=call_mcp_tool, name=tool_name, description=tool_description,)
   #origin
  #Missing required argument [type=missing_argument, input_value={}, input_type=dict]
    #For further information visit https://errors.pydantic.dev/2.13/v/missing_argument
   #destination
  #Missing required argument [type=missing_argument, input_value={}, input_type=dict]
    #For further information visit https://errors.pydantic.dev/2.13/v/missing_argument
    from pydantic import BaseModel, Field

    class RouteArgs(BaseModel):
        origin: str = Field(description="起点地名")
        destination: str = Field(description="终点地名")

    class NearbyArgs(BaseModel):
        location: str = Field(description="位置地名")
        keyword: str = Field(description="搜索关键词，如'美食'、'景点'")


    return StructuredTool.from_function(coroutine=call_mcp_tool_with_cache,
                                        name=tool_name, description=tool_description, args_schema=RouteArgs)

async def connect_mcp_tools(server_url: str):
    #client = Client("http://localhost:8000/mcp")
    client = Client(server_url)
    #async with client:
    await client.__aenter__()
    #Error calling tool 'get_route': 'type' object does not support the asynchronous context manager protocol
    #tools = await client.list_tools()
    #print(f"   发现 {len(tools)} 个原始工具: {[t.name for t in tools]} {tools}")
    #langchain_tools = []
    #for tool in tools:
    #    converted = convert_mcp_tool_to_langchain(tool)
        #langchain_tools.append(tool)
    #    langchain_tools.append(converted)
    #return client, langchain_tools
    return client
        #return [tool.to_langChain() for tool in tools]

#async def create_agent():
async def create_agent(session_id: str = None):
    if session_id is None:
        session_id = str(uuid.uuid4())
        print(f"🆕 创建新会话: {session_id[:8]}...")
    print("🔌 正在连接 MCP 服务...")
    #map_client, map_tools = await connect_mcp_tools("http://localhost:8000/mcp")
    #map_tools = await connect_mcp_tools()
    #prompt_client, prompt_tools = await connect_mcp_tools("http://localhost:8000/mcp")
    #all_tools = map_tools + prompt_tools
    #all_tools = map_tools
     #Error calling tool 'get_route': 'type' object does not support the asynchronous context manager protocol
    map_client = await connect_mcp_tools("http://localhost:8000/mcp"))
    #tools = await map_client.list_tools()
    #all_tools = []
    #for tool in tools:
    #    converted = convert_mcp_tool_to_langchain(tool)
        #langchain_tools.append(tool)
    #    all_tools.append(converted)

    #print(f"✅ 已加载 {len(all_tools)} 个工具")
    #model_with_tools = model.bind_tools(all_tools)
    #tool_node = ToolNode(all_tools)
    def convert_mcp_tool_to_langchain(mcp_tool: Any) -> StructuredTool:
        tool_name = mcp_tool.name
        tool_description = mcp_tool.description or f"Tool: {tool_name}"

        async def call_mcp_tool_with_cache(**kwargs):
            print(f"🔧 包装函数收到的参数: {kwargs}")
            if not kwargs:
                return "❌ 错误：没有传入任何参数。"
            cached_result = cache.get(tool_name, kwargs)
            if cached_result:
                return cached_result
            try:
                result = await map_client.call_tool(tool_name, arguments=kwargs)
                result_text = result.content[0].text if result.content else str(result)
                ttl = 3600 if tool_name == "get_route" else 1800
                cache.set(tool_name, kwargs, result_text, ttl)
                return result_text
            except Exception as e:
                return f"工具调用失败: {str(e)}"

        from pydantic import BaseModel, Field

        class RouteArgs(BaseModel):
            origin: str = Field(description="起点地名")
            destination: str = Field(description="终点地名")

        class NearbyArgs(BaseModel):
            location: str = Field(description="位置地名")
            keyword: str = Field(description="搜索关键词，如'美食'、'景点'")
            radius: int = Field(default=1000, description="搜索半径，单位米")

        class WeatherArgs(BaseModel):
            city: str = Field(description="城市名称，如'北京'、'上海'")
            extensions: str = Field(default="base", description="查询类型：'base'=实时天气，'all'=未来3天预报")

        print(f"tool name is: {tool_name}")
        if tool_name == "get_route":
            args_schema = RouteArgs
        elif tool_name == "search_nearby":
            args_schema = NearbyArgs
        elif tool_name == "get_weather":
            args_schema = WeatherArgs
        else:
            args_schema = None
        print(f"args schema is: {args_schema}")
        return StructuredTool.from_function(coroutine=call_mcp_tool_with_cache,
                                        name=tool_name, description=tool_description, args_schema=args_schema)
    tools = await map_client.list_tools()
    all_tools = []
    for tool in tools:
        converted = convert_mcp_tool_to_langchain(tool)
        #langchain_tools.append(tool)
        all_tools.append(converted)
    from knowledgeclass_service import create_retriever_tool
    from neo4j_tools import query_travel_knowledge, get_graph_schema
    all_tools.append(create_retriever_tool())
    all_tools.append(query_travel_knowledge)
    all_tools.append(get_graph_schema)
    print(f"✅ 已加载 {len(all_tools)} 个工具")
    model_with_tools = model.bind_tools(all_tools)
    #tool_node = ToolNode(all_tools)
    tool_node = ParallelToolNode(all_tools)
#graph_builder = StateGraph(MessageState)

    def call_model(state: MessagesState):
    #def call_model(state, memory: ConversationMemory, session_id: str):
        if "messages" not in state:
            print("⚠️ state 中没有 messages，初始化空列表")
            state["messages"] = []
        if not state["messages"]:
            print("⚠️ messages 为空，添加默认消息")
            return {"messages": [AIMessage(content="你好！我是旅游规划助手，请问有什么可以帮您
？")]}
        current_message = state["messages"][-1]
        #system_prompt = SystemMessage(content="""
        #你是一位资深的旅游规划师。你的职责是：
        #1. 根据用户的需求规划旅游路线
        #2. 推荐当地美食
        #3. 提供实用的旅行建议

        #当用户询问路线时，调用 get_route 工具。
        #当用户询问美食时，调用 search_nearby 工具。
        #""")
        system_prompt = """
        你是一个旅游规划助手，必须使用工具来获取路线信息。

        可用工具：
        - get_route: 获取驾车路线。
          必需参数：
          - origin: 起点地名（如"北京站"、"上海人民广场"）
          - destination: 终点地名（如"天安门"、"杭州西湖"）

        重要规则：
        1. 当用户询问路线时，必须从用户的问题中提取起点和终点。
        2. 例如：用户说"从北京站到天安门" → origin="北京站", destination="天安门"
        3. 如果用户只说了目的地没说起点，先提问"请问您从哪里出发？"
        4. 如果用户只说了起点没说起点，先提问"请问您要去哪里？"
        5. 绝对不要用空参数调用工具！

        示例：
        用户："从沈阳站到鞍山千山怎么走？"
        → 调用 get_route(origin="沈阳站", destination="鞍山千山")

        - search_nearby: 指定地点附近搜索餐厅或景点
          必需参数：
          - location: 地点名称（如"天安门"）
          - keyword: 搜索关键词（如"美食"、"景点"）
          radius: 搜索半径，单位米，默认是1000米

         重要规则：
          1.当用户询问"美食"、"景点"时, 必须从用户的问题中提取地点、美食或景点、1000米半径
          2. 例如：用户说"北京站周围有什么美食" → location="北京站", keyword="美食"

        示例：
        用户："北京站周围1000米内有什么美食？"
        → 调用 search_nearby(location="北京站", keyword="美食", radius=1000)

        - get_weather: 用户问天气/出行建议时用
          必需参数：
          - city: 城市名称（如"北京"、"上海"）
          - extensions: 'base'=实时，'all'=预报

        重要规则：
        1. 用户问天气时，必须从用户的问题中提取城市名称
        2. 例如：用户说"北京天气如何" → city="北京", extensions="all"
        3. 绝对不要用空参数调用工具！

        示例：
        用户："北京天气如何？"
        → 调用 get_weather(city="北京", extensions="all")
        """
        history = memory.get_formatted_history(session_id, limit=10)
        full_messages = [system_prompt]
        for role, content in history:
            if role == "user":
                #full_messages.append(("user", content))
                full_messages.append(HumanMessage(content=content))
            else:
                #full_messages.append(("assistant", content))
                full_messages.append(AIMessage(content=content))
        #current_message = state["messages"][-1]
        #full_messages.append(current_message)
        #messages = histroy + state["messages"]
            #print("🤔 智能体正在思考...")
        #response = model.invoke(state["messages"])
        if isinstance(current_message, tuple):
            role, content = current_message
            if role == "user":
                full_messages.append(HumanMessage(content=content))
            else:
                full_messages.append(AIMessage(content=content))
        else:
            full_messages.append(current_message)
        try:
            response = model_with_tools.invoke(full_messages)
            #response = model_with_tools.invoke(full_messages,
            #tool_choice={"type": "function", "function": {"name": "get_route"}})
            tool_calls_data = None
            if hasattr(response, 'tool_calls'):
                if callable(response.tool_calls):
                    try:
                        tool_calls_data = response.tool_calls()
                    except:
                        tool_calls_data = None
                else:
                    tool_calls_data = response.tool_calls
                if tool_calls_data:
                    try:
                        import json
                        json.dumps(tool_calls_data)
                    except (TypeError, json.JSONEncodeError):
                        tool_calls_data = str(tool_calls_data)
        except Exception as e:
            print(f"❌ 模型调用失败: {e}")
            return {"messages": [AIMessage(content=f"抱歉，我遇到了问题：{e}")]}
        #memory.add_message(session_id, "user": state["messages"][-1].content)
        #memory.add_message(session_id, "assistant", response.content)
        try:
            user_content = current_message.content if hasattr(current_message, 'content') else str(current_message)
            print(f"user_content is {user_content}")
            memory.add_message(session_id, "user", user_content)
            #Object of type method is not JSON serializable
            memory.add_message(session_id, "assistant", response.content, response.tool_calls if hasattr(response, 'tool_calls') else None)
            print(f"response---tool_calls_data is {response}---{tool_calls_data}")
            #print(f"response.content is {response.content}")
            #memory.add_message(session_id, "assistant", response.content, tool_calls_data)
        except Exception as e:
            print(f"⚠️ 保存记忆失败: {e}")
        return {"messages": [response]}

    def should_continue(state) -> Literal["tools", END]:
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            print(f"🔧 调用工具: {[tc['name'] for tc in last_message.tool_calls]}")
            return "tools"
        return END
#async def get_tools_node():
#    mcp_tools = await connect_mcp_tools()
#    tool_node = ToolNode(mcp_tools)
#    return tool_node
    graph_builder = StateGraph(MessagesState)
    graph_builder.add_node("agent", call_model)
    #graph_builder.add_node("tools", tool_node)
    graph_builder.add_node("tools", tool_node.ainvoke)
    graph_builder.add_edge(START, "agent")
    graph_builder.add_conditional_edges("agent", should_continue, ["tools", END])
    graph_builder.add_edge("tools", "agent")
    #with Neo4jSaver.from_conn_string(uri="bolt://192.168.66.88:7687", user="neo4j", password="your-password") as checkpointer:
    #with Neo4jSaver.from_conn_string("bolt://your-password@192.168.66.88:7687") as checkpointer:
    #    checkpointer.setup()
    app = graph_builder.compile(checkpointer=saver)#checkpoint)
    return app, map_client, session_id

async def stream_response(user_input: str):
    async for chunk in model.astream(user_input):
        if chunk.content:
            yield chunk.content
            print(chunk.content, end="", flush=True)

async def chat_with_streaming():
     print("\n🤖 智能体: ", end="", flush=True)
     async for chunk in stream_reponse(user_input):
         pass
     print())

def generate_travel_summary(route_info, food_info):
    return f"""
    你是一位资深的旅游规划师。请根据以下信息生成攻略：
    路线信息：{route_info}
    美食信息：{food_info}
    """

async def main():
    print("=" * 60)
    print("🎯 旅游规划智能体（流式输出）")
    print("=" * 60)
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("❌ 错误: 请设置 DEEPSEEK_API_KEY 环境变量")
        print("   export DEEPSEEK_API_KEY='your-key-here'")
        #return
    session_id = str(uuid.uuid4())
    print(f"📝 会话 ID: {session_id[:8]}...")
    cache_stats = cache.get_stats()
    print(f"💾 缓存状态: {'启用' if cache.enabled else '禁用'} | 命中率: {cache_stats['hit_rate']}")
    print(f"🧠 记忆状态: Redis 启用 | 会话过期: 1小时")
    print("-" * 60)
    if not os.environ.get("AMAP_KEY"):
        print("⚠️  警告: 未设置 AMAP_KEY，地图功能将不可用")
    map_client = None
    try:
        #agent = await create_agent()
        agent, map_client, session_id = await create_agent(session_id)
        print("✅ 智能体已就绪！")
        print("=" * 60)
        print("\n💬 进入对话模式")
        print("   - 输入 'quit' 退出")
        print("   - 输入 'clear' 清空当前对话记忆")
        print("   - 输入 'stats' 查看缓存统计")
        print("-" * 60)
        while True:
            user_input = input("\n👤 你: ").strip()
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("👋 再见！")
                break
            elif user_input.lower() == 'clear':
                memory.clear_session(session_id)
                print("🗑️  对话记忆已清空")
                continue
            elif user_input.lower() == 'stats':
                stats = cache.get_stats()
                session_info = memory.get_session_info(session_id)
                print(f"\n📊 缓存统计: {stats}")
                print(f"📊 会话统计: {session_info}")
                continue
            elif not user_input:
                continue
            print("\n🤖 智能体: ", end="", flush=True)

            full_response = ""
            pending_tools = set()
            completed_tools = set()
            tool_calls_made = []
            config = {"configurable": {"thread_id": session_id}}
            async for event in agent.astream_events({"messages": [("user", user_input)]},
                                                    config=config, version="v2"):
            #for event in agent.stream({"messages": [("user", user_input)]},config=config,):
                event_type = event.get("event", "")
                if event_type == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        content = chunk.content
                        print(content, end="", flush=True)
                        full_response += content
                elif event_type == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    tool_input = event["data"].get("input", {})
                    pending_tools.add(tool_name)
                    print(f"\n⚡ 启动: {tool_name}", end="", flush=True)
                    print(f"\n🔧 正在调用工具: {tool_name}")
                    print(f"📦 参数: {tool_input}")
                    tool_calls_made.append(tool_name)
                elif event_type == "on_tool_end":
                    tool_name = event.get("name", "unkonown")
                    completed_tools.add(tool_name)
                    print(f"\n✅ 完成: {tool_name}", end="", flush=True)
                    output = event["data"].get("output", "")
                    output_preview = str(output)[:200] + "..." if len(str(output)) > 200 else str(output)
                    print(f"✅ 工具 {tool_name} 调用完成")
                    print(f"📊 结果预览: {output_preview}")
                elif event_type == "on_tool_error":
                    tool_name = event.get("name", "unknown")
                    error = event["data"].get("error", "未知错误")
                    print(f"\n❌ 工具 {tool_name} 调用失败: {error}")
            if pending_tools:
                print(f"\n📊 并行执行摘要: {len(pending_tools)} 个工具")
                print(f"   ✅ 已完成: {', '.join(completed_tools)}")
                print(f"   ⏱️   总耗时: 约 {len(pending_tools)} 倍速度提升")
            if not full_response:
                print()
            print()
            #response = await agent.ainvoke({"messages": [("user", user_input)]})
            #last_message = response["messages"][-1]
            #print(last_message.content)
    except KeyboardInterrupt:
        print("\n\n👋 用户中断，再见！")
    except Exception as e:
        print(f"❌ 错误: {e}")
        print("\n💡 请确保:")
        import traceback
        traceback.print_exc()
        #print("   1. 地图服务已启动: uv run python amap_server.py")
        #print("   2. 提示词服务已启动: uv run python prompt_server.py")
        #print("   3. 两个服务都在正确的端口运行")
    finally:
        if map_client:
            await map_client.__aexit__(None, None, None)
        await saver.close()
        #if prompt_client:
        #    await prompt_client.__aexit__(None, None, None)

def save_redis_data():
    try:
        import redis
        r = redis.from_url("redis://localhost:6379")
        r.save()
        print("💾 Redis 数据已手动保存")
    except Exception as e:
        print(f"⚠️ 保存失败: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        save_redis_data()
        #saver.close()
