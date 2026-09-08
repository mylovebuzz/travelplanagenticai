from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import asyncio
import json
from typing import Any, Dict, Optional, Sequence, Tuple, Iterator, AsyncIterator
from langgraph.checkpoint.base import (BaseCheckpointSaver, Checkpoint, CheckpointMetadata,
                                       CheckpointTuple, SerializerProtocol,)
#from langgraph.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from neo4j import AsyncGraphDatabase, AsyncSession
from neo4j import GraphDatabase, Driver, Session

CN_TZ = timezone(timedelta(hours=8))

class AsyncNeo4jSaver(BaseCheckpointSaver):
    """
    基于 Neo4j 的异步检查点保存器。
    注意：由于 neo4j 驱动主要是同步的，这里使用 asyncio.to_thread 来避免阻塞事件循环。
    """
    def __init__(self, url: str, username: str, password: str, database: str = "neo4j",
                 serde: Optional[SerializerProtocol] = None,):
        #super().__init__(serde=serde)
        super().__init__()
        self.url = url
        self.username = username
        self.password = password
        self.database = database
        self.serde: SerializerProtocol = JsonPlusSerializer()
        #self.driver: Driver = GraphDatabase.driver(url, auth=(username, password))
        self.driver: Driver = GraphDatabase.driver(url, auth=(username, password))

    async def close(self):
        await asyncio.to_thread(self.driver.close)

    def _get_session(self) -> AsyncSession:
        return self.driver.session(database=self.database)

    async def aput(self, config: dict, checkpoint: Checkpoint, metadata: CheckpointMetadata, new_versions: dict,) -> dict:
    #async def aput_writes(self, config: dict, writes: Sequence[Tuple[str, Any]], task_id: str, new_versions: dict,) -> None:
        print(f"aput...config: {config}; checkpoint: {checkpoint}; metadata {metadata}; new_versions {new_versions}")
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        parent_id = checkpoint.get("parent_checkpoint_id")
        #checkpoint_data = self.serde.dumps_typed(checkpoint)
        #metadata_data = self.serde.dumps_typed(metadata)
        checkpoint_json = json.dumps(checkpoint, default=str, ensure_ascii=False)
        metadata_json = json.dumps(metadata, default=str, ensure_ascii=False)
        #cn_tz = ZoneInfo("Asia/Shanghai")
        current_timestamp = datetime.now(CN_TZ).isoformat()
        def _sync_put():
            with self._get_session() as session:
                query = """
                MERGE (c:Checkpoint {thread_id: $thread_id, checkpoint_ns: $checkpoint_ns,
                                     id: $checkpoint_id})
                SET c.checkpoint = $checkpoint_json, c.metadata = $metadata_json,
                    c.parent_checkpoint_id = $parent_id, c.timestamp = $timestamp"""
                #parent_checkpoint_id= checkpoint.get("parent_checkpoint_id")
                session.run(query, thread_id=thread_id, checkpoint_ns=checkpoint_ns,
                            checkpoint_id=checkpoint_id, checkpoint_json=checkpoint_json,#checkpoint_data=checkpoint_data,
                            metadata_json=metadata_json, parent_id=parent_id,
                            #metadata_data=metadata_data, parent_id=parent_id,
                            timestamp=current_timestamp)
        await asyncio.to_thread(_sync_put)
        return {"configurable": {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns,
                                 "checkpoint_id": checkpoint_id}}

    #async def aget(self, config: dict) -> Optional[CheckpointTuple]:
    async def aget_tuple(self, config: dict) -> Optional[CheckpointTuple]:
        print(f"aget_tuple...config: {config}")
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        #checkpoint_id = config["configurable"].get("checkpoint_id")

        def _sync_get_ng() -> Optional[CheckpointTuple]:
            with self._get_session() as session:
                if checkpoint_id:
                    query = """
                    MATCH (c: Checkpoint {thread_id: $thread_id,
                                          checkpoint_ns: $checkpoint_ns,id: $checkpoint_id})
                    RETURN c.checkpoint as checkpoint, c.metadata as metadata,
                           c.parent_checkpoint_id as parent_id, c.id as id, c.timestamp as timestamp"""
                    result = session.run(query, thread_id=thread_id,
                                                     checkpoint_ns=checkpoint_ns,
                                                     checkpoint_id=checkpoint_id)#.single()
                else:
                    query = """
                    MATCH (c: Checkpoint {thread_id: $thread_id, checkpoint_ns: $checkpoint_ns})
                    ORDER BY CASE WHEN c.timestamp IS NOT NULL THEN c.timestamp
                                 ELSE '0000-00-00T00:00:00' END DESC
                    LIMIT 1
                    RETURN c.checkpoint as checkpoint, c.metadata as metadata,
                           c.parent_checkpoint_id as parent_id, c.id as id, c.timestamp as timestamp"""
                    result = session.run(query, thread_id=thread_id,
                                         checkpoint_ns=checkpoint_ns)#.single()
                record = result.single()
                if not record:
                    return None
                checkpoint = self.serde.loads_typed(record["checkpoint"])
                metadata = self.serde.loads_typed(record["metadata"]) if record["metadata"] else {}
                #parent_config = None
                #if result.get("parent_checkpoint_id"):
                #    parent_config = {configurable: {"thread_id": thread_id,
                #                                            "checkpoint_ns": checkpoint_ns,
                #                                            "checkepoint_id": result["parent_checkpoint_id"],}}
                #    current_id = result.get("id") or checkpoint_id
                return CheckpointTuple(config={"configurable": {"thread_id": thread_id,
                                           "checkpoint_ns": checkpoint_ns,
                                           "checkpoint_id": record[id]}},
                                           checkpoint=checkpoint, metadata=metadata,
                                       parent_config={"configurable": {
                                           "thread_id": thread_id,
                                           "checkpoint_ns": checkpoint_ns,
                                           "checkpoint_id": record["parent_checkpoint_id"]}
                                        } if record["parent_checkpoint_id"] else None,)
        def _sync_get():
            with self._get_session() as session:
                query = """MATCH(c:Checkpoint {thread_id: $thread_id, checkpoint_ns: $checkpoint_ns})
                RETURN c.checkpoint AS checkpoint_json, c.metadata AS metadata_json,
                       c.parent_checkpoint_id AS parent_id, c.timestamp AS timestamp
                ORDER BY c.timestamp DESC LIMIT 1"""
                result = session.run(query, thread_id=thread_id, checkpoint_ns=checkpoint_ns)
                record = result.single()
                if not record:
                    return None
                checkpoint = json.loads(record["checkpoint_json"])
                metadata = json.loads(record["metadata_json"])
                parent_id = record.get("parent_checkpoint_id")
                return CheckpointTuple(config=config, checkpoint=checkpoint,
                           metadata=metadata, parent_config={"configurable": {
                           "thread_id": thread_id, "checkpoint_ns": checkpoint_ns,
                           "checkpoint_id": parent_id}} if parent_id else None,)
        return await asyncio.to_thread(_sync_get)

    async def aput_writes(self, config: dict, writes: Sequence[Tuple[str, Any]], task_id: str,
                          new_versions: dict = None,) -> None:
        if new_versions is None:
            new_versions = {}
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns =  config["configurable"].get("checkpoint_ns", "")
        checkpoint_id =  config["configurable"]["checkpoint_id"]
        current_timestamp = datetime.now(CN_TZ).isoformat()

        def _sync_put_writes():
            with self._get_session() as session:
                for idx, (key, value) in enumerate(writes):
                    value_json = json.dumps(value, default=str, ensure_ascii=False)
                    query="""CREATE (w: Write {thread_id: $thread_id,
                        checkpoint_ns: $checkpoint_ns, checkpoint_id: $checkpoint_id,
                        task_id: $task_id, idx: $idx, key: $key, value: $value_json,
                        timestamp: $timestamp})"""
                    session.run(query, thread_id=thread_id, checkpoint_ns=checkpoint_ns,
                                checkpoint_id=checkpoint_id, task_id=task_id, idx=idx,
                                key=key, value_json=value_json, timestamp=current_timestamp,)
        await asyncio.to_thread(_sync_put_writes)

    async def alist(self, config: dict, limit: int = 10, before: Optional[dict] = None) -> AsyncIterator[CheckpointTuple]:#Sequence[CheckpointTuple]:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")

        #def _sync_list() -> Sequence[CheckpointTuple]:
        def _sync_list():
            with self._get_session() as session:
                #where_clause = "c.thread_id = $thread_id AND c.checkpoint_ns = $checkpoint_ns"
                #params = {"thread_id": thread_id, "checkpoint_ns": checkpoint_ns, "limit": limit,}
                query = """MATCH(c:Checkpoint {thread_id: $thread_id,
                                               checkpoint_ns: $checkpoint_ns})"""
                if before:
                    before_id = before["configurable"]["checkpoint_id"]
                    query += " WHERE c.id < $before_id"
                    #where_clause += "AND c.id < $before_id"
                    params["before_id"] = before_id
                #query = f"""MATCH (c: Checkpoint) WHERE {where_clause}
                query += " ORDER BY c.timestamp DESC LIMIT $limit"
                query += """RETURN c.id as id, c.checkpoint as checkpoint,
                    c.metadata as metadata, c.parent_checkpoint_id as parent_id"""
                results = session.run(query, **params)
                #tuples = []
                for record in results:
                    checkpoint = self.serde.loads_typed(record["checkpoint"])
                    metadata = self.serde.loads_typed(record["metadata"]) if record["metadata"] else {}
                    yield CheckpointTuple(config={"configurable": {"thread_id": thread_id,
                              "checkpoint_ns": checkpoint_ns, checkpoint_id: record["id"]}},
                              checkpoint=checkpoint, metadata=metadata, parent_config={
                              "configurable": {"thread_id": thread_id,
                              "checkpoint_ns": checkpoint_ns,
                              "checkpoint_id": record["parent_checkpoint_id"]}} if record["parent_checkpoint_id"] else None,)
                    #parent_config = None
                    #if record.get("parent_checkpoint_id"):
                    #    parent_config = {configurable: {"thread_id": thread_id,
                    #                        "checkpoint_ns": checkpoint_ns,
                    #                        "parent_checkpoint_id": result["parent_checkpoint_id"],}}
                    #tuples.append(CheckpointTuple(config={"configurable": {"thread_id": thread_id,
                    #                                             "checkpoint_ns": "checkpoint_ns",
                    #                                                       "checkpoint_id": record["id"],}},
                    #                               checkpoint=checkpoint, metadata=metadata,
                    #                               parent_config=parent_config,))
                #return tuples
        #return await asyncio.to_thread(_sync_list)
        items = await asyncio.to_thread(lambda: list(_sync_list()))
        for item in items:
            yield item

    async def adelete(self, config: dict) -> None:
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"].get("checkpoint_id")

        def _sync_delete():
            with self._get_session() as session:
                if checkpoint_id::
                    query = """
                    MATCH (c: Checkpoint {thread_id: $thread_id,
                                          checkpoint_ns: $checkpoint_ns,id: $checkpoint_id})
                    DETACH DELETE c"""
                    session.run(query, thread_id=thread_id,
                        checkpoint_ns=checkpoint_ns, checkpoint_id=checkpoint_id,)
                else:
                    query = """
                    MATCH (c: Checkpoint {thread_id: $thread_id, checkpoint_ns: $checkpoint_ns})
                    DETACH DELETE c """
                    session.run(query, thread_id=thread_id, checkpoint_ns=checkpoint_ns,)
        return await asyncio.to_thread(_sync_delete)

    #def close(self):
    #    if self.driver:
    #        self.driver.close()
