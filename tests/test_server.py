"""Tests for neo4j_mcp server tools."""

import json
import pytest

# These tests require a running Neo4j instance.
# Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD env vars to run integration tests.
# Without them, tests are skipped.

pytestmark = pytest.mark.skip(reason="Integration tests — need Neo4j running")


@pytest.fixture
async def manager():
    from neo4j_mcp.db import Neo4jManager

    mgr = Neo4jManager()
    await mgr.connect()
    yield mgr
    await mgr.close()


@pytest.mark.asyncio
async def test_insert_and_search(manager):
    from neo4j_mcp.server import neo4j_insert, neo4j_search, neo4j_delete

    # Clean up
    result = await neo4j_delete(label="TestNode", match_properties={"test_id": "mcp-test-1"}, detach=True)

    # Insert
    result = json.loads(
        await neo4j_insert(label="TestNode", properties={"test_id": "mcp-test-1", "name": "MCP Test"})
    )
    assert "created" in result

    # Search
    result = json.loads(
        await neo4j_search(label="TestNode", properties={"test_id": "mcp-test-1"})
    )
    assert len(result) > 0

    # Cleanup
    await neo4j_delete(label="TestNode", match_properties={"test_id": "mcp-test-1"}, detach=True)


@pytest.mark.asyncio
async def test_schema(manager):
    from neo4j_mcp.server import neo4j_schema

    result = json.loads(await neo4j_schema())
    assert "labels" in result
    assert isinstance(result["labels"], list)