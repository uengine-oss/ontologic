FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /srv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
ENV KINETIC_PORT=8030
EXPOSE 8030
CMD ["python", "-m", "app.main"]
