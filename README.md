# Neo4j MCP Server

MCP server para operações abstratas de grafos Neo4j.

## Deploy

```bash
# Build
cd neo4j-mcp && docker build -t neo4j-mcp:latest .

# Import to k3s
docker save neo4j-mcp:latest | k3s ctr images import -

# Apply (password set via existing K8s secret or env)
kubectl apply -f k8s/deployment.yaml

# Or set password directly:
kubectl create secret generic neo4j-mcp-secrets \
  --namespace=openclaw-instance-1 \
  --from-literal=NEO4J_URI=bolt://openclaw-instance-1-neo4j:7687 \
  --from-literal=NEO4J_USER=neo4j \
  --from-literal=NEO4J_PASSWORD=<your-password> \
  --dry-run=client -o yaml | kubectl apply -f -
```

## Tools

| Tool | Description |
|------|-------------|
| `neo4j_search` | Search nodes by label/properties or free-text |
| `neo4j_insert` | Create a node |
| `neo4j_update` | Update node properties |
| `neo4j_delete` | Delete nodes |
| `neo4j_schema` | Introspect schema |
| `neo4j_query` | Raw Cypher queries |
| `neo4j_search_relationships` | Search relationships |
| `neo4j_insert_relationship` | Create a relationship |

## Security

⚠️ **Never commit real passwords.** The deployment manifest uses a placeholder `${NEO4J_PASSWORD}`. Set the actual password via Kubernetes secrets.