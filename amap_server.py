from fastmcp import FastMCP
import httpx
import os

mcp = FastMCP("Amap Navigator 🗺️ ")
AMAP_API_URL = "https://restapi.amap.com/v5"
GEOCODE_API_URL = "https://restapi.amap.com/v3/geocode/geo"
WEATHER_API_URL = "https://restapi.amap.com/v3/weather/weatherInfo"

_geocode_cache = {}

async def geocode(address: str, client: httpx.AsyncClient):
    key = os.environ.get("AMAP_KEY")
    resp = await client.get(GEOCODE_API_URL, params={"key": key, "address": address, "output": "json"})
    data = resp.json()
    print(f"📍 地理编码 [{address}]: {data}")
    if data.get("status") == "1" and data.get("geocodes"):
        location = data["geocodes"][0]["location"]
        return location
    return None

async def geocode_with_cache(address: str, client: httpx.AsyncClient) -> str:
    if address in _geocode_cache:
        print(f"📦 缓存命中: {address}")
        return _geocode_cache[address]
    location = await geocode(address, client)
    if location:
        _geocode_cache[address] = location
    return location

@mcp.tool()
async def get_route(origin: str, destination: str) -> dict:
    """
    获取两个地点之间的驾车路线规划。

    使用场景：用户询问从A地到B地的路线、距离或时间。

    Args:
        origin: 起点地名，必须是一个具体的地点名称（如"北京站"、"上海人民广场"）
        destination: 终点地名，必须是一个具体的地点名称（如"天安门"、"杭州西湖"）

    Returns:
        包含距离（米）、时间（秒）和分段路线信息的字典
    """
    key = os.environ.get("AMAP_KEY")
    async with httpx.AsyncClient(timeout=30.0) as client:
        '''
        async def geocode(address: str):
            resp = await client.get(GEOCODE_API_URL, params={"key": key, "address": address, "output": "json"})
            data = resp.json()
            print(f"📍 地理编码 [{address}]: {data}")
            if data.get("status") == "1" and data.get("geocodes"):
                location = data["geocodes"][0]["location"]
                return location
            return None

        async def geocode_with_cache(address: str) -> str:
            if address in _geocode_cache:
                print(f"📦 缓存命中: {address}")
                return _geocode_cache[address]
        location = await geocode(address)
        if location:
            _geocode_cache[address] = location
        return location
        '''
        #origin_loc = await geocode(origin)
        #destination_loc = await geocode(destination)
        origin_loc = await geocode_with_cache(origin, client)
        destination_loc = await geocode_with_cache(destination, client)
        if not origin_loc or not destination_loc:
            return {"error": "无法解析地点名称，请检查地名是否正确"}

        response = await client.get(f"{AMAP_API_URL}/direction/driving", params={
            "key": key, "origin": origin_loc, "destination": destination_loc, "extensions": "all"})
        print(f"amap response is {response}")
        data = response.json()
        print(f"map data is {data}")
        if data.get("status") == "1":
            route = data["route"]
            path = route["paths"][0] if route.get("paths") else None
            if path:
                return {"origin": origin, "destination": destination, "distance": path.get("distance","未知"), "duration": path.get("duration", "未知"), "steps": path.get("steps", [])}
            return {"error": "未找到有效路线"}
        else:
            return {"error": f"路线规划失败: {data.get('info', '未知错误')}"}

@mcp.tool()
async def search_nearby(location: str, keyword: str = "美食", radius: int = 1000) -> list:
    """
    在指定坐标附近搜索餐厅或景点

    使用场景：用户询问指定地点附近的餐厅和景点。

    Args:
    location: 地点名称（如"天安门"）
    keyword: 搜索关键词（如"美食"、"景点"）
    radius: 搜索半径，单位米，默认1000

    Returns:
        指定地点附近的餐厅或景点
    """
     key = os.environ.get("AMAP_KEY")
    async with httpx.AsyncClient(timeout=30.0) as client:
        '''
        resp = await client.get(GEOCODE_API_URL, params={"key": key, "address": location,"output": "json"})
        geo_data = resp.json()
        print(f"📍 地理编码 [{location}]: {geo_data}")
        if geo_data.get("status") != 1 or not geo_data.get("geocodes"):
            return [{"error": f"无法解析地点: {location}"}]
        location_coord = geo_data["geocodes"][0]["location"]
        '''
        location_coord = await geocode_with_cache(location, client)
        response = await client.get(f"{AMAP_API_URL}/place/around",params={
            "key": key, "location": location_coord, "keyword": keyword, "radius": radius, "offset": 5, "extensions": "all"})
        data = response.json()
        print(f"🔍 搜索响应: {data}")
        if data.get("status") == "1":
            pois = data.get("pois", [])
        return [{"name": p.get("name", "未知"), "address": p.get("address", "暂无地址"),"distance": p.get("distance", "未知"), "type": p.get("type", "未知")} for p in pois[:5]]
    return [{"error": f"搜索失败: {data.get('info', '未知错误')}"}]

@mcp.tool()
async def get_weather(city: str, extensions: str = "base") -> dict:
    """
    查询指定城市的实时天气或天气预报。

    使用场景：
    - 用户询问某城市的天气
    - 旅行规划时推荐出行时间
    - 用户问"适合旅游吗"、"天气怎么样"

    Args:
        city: 城市名称（如"北京"、"上海"）
        extensions: 返回类型，'base'=实时天气，'all'=未来3天预报

    Returns:
        包含天气信息、温度、风力的字典
    """
    key = os.environ.get("AMAP_KEY")
    if not key:
        return {"error": "请设置 AMAP_KEY 环境变量"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"city: {city}")
        geocode = await geocode_with_cache(city, client)
        print(f"geocode: {geocode}")
        weather_resp = await client.get(WEATHER_API_URL,
                                        params={"key": key, "city": geocode,
                                                "extensions": extensions, "output": "json"})
        weather_data = weather_resp.json()
        print(f"🌤️  天气响应: {weather_data}")
        if weather_data.get("status") != "1":
            return {"error":  f"天气查询失败: {weather_data.get('info', '未知错误')}"}
        if extensions == "base":
            info = weather_data["lives"][0] if weather_data.get("lives") else None
            if info:
                return {"city": info.get("city"), "weather": info.get("temperature"),
                    "wind_direction": info.get("winddirection"), "wind_power": info.get("windpower"),
                    "humidity": info.get("humidity"), "update_time": info.get("reporttime")}
            else:
                info = weather_data["forecasts"][0] if weather_data.get("forecasts") else None
                if info:
                    return {"city": info.get("city"), "forecast": info.get("casts", []),
                            "update_time": info.get("reporttime")}
        return {"error": "未找到天气信息"}

if __name__ == "__main__":
    import sys
    print("🚀 高德地图 MCP 服务正在启动...", flush=True)
    print("📍 监听地址: http://localhost:8000/mcp", flush=True)
    print("⌨️  按 Ctrl+C 停止服务", flush=True)
    key = os.environ.get("AMAP_KEY")
    if key:
        print("map key exported")
    else:
         print("no map key")
    mcp.run(transport="http", host="127.0.0.1", port=8000)
