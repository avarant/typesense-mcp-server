FROM python:3.11-slim

# Pinned uv binary for reproducible, lockfile-based installs
COPY --from=ghcr.io/astral-sh/uv:0.6.10 /uv /bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Install exactly the versions pinned in uv.lock (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy only the application source
COPY main.py ./

# Run as an unprivileged user
RUN useradd --system --uid 10001 --no-create-home app
USER app

ENV PATH="/app/.venv/bin:$PATH"

# Default command to start the MCP server on STDIO
CMD ["mcp", "run", "main.py"]
