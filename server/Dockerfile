FROM python:3.12-slim

WORKDIR /app

# install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# copy dependency files first for layer caching
COPY pyproject.toml uv.lock* ./

# install deps
RUN uv sync --frozen --no-dev 2>/dev/null || uv sync --no-dev

# the rest of the source gets mounted as a volume in dev
COPY . .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
