# Neo4j MCP Server

MCP (Model Context Protocol) server for Neo4j — abstract graph operations for LLMs.

## Tools

| Tool | Description |
|------|-------------|
| `neo4j_search` | Search nodes by label + properties, or free-text query |
| `neo4j_search_relationships` | Search relationships with optional label/property filters |
| `neo4j_insert` | Create a node with label and properties |
| `neo4j_insert_relationship` | Create a relationship between two existing nodes |
| `neo4j_update` | Update properties on nodes matching label + properties |
| `neo4j_delete` | Delete nodes matching label + properties |
| `neo4j_schema` | Introspect labels, relationship types, indexes, constraints |
| `neo4j_query` | Execute raw Cypher (use with caution) |

## Quick Start

### Local (stdio)

```bash
pip install -e .
neo4j-mcp
```

### Streamable HTTP (K8s / network)

```bash
NEO4J_MCP_TRANSPORT=streamable-http NEO4J_MCP_PORT=8080 neo4j-mcp
```

### Docker

```bash
docker build -t neo4j-mcp:latest .
docker run -e NEO4J_URI=bolt://host:7687 \
           -e NEO4J_USER=neo4j \
           -e NEO4J_PASSWORD=your-password \
           -p 8080:8080 neo4j-mcp:latest
```

### Kubernetes

```bash
kubectl apply -f k8s/deployment.yaml
```

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection URI |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | _(empty)_ | Neo4j password |
| `NEO4J_DATABASE` | `neo4j` | Database name |
| `NEO4J_MCP_TRANSPORT` | `stdio` | Transport: `stdio`, `sse`, `streamable-http` |
| `NEO4J_MCP_HOST` | `0.0.0.0` | HTTP host (for streamable-http/sse) |
| `NEO4J_MCP_PORT` | `8080` | HTTP port (for streamable-http/sse) |

## OpenClaw Integration (mcporter)

Add to `~/.mcporter/mcporter.json`:

### stdio (local)

```json
{
  "servers": {
    "neo4j": {
      "command": "neo4j-mcp",
      "env": {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "your-password"
      }
    }
  }
}
```

### Streamable HTTP (K8s)

```json
{
  "servers": {
    "neo4j": {
      "type": "streamable-http",
      "url": "http://neo4j-mcp.openclaw-instance-1:8080/mcp"
    }
  }
}
```

## Tool Reference

### neo4j_search

Search nodes by label with property filters, or free-text across all string properties.

```json
{"label": "Comprovante", "properties": {"categoria": "educacao"}, "limit": 10}
```

Or free-text:
```json
{"query": "Nubank", "limit": 10}
```

### neo4j_insert

Create a node:

```json
{"label": "Comprovante", "properties": {"id": "pix-123", "valor": 150.00, "categoria": "educacao"}}
```

### neo4j_insert_relationship

Create a relationship between existing nodes:

```json
{
  "from_label": "Pessoa",
  "from_properties": {"nome": "Alvaro"},
  "rel_type": "PAGOU",
  "to_label": "Comprovante",
  "to_properties": {"id": "pix-123"},
  "rel_properties": {"data": "2026-07-09"}
}
```

### neo4j_update

Update node properties:

```json
{"label": "Comprovante", "match_properties": {"id": "pix-123"}, "update_properties": {"status": "confirmado"}}
```

### neo4j_delete

Delete nodes (use `detach: true` to remove relationships):

```json
{"label": "Comprovante", "match_properties": {"id": "pix-123"}, "detach": true}
```

### neo4j_schema

Returns all labels, relationship types, indexes, and constraints — no parameters needed.

### neo4j_query

⚠️ Raw Cypher — use sparingly:

```json
{"query": "MATCH (n:Comprovante) RETURN n.valor, n.categoria ORDER BY n.valor DESC LIMIT 5"}
```

For write queries, set `"write": true`.

## Development

```bash
# Install with dev deps
pip install -e ".[dev]"

# Run tests (requires running Neo4j)
NEO4J_URI=bolt://localhost:7687 NEO4J_PASSWORD=test pytest

# Lint
ruff check src/
```

## Architecture

```
LLM / Agent
    ↓ (MCP tool calls)
OpenClaw / mcporter
    ↓ (stdio or HTTP)
neo4j-mcp (FastMCP server)
    ↓ (bolt driver)
Neo4j
```

The server provides a structured abstraction over Cypher — LLMs use named tools with typed parameters instead of constructing raw queries. This gives you:

- **Safety** — no arbitrary query injection
- **Observability** — every operation is traceable
- **Consistency** — uniform interface across all LLM providers
- **Schema awareness** — `neo4j_schema` lets agents discover the graph structure

## License

MIT