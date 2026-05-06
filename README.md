# Typesense MCP Server
[![smithery badge](https://smithery.ai/badge/@avarant/typesense-mcp-server)](https://smithery.ai/server/@avarant/typesense-mcp-server)

A [Model Context Protocol](https://github.com/modelcontextprotocol/python-sdk) (MCP) Server that interfaces with [Typesense](https://typesense.org/)

## Installation

### Installing via Smithery

To install Typesense Server Integration for Claude Desktop automatically via [Smithery](https://smithery.ai/server/@avarant/typesense-mcp-server):

```bash
npx -y @smithery/cli install @avarant/typesense-mcp-server --client claude
```

### Manual Installation
Install [uv](https://docs.astral.sh/uv/getting-started/installation/)

On Mac you can install it using [homebrew](https://brew.sh/)

```shell
brew install uv
```

Clone the package

```shell
git clone git@github.com:avarant/typesense-mcp-server.git ~/typesense-mcp-server
```

Update your `.cursor/mcp.json` to use in **Cursor**

```json
{
  "mcpServers": {
    "typesense": {
      "command": "uv",
      "args": ["--directory", "~/typesense-mcp-server", "run", "mcp", "run", "main.py"],
      "env": {
        "TYPESENSE_HOST": "",
        "TYPESENSE_PORT": "", 
        "TYPESENSE_PROTOCOL": "",
        "TYPESENSE_API_KEY": ""
      }
    }
  }
}
```

## Transports

The server supports three MCP transports. STDIO is the default and is what most desktop clients (Claude Desktop, Cursor, etc.) use. For remote clients or web UIs, you can run it as an HTTP server using either the legacy SSE transport or the newer **Streamable HTTP** transport.

### STDIO (default)

```shell
TYPESENSE_API_KEY=xyz uv run python main.py
```

### Streamable HTTP (recommended for web clients)

Single endpoint at `/mcp`. Works with browser-based clients like the `llama.cpp` web chat. Set `MCP_TRANSPORT=streamable-http` (or pass `--http`):

```shell
TYPESENSE_API_KEY=xyz \
MCP_TRANSPORT=streamable-http \
MCP_STATELESS_HTTP=true \
MCP_CORS_ORIGINS='*' \
uv run python main.py
```

- Stateless mode (`MCP_STATELESS_HTTP=true`) is required for clients that don't keep an MCP session across requests.
- CORS must be enabled (`MCP_CORS_ORIGINS`) for browser clients. Use a specific origin like `http://localhost:8080` in production rather than `*`.

### SSE (legacy)

Two endpoints, `GET /sse` for the event stream and `POST /messages/` for JSON-RPC. Set `MCP_TRANSPORT=sse` (or pass `--sse`):

```shell
TYPESENSE_API_KEY=xyz MCP_TRANSPORT=sse uv run python main.py
```

### Configuration

| Env var               | Default     | Description                                                          |
|-----------------------|-------------|----------------------------------------------------------------------|
| `MCP_TRANSPORT`       | `stdio`     | `stdio`, `sse`, or `streamable-http`                                 |
| `MCP_HOST`            | `0.0.0.0`   | Bind address for HTTP transports                                     |
| `MCP_PORT`            | `8000`      | Bind port for HTTP transports                                        |
| `MCP_STATELESS_HTTP`  | `false`     | Stateless mode for HTTP transports (required for some web clients)   |
| `MCP_CORS_ORIGINS`    | _(empty)_   | Comma-separated allowed origins. Empty disables CORS. `*` = any.     |

## Available Tools

The Typesense MCP Server provides the following tools:

### Server Management
- `check_typesense_health` - Checks the health status of the configured Typesense server
- `list_collections` - Retrieves a list of all collections in the Typesense server

### Collection Management
- `describe_collection` - Retrieves the schema and metadata for a specific collection
- `export_collection` - Exports all documents from a specific collection
- `create_collection` - Creates a new collection with the provided schema
- `delete_collection` - Deletes a specific collection
- `truncate_collection` - Truncates a collection by deleting all documents but keeping the schema

### Document Operations
- `create_document` - Creates a single new document in a specific collection
- `upsert_document` - Upserts (creates or updates) a single document in a specific collection
- `index_multiple_documents` - Indexes (creates, upserts, or updates) multiple documents in a batch
- `delete_document` - Deletes a single document by its ID from a specific collection
- `import_documents_from_csv` - Imports documents from CSV data into a collection

### Search Capabilities
- `search` - Performs a keyword search on a specific collection
- `vector_search` - Performs a vector similarity search on a specific collection
