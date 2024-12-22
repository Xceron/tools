FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python3.13

# Mount the cache, uv.lock, and pyproject.toml files for the initial sync
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project

# Copy the entire project directory
COPY . .

# Sync dependencies again after copying the project files
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# Create the Streamlit config directory and copy the config file
RUN mkdir -p /root/.streamlit
COPY .streamlit/config.toml /root/.streamlit/config.toml

EXPOSE 8501

ENTRYPOINT ["uv", "run", "streamlit", "run", "src/app.py"]