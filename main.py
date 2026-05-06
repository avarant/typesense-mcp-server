# Add lifespan support for startup/shutdown with strong typing
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass
import os  # Import os for environment variables (though BaseSettings handles it)
import json # Added for parsing JSON Lines in export
import csv  # Added for CSV import
import io   # Added for CSV import from string

# Import Typesense and Pydantic Settings
import typesense
from pydantic_settings import BaseSettings
from pydantic import Field  # Import Field for default values/validation if needed

# Remove fake database import
# from fake_database import Database  # Replace with your actual DB type

from mcp.server.fastmcp import Context, FastMCP

# Configuration settings loaded from environment variables
class Settings(BaseSettings):
    # Defines application settings, loading values from environment variables.
    typesense_host: str = Field(default='localhost', alias='TYPESENSE_HOST')
    typesense_port: int = Field(default=8108, alias='TYPESENSE_PORT')
    typesense_protocol: str = Field(default='http', alias='TYPESENSE_PROTOCOL')
    typesense_api_key: str = Field(..., alias='TYPESENSE_API_KEY') # Required, use ...

    # MCP transport settings (used when running as an HTTP listener)
    # Supported transports: 'stdio', 'sse', 'streamable-http'
    mcp_transport: str = Field(default='stdio', alias='MCP_TRANSPORT')
    mcp_host: str = Field(default='0.0.0.0', alias='MCP_HOST')
    mcp_port: int = Field(default=8000, alias='MCP_PORT')
    # Stateless mode: required for browser clients like llama.cpp web chat that
    # don't maintain a session across requests. Only meaningful for HTTP transports.
    mcp_stateless_http: bool = Field(default=False, alias='MCP_STATELESS_HTTP')
    # CORS allowed origins, comma-separated (e.g. "http://localhost:3000,https://app.example").
    # Use "*" to allow any origin. Empty (default) disables CORS.
    mcp_cors_origins: str = Field(default='', alias='MCP_CORS_ORIGINS')

    class Config:
        # Allows loading from a .env file if present
        env_file = '.env'
        extra = 'ignore' # Ignore extra fields from env

# Create a named server
# Note: The MCP instance creation is duplicated, consolidating to the one with lifespan
# mcp = FastMCP("My App")

# Specify dependencies for deployment and development
# Dependencies can also be managed in pyproject.toml
# mcp = FastMCP("My App", dependencies=["pandas", "numpy"])


# Application context holding shared resources like the Typesense client
@dataclass
class AppContext:
    # Holds shared application state, accessible within tools.
    client: typesense.Client
    settings: Settings # Keep settings accessible if needed


# Manages the application lifecycle, initializing and cleaning up resources
@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """
    Manage application lifecycle: initialize Typesense client on startup.

    Args:
        server (FastMCP): The FastMCP server instance.

    Yields:
        AppContext: The application context containing the initialized Typesense client.
    """
    # Load settings from environment variables
    settings = Settings()

    # Configure Typesense client
    # Ensure required env var TYPESENSE_API_KEY is set
    if not settings.typesense_api_key:
        raise ValueError("TYPESENSE_API_KEY environment variable not set.")

    client = typesense.Client({
        'nodes': [{
            'host': settings.typesense_host,
            'port': settings.typesense_port,
            'protocol': settings.typesense_protocol
        }],
        'api_key': settings.typesense_api_key,
        'connection_timeout_seconds': 2 # Example timeout
    })

    try:
        # Provide the context to the application
        yield AppContext(client=client, settings=settings)
    finally:
        # Cleanup on shutdown (if necessary)
        # Typesense client based on HTTPX usually doesn't need explicit closing
        print("Shutting down. Typesense client resources managed automatically.")


# Pre-load settings so we can pass HTTP host/port into FastMCP for HTTP modes.
# Settings() reads env vars; a missing TYPESENSE_API_KEY would raise here, which is
# fine for `mcp.run(...)` but not for tooling like `mcp dev` that imports this
# module without the env set — so fall back to defaults if instantiation fails.
try:
    _settings = Settings()
    _server_kwargs = {
        "host": _settings.mcp_host,
        "port": _settings.mcp_port,
        "stateless_http": _settings.mcp_stateless_http,
    }
except Exception:
    _settings = None
    _server_kwargs = {}

# Initialize the MCP Server with the lifespan manager
mcp = FastMCP("Typesense MCP Server", lifespan=app_lifespan, **_server_kwargs)


# Example tool demonstrating access to the Typesense client
@mcp.tool()
async def check_typesense_health(ctx: Context) -> dict | str:
    """
    Checks the health status of the configured Typesense server.

    Args:
        ctx (Context): The MCP context, providing access to application resources.

    Returns:
        dict | str: The health status dictionary from Typesense or an error message.
    """
    # Access the Typesense client from the lifespan context
    try:
        client: typesense.Client = ctx.request_context.lifespan_context.client
        health_status = await client.health.retrieve()
        return health_status
    except Exception as e:
        # Log the exception ideally
        print(f"Error checking Typesense health: {e}")
        return f"Error connecting to Typesense or checking health: {e}"

# --- Typesense Collection Tools ---

# Tool to list all collections
@mcp.tool()
async def list_collections(ctx: Context) -> list | str:
    """
    Retrieves a list of all collections in the Typesense server.

    Args:
        ctx (Context): The MCP context.

    Returns:
        list | str: A list of collection schemas or an error message string.
    """
    try:
        client: typesense.Client = ctx.request_context.lifespan_context.client
        collections = client.collections.retrieve()
        # The response is expected to be a list of dictionaries
        return collections
    except typesense.exceptions.TypesenseClientError as e:
        print(f"Error listing collections: {e}")
        return f"Error listing collections: {e}"
    except Exception as e:
        print(f"An unexpected error occurred while listing collections: {e}")
        return f"An unexpected error occurred: {e}"

# Tool to describe a specific collection
@mcp.tool()
async def describe_collection(ctx: Context, collection_name: str) -> dict | str:
    """
    Retrieves the schema and metadata for a specific collection.

    Args:
        ctx (Context): The MCP context.
        collection_name (str): The name of the collection to describe.

    Returns:
        dict | str: The collection schema dictionary or an error message string.
    """
    if not collection_name:
        return "Error: collection_name parameter is required."
    try:
        client: typesense.Client = ctx.request_context.lifespan_context.client
        collection_info = client.collections[collection_name].retrieve()
        return collection_info
    except typesense.exceptions.ObjectNotFound:
        return f"Error: Collection '{collection_name}' not found."
    except typesense.exceptions.TypesenseClientError as e:
        print(f"Error describing collection '{collection_name}': {e}")
        return f"Error describing collection '{collection_name}': {e}"
    except Exception as e:
        print(f"An unexpected error occurred while describing collection '{collection_name}': {e}")
        return f"An unexpected error occurred: {e}"

# Tool to export all documents from a collection
@mcp.tool()
async def export_collection(ctx: Context, collection_name: str) -> list[dict] | str:
    """
    Exports all documents from a specific collection.

    Warning: This can be memory-intensive for very large collections.

    Args:
        ctx (Context): The MCP context.
        collection_name (str): The name of the collection to export.

    Returns:
        list[dict] | str: A list of document dictionaries or an error message string.
    """
    if not collection_name:
        return "Error: collection_name parameter is required."

    documents = []
    try:
        client: typesense.Client = ctx.request_context.lifespan_context.client
        # Check if collection exists first to give a clearer error
        _ = client.collections[collection_name].retrieve() # Check existence synchronously

        exported_lines = client.collections[collection_name].documents.export()
        for line in exported_lines:
            try:
                documents.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"Warning: Could not decode JSON line during export: {line}")
                # Decide whether to skip or raise an error
                continue
        return documents
    except typesense.exceptions.ObjectNotFound:
        return f"Error: Collection '{collection_name}' not found."
    except typesense.exceptions.TypesenseClientError as e:
        print(f"Error exporting collection '{collection_name}': {e}")
        return f"Error exporting collection '{collection_name}': {e}"
    except Exception as e:
        print(f"An unexpected error occurred while exporting collection '{collection_name}': {e}")
        return f"An unexpected error occurred: {e}"

# --- Typesense Search Tools ---

# Tool to perform keyword search
@mcp.tool()
async def search(
    ctx: Context,
    collection_name: str,
    query: str,
    query_by: str,
    filter_by: str | None = None,
    sort_by: str | None = None,
    group_by: str | None = None, # Added group_by
    facet_by: str | None = None, # Added facet_by
    per_page: int = 20,
    page: int = 1 # Added page
) -> dict | str:
    """
    Performs a keyword search on a specific collection.

    Args:
        ctx (Context): The MCP context.
        collection_name (str): The name of the collection to search within.
        query (str): The search query string. Use '*' for all documents.
        query_by (str): Comma-separated list of fields to search in.
        filter_by (str | None): Filter conditions (e.g., 'price:>100 && category:Electronics'). Defaults to None.
        sort_by (str | None): Sorting criteria (e.g., 'price:asc, rating:desc'). Defaults to None.
        group_by (str | None): Field to group results by. Defaults to None.
        facet_by (str | None): Fields to facet on. Defaults to None.
        per_page (int): Number of results per page. Defaults to 20.
        page (int): Page number to retrieve. Defaults to 1.


    Returns:
        dict | str: The search results dictionary from Typesense or an error message string.
    """
    if not collection_name:
        return "Error: collection_name parameter is required."
    if not query:
        return "Error: query parameter is required."
    if not query_by:
        return "Error: query_by parameter is required."

    search_params = {
        'q': query,
        'query_by': query_by,
        'per_page': per_page,
        'page': page,
    }
    if filter_by:
        search_params['filter_by'] = filter_by
    if sort_by:
        search_params['sort_by'] = sort_by
    if group_by:
        search_params['group_by'] = group_by
    if facet_by:
        search_params['facet_by'] = facet_by

    try:
        client: typesense.Client = ctx.request_context.lifespan_context.client
        search_results = client.collections[collection_name].documents.search(search_params)
        return search_results
    except typesense.exceptions.ObjectNotFound:
        return f"Error: Collection '{collection_name}' not found."
    except typesense.exceptions.RequestMalformed as e:
         return f"Error: Malformed search request for collection '{collection_name}'. Check parameters (query_by fields existence, filter/sort syntax, etc.). Details: {e}"
    except typesense.exceptions.TypesenseClientError as e:
        print(f"Error searching collection '{collection_name}': {e}")
        return f"Error searching collection '{collection_name}': {e}"
    except Exception as e:
        print(f"An unexpected error occurred while searching collection '{collection_name}': {e}")
        return f"An unexpected error occurred: {e}"


# Tool to perform vector search (with optional text query for hybrid search)
@mcp.tool()
async def vector_search(
    ctx: Context,
    collection_name: str,
    vector_query: str,
    query: str | None = None, # Optional text query for hybrid search
    query_by: str | None = None, # Required if 'query' is provided for hybrid search
    filter_by: str | None = None,
    sort_by: str | None = None,
    per_page: int = 10,
    page: int = 1
) -> dict | str:
    """
    Performs a vector similarity search on a specific collection, with optional hybrid text search.

    Args:
        ctx (Context): The MCP context.
        collection_name (str): The name of the collection to search within.
        vector_query (str): The vector query string, formatted as 'vector_field:([v1,v2,...], k: num_neighbors)'.
        query (str | None): Optional: The text query string for hybrid search. Defaults to None.
        query_by (str | None): Optional: Comma-separated list of text fields. Required if 'query' is provided. Defaults to None.
        filter_by (str | None): Filter conditions to apply. Defaults to None.
        sort_by (str | None): Optional sorting criteria. Defaults to None.
        per_page (int): Number of results per page. Defaults to 10.
        page (int): Page number to retrieve. Defaults to 1.

    Returns:
        dict | str: The vector search results dictionary from Typesense or an error message string.
    """
    if not collection_name:
        return "Error: collection_name parameter is required."
    if not vector_query:
        return "Error: vector_query parameter is required (e.g., 'vec:([0.1,...], k:5)')."
    if query and not query_by:
        return "Error: query_by parameter is required when providing a text query for hybrid search."

    search_params = {
        'vector_query': vector_query,
        'per_page': per_page,
        'page': page,
        'q': query if query else '*' # Use text query if provided, else '*' for pure vector
    }

    if query and query_by:
        search_params['query_by'] = query_by

    if filter_by:
        search_params['filter_by'] = filter_by
    if sort_by:
        search_params['sort_by'] = sort_by

    try:
        client: typesense.Client = ctx.request_context.lifespan_context.client
        search_results = client.collections[collection_name].documents.search(search_params)
        return search_results
    except typesense.exceptions.ObjectNotFound:
        return f"Error: Collection '{collection_name}' not found."
    except typesense.exceptions.RequestMalformed as e:
         # Provide more specific feedback if possible
         error_message = f"Error: Malformed vector search request for collection '{collection_name}'. Details: {e}"
         if "vector_query" in str(e) and "dimension" in str(e):
             error_message += " Check if vector dimensions match the schema."
         elif "vector_query" in str(e):
             error_message += " Check vector query format 'field:([vector], k:num)'."
         elif "filter_by" in str(e):
             error_message += " Check filter syntax."
         elif query and query_by and any(field in str(e) for field in query_by.split(',')):
             error_message += f" Check if text search fields in 'query_by' ({query_by}) exist in the schema."
         return error_message
    except typesense.exceptions.TypesenseClientError as e:
        print(f"Error during vector search in collection '{collection_name}': {e}")
        return f"Error during vector search in collection '{collection_name}': {e}"
    except Exception as e:
        print(f"An unexpected error occurred during vector search in collection '{collection_name}': {e}")
        return f"An unexpected error occurred: {e}"

# --- Collection Management Tools ---

# Tool to create a new collection
@mcp.tool()
async def create_collection(ctx: Context, schema: dict) -> dict | str:
    """
    Creates a new collection with the provided schema.

    Args:
        ctx (Context): The MCP context.
        schema (dict): The collection schema dictionary (must include 'name' and 'fields').

    Returns:
        dict | str: The created collection schema dictionary or an error message string.
    """
    if not isinstance(schema, dict) or 'name' not in schema or 'fields' not in schema:
        return "Error: Invalid schema provided. Must be a dictionary with 'name' and 'fields' keys."

    try:
        client: typesense.Client = ctx.request_context.lifespan_context.client
        # Assuming create is async based on library structure
        created_collection = await client.collections.create(schema)
        return created_collection
    except typesense.exceptions.ObjectAlreadyExists:
        return f"Error: Collection '{schema.get('name')}' already exists."
    except typesense.exceptions.RequestMalformed as e:
         return f"Error: Malformed create collection request. Check schema format. Details: {e}"
    except typesense.exceptions.TypesenseClientError as e:
        print(f"Error creating collection '{schema.get('name')}': {e}")
        return f"Error creating collection '{schema.get('name')}': {e}"
    except Exception as e:
        print(f"An unexpected error occurred while creating collection '{schema.get('name')}': {e}")
        return f"An unexpected error occurred: {e}"

# Tool to delete a collection
@mcp.tool()
async def delete_collection(ctx: Context, collection_name: str) -> dict | str:
    """
    Deletes a specific collection.

    Args:
        ctx (Context): The MCP context.
        collection_name (str): The name of the collection to delete.

    Returns:
        dict | str: The deleted collection schema dictionary or an error message string.
    """
    if not collection_name:
        return "Error: collection_name parameter is required."

    try:
        client: typesense.Client = ctx.request_context.lifespan_context.client
        # NOTE: Assuming delete is synchronous based on pattern with retrieve/export/search.
        deleted_info = client.collections[collection_name].delete()
        return deleted_info
    except typesense.exceptions.ObjectNotFound:
        return f"Error: Collection '{collection_name}' not found."
    except typesense.exceptions.TypesenseClientError as e:
        print(f"Error deleting collection '{collection_name}': {e}")
        return f"Error deleting collection '{collection_name}': {e}"
    except Exception as e:
        print(f"An unexpected error occurred while deleting collection '{collection_name}': {e}")
        return f"An unexpected error occurred: {e}"

# Tool to truncate a collection (delete all documents, keep schema)
@mcp.tool()
async def truncate_collection(ctx: Context, collection_name: str) -> str:
    """
    Truncates a collection by deleting all documents but keeping the schema.
    Achieved by retrieving schema, deleting collection, and recreating it.

    Args:
        ctx (Context): The MCP context.
        collection_name (str): The name of the collection to truncate.

    Returns:
        str: A success or error message string.
    """
    if not collection_name:
        return "Error: collection_name parameter is required."

    client: typesense.Client = ctx.request_context.lifespan_context.client
    original_schema = None

    try:
        # 1. Retrieve the current schema (assuming sync)
        print(f"Truncating '{collection_name}': Retrieving schema...")
        original_schema = client.collections[collection_name].retrieve()
        # We only need the fields, name, and potentially other top-level settings for re-creation
        # Remove read-only fields like 'created_at', 'num_documents' before re-creating
        schema_to_recreate = {
            key: value for key, value in original_schema.items()
            if key in ['name', 'fields', 'default_sorting_field', 'token_separators', 'symbols_to_index', 'enable_nested_fields']
        }

        # 2. Delete the collection (assuming sync)
        print(f"Truncating '{collection_name}': Deleting original collection...")
        client.collections[collection_name].delete()

        # 3. Recreate the collection with the original schema (assuming async)
        print(f"Truncating '{collection_name}': Recreating collection with schema...")
        await client.collections.create(schema_to_recreate)

        return f"Successfully truncated collection '{collection_name}'."

    except typesense.exceptions.ObjectNotFound:
        return f"Error during truncate: Collection '{collection_name}' not found (maybe already deleted?)."
    except typesense.exceptions.TypesenseClientError as e:
        error_message = f"Error during truncate operation on '{collection_name}': {e}"
        print(error_message)
        # Attempt to restore if deletion succeeded but recreation failed?
        # For now, just report the error stage.
        if original_schema and not client.collections[collection_name].exists(): # Check if deleted but not recreated
             error_message += " Original collection was deleted but recreation failed."
        return error_message
    except Exception as e:
        print(f"An unexpected error occurred during truncate for '{collection_name}': {e}")
        return f"An unexpected error occurred during truncate: {e}"

# --- Document Management Tools ---

# Tool to create a single document
@mcp.tool()
async def create_document(ctx: Context, collection_name: str, document: dict) -> dict | str:
    """
    Creates a single new document in a specific collection.

    Args:
        ctx (Context): The MCP context.
        collection_name (str): The name of the collection.
        document (dict): The document data to create (must include an 'id' field unless auto-schema).

    Returns:
        dict | str: The created document dictionary or an error message string.
    """
    if not collection_name:
        return "Error: collection_name parameter is required."
    if not isinstance(document, dict):
        return "Error: document parameter must be a dictionary."
    # Consider adding check for 'id' field if not using auto-id generation

    try:
        print(f"Creating document in collection '{collection_name}' with ID: {document.get('id', 'N/A')}")
        client: typesense.Client = ctx.request_context.lifespan_context.client
        # NOTE: Assuming create is *sync* based on observed pattern
        created_doc = client.collections[collection_name].documents.create(document)
        return created_doc
    except typesense.exceptions.ObjectNotFound:
        return f"Error: Collection '{collection_name}' not found."
    except typesense.exceptions.ObjectAlreadyExists as e:
         # Occurs if document ID already exists
         return f"Error: Document with ID '{document.get('id', 'N/A')}' already exists in collection '{collection_name}'. Use upsert to update. Details: {e}"
    except typesense.exceptions.RequestMalformed as e:
         return f"Error: Malformed create document request for collection '{collection_name}'. Check document structure against schema. Details: {e}"
    except typesense.exceptions.TypesenseClientError as e:
        print(f"Error creating document in '{collection_name}': {e}")
        return f"Error creating document in '{collection_name}': {e}"
    except Exception as e:
        print(f"An unexpected error occurred while creating document in '{collection_name}': {e}")
        return f"An unexpected error occurred: {e}"

# Tool to upsert (create or update) a single document
@mcp.tool()
async def upsert_document(ctx: Context, collection_name: str, document: dict) -> dict | str:
    """
    Upserts (creates or updates) a single document in a specific collection.

    Args:
        ctx (Context): The MCP context.
        collection_name (str): The name of the collection.
        document (dict): The document data to upsert (must include an 'id' field).

    Returns:
        dict | str: The upserted document dictionary or an error message string.
    """
    if not collection_name:
        return "Error: collection_name parameter is required."
    if not isinstance(document, dict) or 'id' not in document:
        return "Error: document parameter must be a dictionary and include an 'id' field."

    try:
        client: typesense.Client = ctx.request_context.lifespan_context.client
        # NOTE: Assuming upsert is *sync* based on observed pattern
        upserted_doc = client.collections[collection_name].documents.upsert(document)
        return upserted_doc
    except typesense.exceptions.ObjectNotFound:
        return f"Error: Collection '{collection_name}' not found."
    except typesense.exceptions.RequestMalformed as e:
         return f"Error: Malformed upsert document request for collection '{collection_name}'. Check document structure against schema. Details: {e}"
    except typesense.exceptions.TypesenseClientError as e:
        print(f"Error upserting document in '{collection_name}': {e}")
        return f"Error upserting document in '{collection_name}': {e}"
    except Exception as e:
        print(f"An unexpected error occurred while upserting document in '{collection_name}': {e}")
        return f"An unexpected error occurred: {e}"

# Tool to index (create, upsert, update) multiple documents
@mcp.tool()
async def index_multiple_documents(
    ctx: Context,
    collection_name: str,
    documents: list[dict],
    action: str = 'upsert'
) -> list[dict] | str:
    """
    Indexes (creates, upserts, or updates) multiple documents in a batch.

    Args:
        ctx (Context): The MCP context.
        collection_name (str): The name of the collection.
        documents (list[dict]): A list of document dictionaries to index.
        action (str): The import action ('create', 'upsert', 'update'). Defaults to 'upsert'.

    Returns:
        list[dict] | str: A list of result dictionaries (one per document) or an error message string.
                         Each result dict typically looks like {'success': true/false, 'error': '...', 'document': {...}}.
    """
    if not collection_name:
        return "Error: collection_name parameter is required."
    if not isinstance(documents, list) or not documents:
        return "Error: documents parameter must be a non-empty list of dictionaries."
    if action not in ['create', 'upsert', 'update']:
        return "Error: action parameter must be one of 'create', 'upsert', 'update'."

    results = []
    try:
        client: typesense.Client = ctx.request_context.lifespan_context.client
        # NOTE: Assuming import_ is *sync* based on observed pattern
        # Also, the response is JSONL strings, not directly awaitable objects
        import_response_lines = client.collections[collection_name].documents.import_(documents, {'action': action})

        # Response is JSON Lines (string per result), parse each line
        # NOTE: Changed to normal 'for' loop
        for line in import_response_lines:
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"Warning: Could not decode JSON line from import response: {line}")
                results.append({'success': False, 'error': 'Failed to decode response line', 'raw_line': line})
        return results
    except typesense.exceptions.ObjectNotFound:
        return f"Error: Collection '{collection_name}' not found."
    except typesense.exceptions.RequestMalformed as e:
         return f"Error: Malformed bulk import request for collection '{collection_name}'. Check document structures. Details: {e}"
    except typesense.exceptions.TypesenseClientError as e:
        print(f"Error during bulk import to '{collection_name}': {e}")
        return f"Error during bulk import to '{collection_name}': {e}"
    except Exception as e:
        print(f"An unexpected error occurred during bulk import to '{collection_name}': {e}")
        return f"An unexpected error occurred during bulk import: {e}"

# Tool to delete a single document by ID
@mcp.tool()
async def delete_document(ctx: Context, collection_name: str, document_id: str) -> dict | str:
    """
    Deletes a single document by its ID from a specific collection.

    Args:
        ctx (Context): The MCP context.
        collection_name (str): The name of the collection.
        document_id (str): The ID of the document to delete.

    Returns:
        dict | str: The deleted document dictionary or an error message string.
    """
    if not collection_name:
        return "Error: collection_name parameter is required."
    if not document_id:
        return "Error: document_id parameter is required."

    try:
        client: typesense.Client = ctx.request_context.lifespan_context.client
        # NOTE: Assuming document delete is synchronous based on collection delete pattern.
        deleted_doc = client.collections[collection_name].documents[document_id].delete()
        return deleted_doc
    except typesense.exceptions.ObjectNotFound:
        # Could be collection or document not found
        return f"Error: Collection '{collection_name}' or Document ID '{document_id}' not found."
    except typesense.exceptions.TypesenseClientError as e:
        print(f"Error deleting document '{document_id}' from '{collection_name}': {e}")
        return f"Error deleting document '{document_id}' from '{collection_name}': {e}"
    except Exception as e:
        print(f"An unexpected error occurred while deleting document '{document_id}' from '{collection_name}': {e}")
        return f"An unexpected error occurred: {e}"

# Tool to import documents from CSV data or file path
@mcp.tool()
async def import_documents_from_csv(
    ctx: Context,
    collection_name: str,
    csv_data_or_path: str,
    batch_size: int = 100,
    action: str = 'upsert'
) -> dict:
    """
    Imports documents from CSV data (as a string) or a file path into a collection.
    Assumes CSV header row maps directly to Typesense field names.
    Does basic type inference for int/float, otherwise treats as string.

    Args:
        ctx (Context): The MCP context.
        collection_name (str): The name of the collection.
        csv_data_or_path (str): Either the raw CSV data as a string or the path to a CSV file.
        batch_size (int): Number of documents to import per batch. Defaults to 100.
        action (str): Import action ('create', 'upsert', 'update'). Defaults to 'upsert'.

    Returns:
        dict: A summary of the import process including total processed, successful, failed count, and any errors.
    """
    if not collection_name:
        return {"success": False, "error": "collection_name parameter is required."}
    if not csv_data_or_path:
        return {"success": False, "error": "csv_data_or_path parameter is required."}
    if action not in ['create', 'upsert', 'update']:
        return {"success": False, "error": "action parameter must be one of 'create', 'upsert', 'update'."}

    client: typesense.Client = ctx.request_context.lifespan_context.client
    batch = []
    total_processed = 0
    total_successful = 0
    total_failed = 0
    errors = []
    import_results = []

    try:
        # Check if collection exists (synchronously)
        _ = client.collections[collection_name].retrieve()

        file_obj = None
        reader = None

        # Determine if input is path or data
        if os.path.exists(csv_data_or_path):
            print(f"Importing from file path: {csv_data_or_path}")
            try:
                # Specify encoding, adjust if needed
                file_obj = open(csv_data_or_path, 'r', newline='', encoding='utf-8')
                reader = csv.DictReader(file_obj)
            except FileNotFoundError:
                 return {"success": False, "error": f"CSV file not found at path: {csv_data_or_path}"}
            except Exception as e:
                 return {"success": False, "error": f"Error opening or reading CSV file: {e}"}
        else:
            print("Importing from CSV string data.")
            file_obj = io.StringIO(csv_data_or_path)
            reader = csv.DictReader(file_obj)

        if not reader or not reader.fieldnames:
             return {"success": False, "error": "Could not read CSV headers or data."}

        print(f"CSV Headers detected: {reader.fieldnames}")

        for row in reader:
            total_processed += 1
            # Basic type inference (can be expanded significantly)
            processed_row = {}
            for key, value in row.items():
                if value is None or value == '':
                    # Handle empty strings or None - skip or set default? Depends on schema.
                    # For now, let's skip adding the key if value is empty/None
                    continue
                try:
                    # Try int, then float, then string
                    processed_row[key] = int(value)
                except ValueError:
                    try:
                        processed_row[key] = float(value)
                    except ValueError:
                        processed_row[key] = value # Keep as string

            batch.append(processed_row)

            if len(batch) >= batch_size:
                print(f"Importing batch of {len(batch)} documents...")
                try:
                    # NOTE: Assuming import_ is *sync* based on observed pattern
                    # Also, the response is JSONL strings
                    batch_results_lines = client.collections[collection_name].documents.import_(batch, {'action': action})
                    # NOTE: Changed to normal 'for' loop
                    for line in batch_results_lines:
                        try:
                            result = json.loads(line)
                            import_results.append(result)
                            if result.get('success', False):
                                total_successful += 1
                            else:
                                total_failed += 1
                                errors.append(result.get('error', 'Unknown error in batch result'))
                        except json.JSONDecodeError:
                            print(f"Warning: Could not decode JSON line from import response: {line}")
                            total_failed += 1
                            errors.append(f"Failed to decode response line: {line}")
                except Exception as batch_error:
                    print(f"Error importing batch: {batch_error}")
                    total_failed += len(batch) # Assume all in batch failed
                    errors.append(f"Failed to import batch: {batch_error}")
                finally:
                    batch = [] # Clear batch

        # Import any remaining documents in the last batch
        if batch:
            print(f"Importing final batch of {len(batch)} documents...")
            try:
                # NOTE: Assuming import_ is *sync* based on observed pattern
                batch_results_lines = client.collections[collection_name].documents.import_(batch, {'action': action})
                # NOTE: Changed to normal 'for' loop
                for line in batch_results_lines:
                     try:
                        result = json.loads(line)
                        import_results.append(result)
                        if result.get('success', False):
                            total_successful += 1
                        else:
                            total_failed += 1
                            errors.append(result.get('error', 'Unknown error in batch result'))
                     except json.JSONDecodeError:
                        print(f"Warning: Could not decode JSON line from import response: {line}")
                        total_failed += 1
                        errors.append(f"Failed to decode response line: {line}")
            except Exception as batch_error:
                print(f"Error importing final batch: {batch_error}")
                total_failed += len(batch)
                errors.append(f"Failed to import final batch: {batch_error}")

    except typesense.exceptions.ObjectNotFound:
        return {"success": False, "error": f"Collection '{collection_name}' not found."}
    except Exception as e:
        print(f"An unexpected error occurred during CSV import preparation or loop for '{collection_name}': {e}")
        return {"success": False, "error": f"An unexpected error occurred during CSV import: {e}"}
    finally:
        if file_obj and not isinstance(file_obj, io.StringIO):
             file_obj.close() # Close file if opened

    summary = {
        "success": total_failed == 0,
        "total_processed": total_processed,
        "total_successful": total_successful,
        "total_failed": total_failed,
        "errors": errors[:10] # Limit reported errors
    }
    print(f"CSV Import Summary: {summary}")
    return summary


def _parse_cors_origins(raw: str) -> list[str]:
    return [o.strip() for o in raw.split(',') if o.strip()]


def _run_http_with_cors(app, host: str, port: int, origins: list[str]) -> None:
    """Wrap a FastMCP HTTP app in CORS middleware and serve it with uvicorn."""
    import uvicorn
    from starlette.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    # Transport selection:
    #   MCP_TRANSPORT=stdio (default)    -> stdin/stdout, for desktop clients
    #   MCP_TRANSPORT=sse                -> HTTP SSE listener on MCP_HOST:MCP_PORT
    #   MCP_TRANSPORT=streamable-http    -> Streamable HTTP at /mcp (recommended for web clients)
    # CLI flags --sse and --http override the env var for convenience.
    import sys
    if _settings is None:
        raise SystemExit("Failed to load settings (is TYPESENSE_API_KEY set?).")

    if "--sse" in sys.argv:
        transport = "sse"
    elif "--http" in sys.argv:
        transport = "streamable-http"
    else:
        transport = _settings.mcp_transport

    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport in ("sse", "streamable-http"):
        origins = _parse_cors_origins(_settings.mcp_cors_origins)
        if origins:
            app = mcp.sse_app() if transport == "sse" else mcp.streamable_http_app()
            _run_http_with_cors(app, _settings.mcp_host, _settings.mcp_port, origins)
        else:
            mcp.run(transport=transport)
    else:
        raise SystemExit(
            f"Unsupported MCP_TRANSPORT={transport!r}; expected 'stdio', 'sse', or 'streamable-http'."
        )
