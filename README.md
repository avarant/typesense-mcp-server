

# Typesense MCP Server

A [Model Context Protocol](https://github.com/modelcontextprotocol/python-sdk) (MCP) Server that interfaces with [Typesense](https://typesense.org/)

## Installation

Install [uv](https://docs.astral.sh/uv/getting-started/installation/)

*Requires Python 3.11 or higher.*

On Mac you can install it using [homebrew](https://brew.sh/)

```shell
brew install uv
```

Clone the package

```shell
git clone git@github.com:avarant/typesense-mcp-server.git ~/typesense-mcp-server
```

Add the server to your MCP client config. Most clients (Cursor at `~/.cursor/mcp.json`, Claude Desktop at `~/Library/Application Support/Claude/claude_desktop_config.json`, Windsurf, Zed, VS Code, etc.) accept the same `mcpServers` shape:

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

Refer to your client's MCP documentation for the exact config file location.

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

### HTTP security

The HTTP transports give full access to your Typesense instance using the configured API key, so they are locked down by default:

- **Loopback only.** The server listens on `127.0.0.1` unless you set `MCP_HOST`.
- **Host/Origin checks.** Requests must address the server as `localhost`, `127.0.0.1` or `[::1]` (plus anything in `MCP_ALLOWED_HOSTS`), and browser requests must come from a localhost page or an origin listed in `MCP_CORS_ORIGINS`. This blocks DNS-rebinding attacks from websites you visit. With `MCP_CORS_ORIGINS='*'`, only localhost pages are allowed.
- **Token required for remote access.** To accept connections from other machines, set `MCP_HOST=0.0.0.0`, `MCP_AUTH_TOKEN`, and `MCP_ALLOWED_HOSTS` to the hostname/IP clients use. Clients must then send `Authorization: Bearer <token>`. The server refuses to start on a non-loopback address without a token unless `MCP_ALLOW_UNAUTHENTICATED=true` (only for setups that enforce auth elsewhere, e.g. a reverse proxy).

```shell
TYPESENSE_API_KEY=xyz \
MCP_TRANSPORT=streamable-http \
MCP_HOST=0.0.0.0 \
MCP_AUTH_TOKEN="$(openssl rand -hex 32)" \
MCP_ALLOWED_HOSTS=mcp.example.com \
uv run python main.py
```

When running the HTTP transport in Docker, set `MCP_HOST=0.0.0.0` inside the container (plus a token), since connections from the host aren't loopback from the container's point of view.

### SSE (legacy)

Two endpoints, `GET /sse` for the event stream and `POST /messages/` for JSON-RPC. Set `MCP_TRANSPORT=sse` (or pass `--sse`):

```shell
TYPESENSE_API_KEY=xyz MCP_TRANSPORT=sse uv run python main.py
```

### Configuration

| Env var               | Default     | Description                                                          |
|-----------------------|-------------|----------------------------------------------------------------------|
| `MCP_TRANSPORT`       | `stdio`     | `stdio`, `sse`, or `streamable-http`                                 |
| `MCP_HOST`            | `127.0.0.1` | Bind address for HTTP transports                                     |
| `MCP_PORT`            | `8000`      | Bind port for HTTP transports                                        |
| `MCP_AUTH_TOKEN`      | _(empty)_   | Bearer token required on HTTP requests. Required when `MCP_HOST` is not loopback. |
| `MCP_ALLOWED_HOSTS`   | _(empty)_   | Extra accepted `Host` values, comma-separated (localhost is always allowed). No port = any port. |
| `MCP_ALLOW_UNAUTHENTICATED` | `false` | Allow a non-loopback `MCP_HOST` without `MCP_AUTH_TOKEN` (auth enforced elsewhere). |
| `MCP_STATELESS_HTTP`  | `false`     | Stateless mode for HTTP transports (required for some web clients)   |
| `MCP_CORS_ORIGINS`    | _(empty)_   | Comma-separated allowed origins. Empty disables CORS. `*` = any.     |
| `CSV_IMPORT_DIR`      | _(empty)_   | Directory `import_documents_from_csv` may read files from. Empty disables file-path imports (inline CSV only). |

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
- `import_documents_from_csv` - Imports documents from inline CSV data, or from a CSV file inside `CSV_IMPORT_DIR`, into a collection

### Search Capabilities
- `search` - Performs a keyword search on a specific collection
- `vector_search` - Performs a vector similarity search on a specific collection
