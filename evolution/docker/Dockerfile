FROM python:3.13-slim

RUN useradd --create-home --uid 10001 evaluator
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev
COPY alphas ./alphas
COPY common ./common
COPY data ./data
COPY evolution ./evolution
USER evaluator
ENV PATH="/app/.venv/bin:${PATH}" PYTHONPATH=/app PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python", "-m", "evolution.sandbox_worker"]

