"""MCP server exposing Neo4j operations as tools for LLMs."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .db import Neo4jManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EMBEDDING_KEYS = {"embedding"}


def _strip_embeddings(records: list[dict[str, Any]]) -> None:
    """Remove large embedding arrays from node dicts in-place."""
    for record in records:
        for key in _EMBEDDING_KEYS:
            if key in record and isinstance(record[key], list):
                record[key] = f"[{len(record[key])} floats]"

# ---------------------------------------------------------------------------
# MCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "neo4j-mcp",
    instructions=(
        "Neo4j MCP server. Use the provided tools to search, create, update, "
        "and delete graph data. Prefer structured tools over raw Cypher queries."
    ),
)

# ---------------------------------------------------------------------------
# Neo4j manager (initialized lazily)
# ---------------------------------------------------------------------------

_manager: Neo4jManager | None = None


def _get_manager() -> Neo4jManager:
    global _manager
    if _manager is None:
        _manager = Neo4jManager()
    return _manager


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def neo4j_search(
    label: str | None = None,
    properties: dict[str, Any] | None = None,
    query: str | None = None,
    limit: int = 25,
) -> str:
    """Search for nodes in Neo4j.

    Provide ONE of:
    - label + optional properties: finds nodes by label and property match
    - query: free-text / semantic-like search across all string properties

    Args:
        label: Node label to filter by (e.g. "Comprovante", "Pessoa").
        properties: Optional dict of exact property matches {key: value}.
        query: Free-text search across all string properties (LIKE %query%).
        limit: Maximum results to return (default 25, max 100).
    """
    limit = min(limit, 100)
    mgr = _get_manager()

    if query:
        # Search across string-like properties only — skip arrays, lists, and non-scalar types
        cypher = (
            "MATCH (n) WHERE ANY(prop IN KEYS(n) WHERE "
            "n[prop] IS NOT NULL AND (n[prop] IS :: STRING OR n[prop] IS :: INTEGER OR n[prop] IS :: FLOAT OR n[prop] IS :: BOOLEAN) AND "
            "toLower(toString(n[prop])) CONTAINS toLower($query)) "
            "RETURN n LIMIT $limit"
        )
        params = {"query": query, "limit": limit}
    elif label:
        # Build parameterized MATCH with optional property filters
        prop_clause = ""
        params: dict[str, Any] = {"limit": limit}
        if properties:
            fragments = []
            for i, (k, v) in enumerate(properties.items()):
                fragments.append(f"n.{k} = $p{i}")
                params[f"p{i}"] = v
            prop_clause = " AND " + " AND ".join(fragments)

        cypher = f"MATCH (n:{label}) WHERE true{prop_clause} RETURN n LIMIT $limit"
        params["limit"] = limit
    else:
        return json.dumps({"error": "Provide 'label' or 'query' parameter"})

    try:
        results = await mgr.execute(cypher, params)
        # Unwrap node dicts from "n" key
        unwrapped = []
        for r in results:
            node = r.get("n", r)
            if hasattr(node, "items"):
                unwrapped.append(node)
            else:
                unwrapped.append({"data": str(node)})
        # Strip large embedding arrays from output (not useful for LLM context)
        _strip_embeddings(unwrapped)
        return json.dumps(unwrapped, ensure_ascii=False, default=str)
    except Exception as e:
        logger.exception("neo4j_search failed")
        return json.dumps({"error": str(e)})


@mcp.tool()
async def neo4j_search_relationships(
    from_label: str | None = None,
    from_properties: dict[str, Any] | None = None,
    rel_type: str | None = None,
    to_label: str | None = None,
    to_properties: dict[str, Any] | None = None,
    limit: int = 25,
) -> str:
    """Search for relationships (edges) in Neo4j.

    Finds patterns (from_node)-[rel]->(to_node) matching the given filters.

    Args:
        from_label: Label of the source node.
        from_properties: Property filters on the source node.
        rel_type: Relationship type to match (e.g. "PAGOU", "PERTENCE").
        to_label: Label of the target node.
        to_properties: Property filters on the target node.
        limit: Maximum results (default 25, max 100).
    """
    limit = min(limit, 100)
    mgr = _get_manager()

    from_lbl = f":{from_label}" if from_label else ""
    to_lbl = f":{to_label}" if to_label else ""
    rel_lbl = f":{rel_type}" if rel_type else ""

    params: dict[str, Any] = {"limit": limit}
    clauses = []

    # Build property filter clauses
    for prefix, props in [("a", from_properties), ("b", to_properties)]:
        if props:
            for i, (k, v) in enumerate(props.items()):
                param_key = f"{prefix}{i}"
                clauses.append(f"{prefix}.{k} = ${param_key}")
                params[param_key] = v

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

    cypher = (
        f"MATCH (a{from_lbl})-[r{rel_lbl}]->(b{to_lbl})"
        f"{where} RETURN a, type(r) AS rel_type, properties(r) AS rel_props, b"
        f" LIMIT $limit"
    )
    params["limit"] = limit

    try:
        results = await mgr.execute(cypher, params)
        output = []
        for r in results:
            output.append({
                "from": r.get("a", {}),
                "rel_type": r.get("rel_type"),
                "rel_props": r.get("rel_props", {}),
                "to": r.get("b", {}),
            })
        _strip_embeddings(output)
        return json.dumps(output, ensure_ascii=False, default=str)
    except Exception as e:
        logger.exception("neo4j_search_relationships failed")
        return json.dumps({"error": str(e)})


@mcp.tool()
async def neo4j_insert(
    label: str,
    properties: dict[str, Any],
) -> str:
    """Create a node in Neo4j.

    Args:
        label: Node label (e.g. "Comprovante", "Pessoa", "Categoria").
        properties: Node properties as key-value pairs.
    """
    mgr = _get_manager()

    # Build parameterized CREATE
    prop_fragments = []
    params: dict[str, Any] = {}
    for i, (k, v) in enumerate(properties.items()):
        prop_fragments.append(f"{k}: $p{i}")
        params[f"p{i}"] = v

    props_str = " {" + ", ".join(prop_fragments) + "}" if prop_fragments else ""
    cypher = f"CREATE (n:{label}{props_str}) RETURN n"

    try:
        results = await mgr.execute_write(cypher, params)
        node = results[0].get("n", results[0]) if results else {}
        _strip_embeddings([node]) if isinstance(node, dict) else None
        return json.dumps({"created": node}, ensure_ascii=False, default=str)
    except Exception as e:
        logger.exception("neo4j_insert failed")
        return json.dumps({"error": str(e)})


@mcp.tool()
async def neo4j_insert_relationship(
    from_label: str,
    from_properties: dict[str, Any],
    rel_type: str,
    to_label: str,
    to_properties: dict[str, Any],
    rel_properties: dict[str, Any] | None = None,
) -> str:
    """Create a relationship between two existing nodes (matched by label + properties).

    Args:
        from_label: Label of the source node.
        from_properties: Properties to match the source node (must be unique).
        rel_type: Relationship type (e.g. "PAGOU", "PERTENCE").
        to_label: Label of the target node.
        to_properties: Properties to match the target node (must be unique).
        rel_properties: Optional properties on the relationship itself.
    """
    mgr = _get_manager()

    params: dict[str, Any] = {}
    from_clauses = []
    for i, (k, v) in enumerate(from_properties.items()):
        from_clauses.append(f"a.{k} = $fa{i}")
        params[f"fa{i}"] = v

    to_clauses = []
    for i, (k, v) in enumerate(to_properties.items()):
        to_clauses.append(f"b.{k} = $tb{i}")
        params[f"tb{i}"] = v

    rel_props = ""
    if rel_properties:
        rel_fragments = []
        for i, (k, v) in enumerate(rel_properties.items()):
            rel_fragments.append(f"{k}: $rp{i}")
            params[f"rp{i}"] = v
        rel_props = " {" + ", ".join(rel_fragments) + "}"

    from_where = " AND ".join(from_clauses) if from_clauses else "true"
    to_where = " AND ".join(to_clauses) if to_clauses else "true"

    cypher = (
        f"MATCH (a:{from_label} {{}}) WHERE {from_where} "
        f"MATCH (b:{to_label} {{}}) WHERE {to_where} "
        f"CREATE (a)-[r:{rel_type}{rel_props}]->(b) "
        f"RETURN type(r) AS rel_type, properties(r) AS rel_props"
    )

    try:
        results = await mgr.execute_write(cypher, params)
        r = results[0] if results else {}
        return json.dumps({"created_relationship": r}, ensure_ascii=False, default=str)
    except Exception as e:
        logger.exception("neo4j_insert_relationship failed")
        return json.dumps({"error": str(e)})


@mcp.tool()
async def neo4j_update(
    label: str,
    match_properties: dict[str, Any],
    update_properties: dict[str, Any],
) -> str:
    """Update properties on nodes matching label + match_properties.

    Args:
        label: Node label to match.
        match_properties: Properties to identify the node(s).
        update_properties: Properties to set/update on matched nodes.
    """
    mgr = _get_manager()

    params: dict[str, Any] = {}
    match_clauses = []
    for i, (k, v) in enumerate(match_properties.items()):
        match_clauses.append(f"n.{k} = $m{i}")
        params[f"m{i}"] = v

    set_clauses = []
    for i, (k, v) in enumerate(update_properties.items()):
        set_clauses.append(f"n.{k} = $u{i}")
        params[f"u{i}"] = v

    where = " AND ".join(match_clauses) if match_clauses else "true"
    sets = ", ".join(set_clauses)

    cypher = f"MATCH (n:{label}) WHERE {where} SET {sets} RETURN n"

    try:
        results = await mgr.execute_write(cypher, params)
        nodes = [r.get("n", {}) for r in results]
        _strip_embeddings(nodes)
        return json.dumps(
            {"updated": len(results), "nodes": nodes},
            ensure_ascii=False,
            default=str,
        )
    except Exception as e:
        logger.exception("neo4j_update failed")
        return json.dumps({"error": str(e)})


@mcp.tool()
async def neo4j_delete(
    label: str,
    match_properties: dict[str, Any],
    detach: bool = False,
) -> str:
    """Delete nodes matching label + match_properties.

    Args:
        label: Node label to match.
        match_properties: Properties to identify the node(s).
        detach: If True, delete node even if it has relationships (DETACH DELETE).
    """
    mgr = _get_manager()

    params: dict[str, Any] = {}
    match_clauses = []
    for i, (k, v) in enumerate(match_properties.items()):
        match_clauses.append(f"n.{k} = $m{i}")
        params[f"m{i}"] = v

    where = " AND ".join(match_clauses) if match_clauses else "true"
    delete_op = "DETACH DELETE" if detach else "DELETE"

    # Count first
    count_cypher = f"MATCH (n:{label}) WHERE {where} RETURN count(n) AS cnt"
    count_result = await mgr.execute(count_cypher, params)
    count = count_result[0]["cnt"] if count_result else 0

    cypher = f"MATCH (n:{label}) WHERE {where} {delete_op} n"

    try:
        await mgr.execute_write(cypher, params)
        return json.dumps({"deleted": count})
    except Exception as e:
        logger.exception("neo4j_delete failed")
        return json.dumps({"error": str(e)})


@mcp.tool()
async def neo4j_schema() -> str:
    """Introspect the Neo4j database schema.

    Returns labels, relationship types, indexes, and constraints.
    """
    mgr = _get_manager()
    try:
        info = await mgr.get_schema_info()
        return json.dumps(info, ensure_ascii=False, default=str)
    except Exception as e:
        logger.exception("neo4j_schema failed")
        return json.dumps({"error": str(e)})


@mcp.tool()
async def neo4j_query(
    query: str,
    parameters: dict[str, Any] | None = None,
    write: bool = False,
) -> str:
    """Execute a raw Cypher query against Neo4j.

    WARNING: This tool allows arbitrary Cypher execution. Use with caution.
    Prefer the structured tools (neo4j_search, neo4j_insert, etc.) when possible.

    Args:
        query: Cypher query string.
        parameters: Optional query parameters.
        write: Set True for write queries (CREATE, MERGE, DELETE, SET, etc.).
    """
    mgr = _get_manager()

    # Safety: limit results for read queries
    if not write and "LIMIT" not in query.upper():
        query = query.rstrip(";") + " LIMIT 100"

    try:
        if write:
            results = await mgr.execute_write(query, parameters)
        else:
            results = await mgr.execute(query, parameters)
        return json.dumps(results, ensure_ascii=False, default=str)
    except Exception as e:
        logger.exception("neo4j_query failed")
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Lifecycle — lazy-connect on first use, close on process exit
# ---------------------------------------------------------------------------

import atexit


def _cleanup():
    """Best-effort close on process exit."""
    import asyncio

    global _manager
    if _manager and _manager._driver:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(_manager.close())
            else:
                loop.run_until_complete(_manager.close())
        except Exception:
            pass


atexit.register(_cleanup)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    """Run the MCP server."""
    transport = os.environ.get("NEO4J_MCP_TRANSPORT", "stdio")

    # Configure host/port and security settings for network transports
    host = os.environ.get("NEO4J_MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("NEO4J_MCP_PORT", "8080"))
    mcp.settings.host = host
    mcp.settings.port = port

    # Allow internal K8s traffic — relax DNS rebinding protection
    if transport in ("streamable-http", "sse"):
        from mcp.server.fastmcp.server import TransportSecuritySettings
        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False,
        )

    mcp.run(transport=transport)


if __name__ == "__main__":
    main()