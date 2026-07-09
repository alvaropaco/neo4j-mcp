FROM python:3.12-slim AS builder

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

# --- Production image ---
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/neo4j-mcp /usr/local/bin/neo4j-mcp

# Non-root user
RUN groupadd -r mcp && useradd -r -g mcp mcp
USER mcp

ENV NEO4J_MCP_TRANSPORT=streamable-http
ENV NEO4J_MCP_HOST=0.0.0.0
ENV NEO4J_MCP_PORT=8080

EXPOSE 8080

ENTRYPOINT ["neo4j-mcp"]