# dev-idp · mock-mes · mock-cmms · mock-aps 공용 이미지 (데모 전용)
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /srv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-install-project
COPY dev_idp.py mock_mes.py mock_cmms.py mock_aps.py ./
