"""Neo4j connection manager with async support."""

from __future__ import annotations

import os
import logging
from contextlib import asynccontextmanager
from typing import Any

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession

logger = logging.getLogger(__name__)


class Neo4jManager:
    """Manages Neo4j driver lifecycle and provides query execution."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ):
        self.uri = uri or os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        self.user = user or os.environ.get("NEO4J_USER", "neo4j")
        self.password = password or os.environ.get("NEO4J_PASSWORD", "")
        self.database = database or os.environ.get("NEO4J_DATABASE", "neo4j")
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        """Initialize the async driver."""
        if self._driver is None:
            self._driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
            )
            # Verify connectivity
            await self._driver.verify_connectivity()
            logger.info("Connected to Neo4j at %s", self.uri)

    async def close(self) -> None:
        """Close the driver."""
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("Neo4j connection closed")

    @asynccontextmanager
    async def session(self) -> Any:
        """Yield an async Neo4j session."""
        if self._driver is None:
            await self.connect()
        assert self._driver is not None
        async with self._driver.session(database=self.database) as sess:
            yield sess

    async def execute(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a Cypher query and return records as dicts."""
        async with self.session() as sess:
            result = await sess.run(query, parameters or {})
            records = await result.data()
            await result.consume()
            return records

    async def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a write transaction."""
        async def _run(tx: Any) -> list[dict[str, Any]]:
            result = await tx.run(query, parameters or {})
            records = await result.data()
            await result.consume()
            return records

        async with self.session() as sess:
            return await sess.execute_write(_run)

    async def get_schema_info(self) -> dict[str, Any]:
        """Introspect the database schema: labels, rel types, indexes."""
        labels = await self.execute("CALL db.labels()")
        rel_types = await self.execute("CALL db.relationshipTypes()")
        indexes = await self.execute("SHOW INDEXES")
        constraints = await self.execute("SHOW CONSTRAINTS")

        return {
            "labels": [r["label"] for r in labels],
            "relationship_types": [r["relationshipType"] for r in rel_types],
            "indexes": [
                {
                    "name": r.get("name"),
                    "type": r.get("type"),
                    "labelsOrTypes": r.get("labelsOrTypes", []),
                    "properties": r.get("properties", []),
                }
                for r in indexes
            ],
            "constraints": [
                {
                    "name": r.get("name"),
                    "type": r.get("type"),
                    "entityType": r.get("entityType"),
                    "labelsOrTypes": r.get("labelsOrTypes", []),
                    "properties": r.get("properties", []),
                }
                for r in constraints
            ],
        }