import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
#os.environ["HUGGINGFACE_HUB_ENDPOINT"] = "https://hf-mirror.com"

from typing import List, Optional
from pymilvus import MilvusClient, DataType, CollectionSchema, FieldSchema, model
from langchain_milvus import Milvus as LangChainMilvus
#from langchain.tools import create_retriever_tool
from langchain_core.tools import BaseTool, create_retriever_tool
from sentence_transformers import SentenceTransformer

#os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
#os.environ["HUGGINGFACE_HUB_ENDPOINT"] = "https://hf-mirror.com"
MILVUS_DB_PATH = "http://192.168.66.88:19530"
COLLECTION_NAME = "travel_knowledge"
EMBEDDING_DIM = 768

_embedding_fn = None
_client = None
_vector_store = None

class CustomEmbeddingFunction:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self.dim = 384
        #self.dim = EMBEDDING_DIM

    def encode_documents(self, texts: List[str]) -> List[List[float]]:
        return self.model.encode(texts, convert_to_numpy=True).tolist()

    def encode_queries(self, queries: List[str]) -> List[List[float]]:
        return self.model.encode(queries, convert_to_numpy=True).tolist()

def get_embedding_function():
    global _embedding_fn
    if _embedding_fn is None:
        print("📥 加载嵌入模型...")
        #_embedding_fn = model.DefaultEmbeddingFunction()
        _embedding_fn = CustomEmbeddingFunction()
        print("✅ 嵌入模型加载完成")
    return _embedding_fn

def get_milvus_client():
    global _client
    if _client is None:
        print("🔌 连接 Milvus 数据库...")
        #_client = MilvusClient(MILVUS_DB_PATH)
        _client = MilvusClient(uri=f"{MILVUS_DB_PATH}")
        print(f"✅ Milvus 连接成功: {MILVUS_DB_PATH}")
    return _client

def index_travel_data(docs: Optional[List[str]] = None):
    if docs is None:
        docs = get_default_travel_guides()
    print(f"📚 准备索引 {len(docs)} 条旅游攻略...")
    #client = get_milvus_client()
    get_milvus_client()
    embedding_fn = get_embedding_function()
    if _client.has_collection(COLLECTION_NAME):
        print(f"🔄 删除已存在的 Collection: {COLLECTION_NAME}")
        _client.drop_collection(COLLECTION_NAME)
    test_vector = embedding_fn.encode_documents(["测试"])[0]
    actual_dim = len(test_vector)
    print(f"📊 实际向量维度: {actual_dim}")
    fields = [FieldSchema(name="id", dtype=DataType.INT64, is_primary=True),
              FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=actual_dim),
              FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
              FieldSchema(name="topic", dtype=DataType.VARCHAR, max_length=255),
              FieldSchema(name="city", dtype=DataType.VARCHAR, max_length=255),]
    schema = CollectionSchema(fields, description="旅游攻略知识库")
    print(f"📦 创建 Collection: {COLLECTION_NAME}")
    _client.create_collection(collection_name=COLLECTION_NAME, schema=schema)#dimension=EMBEDDING_DIM, auto_id=False,
                             #schema={"fields": [
                             #    {"name": "id", "type": "INT64", "is_primary": True},
                             #    {"name": "vector", "type": "FLOAT_VECTOR", "dim": EMBEDDING_DIM},
                             #    {"name": "text", "type": "VARCHAR", "max_length": 65535},
                             #    {"name": "topic", "type": "VARCHAR", "max_length": 255},
                             #    {"name": "city", "type": "VARCHAR", "max_length": 255},]})
    print(f"✅ Collection 创建成功: {COLLECTION_NAME}")
    vectors = embedding_fn.encode_documents(docs)
    data = [{"id": i, "vector": vectors[i], "text": docs[i], "topic": "travel_guide",
             "city": extract_city(docs[i])} for i in range(len(docs))]
    _client.insert(collection_name=COLLECTION_NAME, data=data)

def get_default_travel_guides() -> List[str]:
    return [
        # 北京
        "北京故宫是中国明清两代的皇家宫殿，旧称紫禁城，位于北京中轴线的中心。",
        "北京长城是世界上最长的城墙，主要建于明朝，是中国的象征之一。",
        "北京天坛是明清两代皇帝祭天的场所，以祈年殿和回音壁闻名。",

        # 杭州
        "杭州西湖以其秀丽的湖光山色和众多名胜古迹闻名中外，有断桥残雪、雷峰塔等景点。",
        "杭州灵隐寺是著名的佛教寺院，始建于东晋，是江南佛教圣地。",
        "杭州千岛湖是世界上岛屿最多的湖，因湖中1078个岛屿而得名。",

        # 成都
        "成都大熊猫繁育研究基地是全球最大的大熊猫科研繁育机构，可以近距离观察大熊猫。",
        "成都宽窄巷子是成都遗留下来的较成规模的清朝古街道，是成都的文化地标。",
        "成都都江堰是古代水利工程，由李冰父子修建，至今仍在使用。",

        # 西安
        "西安兵马俑是秦始皇陵的陪葬坑，被誉为世界第八大奇迹。",
        "西安大雁塔是唐代建筑，用于存放玄奘法师从印度带回来的经书。",
        "西安城墙是中国现存最完整的古代城墙，全长约14公里。",

        # 上海
        "上海外滩是上海的标志性景点，有万国建筑博览群，对岸是浦东陆家嘴金融区。",
        "上海迪士尼乐园是中国大陆第一个迪士尼主题乐园，有7个主题园区。",
        "上海豫园是明代古典园林，位于上海老城厢，被誉为城市山林。",

        # 丽江
        "丽江古城是世界文化遗产，以纳西族文化和古建筑群闻名。",
        "丽江玉龙雪山是北半球最南的雪山，以雪山、冰川和高山草甸景观著称。",
        "丽江泸沽湖是高原淡水湖，以摩梭人的走婚习俗和自然风光闻名。"]

def extract_city(text: str) -> str:
    cities = ["北京", "上海", "杭州", "成都", "西安", "丽江", "南京", "苏州", "桂林", "厦门"]
    for city in cities:
        if city in text:
            return city
    return "其他"

def get_vector_store():
    global _vector_store
    if _vector_store is None:
        from pymilvus import connections
        connections.connect(alias="default", uri=MILVUS_DB_PATH)
        print("✅ Milvus 连接已建立")
        embedding_fn = get_embedding_function()
        _vector_store = LangChainMilvus(embedding_function=embedding_fn,
        #from langchain_milvus import Milvus
        #_vector_store = Milvus(embedding_function=embedding_fn,
                                        connection_args={"uri": MILVUS_DB_PATH},
                                        collection_name=COLLECTION_NAME, auto_id=False,
                                        consistency_level="Strong")
        print("✅ VectorStore 初始化完成")
    return _vector_store

def get_retriever_tool():
    from pymilvus import MilvusClient
    #client = MilvusClient(MILVUS_DB_PATH)
    #client = MilvusClient(f"uri= {MILVUS_DB_PATH}")
    vector_field_name = "vector"
    index_params = _client.prepare_index_params()
    index_params.add_index(field_name=vector_field_name, index_type="IVF_FLAT", metric_type="L2", params={"nlist": 128})
    _client.create_index(collection_name=COLLECTION_NAME, index_params=index_params)
    print(f"集合 {COLLECTION_NAME} 的索引创建成功")
    if _client.has_collection(COLLECTION_NAME):
        _client.load_collection(collection_name=COLLECTION_NAME, timeout=60)
        print(f"集合 {COLLECTION_NAME} 已加载到内存")
    else:
        print(f"集合 {COLLECTION_NAME} 不存在，请先创建")
        return

    def search_knowledge(query: str, k: int = 3) -> List[str]:
        embedding_fn = get_embedding_function()
        query_vector = embedding_fn.encode_queries([query])[0]
        results = _client.search(collection_name=COLLECTION_NAME, data=[query_vector],
                                limit=k, output_fields=["text", "city"])
        docs = []
        for hits in results:
            for hit in hits:
                docs.append(hit.get("entity", {}).get("text", ""))
        return docs

    from langchain_core.tools import tool
    @tool
    def search_travel_guides(query: str) -> str:
        """搜索旅游知识库，查找相关的景点、美食或攻略信息。"""
        print(f"🔧 工具被调用: search_travel_guides(query='{query}')")
        results = search_knowledge(query)
        if not results:
            return "未找到相关信息。"
        return "\n\n".join(results)
    return search_travel_guides

def get_knowledge_retriever_tool() -> BaseTool:
    vector_store = get_vector_store()
    retriever = vector_store.as_retriver(search_kwargs={"k": 3})
    tool = create_retriever_tool(retriever, "search_travel_guides",
        """搜索旅游知识库，根据用户的问题查找相关的旅游景点、历史文化、
        美食推荐或旅行攻略信息。

        使用场景：
        - 用户问"XX景点有什么历史故事"
        - 用户问"XX城市有什么值得去的景点"
        - 用户问"XX有什么特色美食"
        - 用户问"XX有什么好玩的推荐"
        """,)
    print("✅ 知识检索工具创建完成")
    return tool

def init_knowledge_service(force_reindex: bool = False):
    #client = get_milvus_client()
    get_milvus_client()
    if force_reindex or not client.has_collection(COLLECTION_NAME):
        print("📚 未找到知识库数据，开始索引...")
        index_travel_data()
    else:
        stats = _client.get_collection_stats(COLLECTION_NAME)
        if stats.get("row_count", 0) == 0:
            print("📚 知识库为空，开始索引...")
            index_travel_data()
        else:
            print(f"✅ 知识库已就绪，共 {stats.get('row_count', 0)} 条数据")

if __name__ == "__main__":
    print("=" * 50)
    print("🗄️   旅游攻略知识索引工具")
    print("=" * 50)
    init_knowledge_service(force_reindex=True)
    print("\n✅ 知识索引完成！")
    print(f"📁 数据文件: {MILVUS_DB_PATH}")
    print("\n🧪 测试检索:")
    #tool = get_knowledge_retriever_tool()
    tool = get_retriever_tool()
    print("✅ 检索工具创建成功")
    #test_query = "北京故宫有哪些历史故事"
    test_query = "上海有什么好玩的，好吃的"
    print(f"\n👤 用户查询: {test_query}")
    #result = tool.invoke({"query": "故宫有什么历史故事"})
    result = tool.invoke({"query": test_query})
    print(f"检索结果: {result}")
