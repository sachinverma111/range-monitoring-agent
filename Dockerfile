# Base image
FROM python:3.11-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Builder stage
FROM base AS builder

RUN apt-get update \
    && apt-get -y upgrade \
    && apt-get install -y --no-install-recommends \
    git build-essential curl python3-dev
# Install poetry for Python dependency management
RUN curl -sSL https://install.python-poetry.org | python3 - --version 1.8.0 \
    && ln -s /root/.local/bin/poetry /usr/local/bin/poetry

# Configure Poetry to use project-level venvs
WORKDIR /app

ENV VIRTUAL_ENV=/app/.venv
RUN poetry config virtualenvs.create true \
    && poetry config virtualenvs.in-project true \
    && poetry config virtualenvs.path /app/.venv

# Install dependencies
COPY pyproject.toml poetry.lock /app/
RUN mkdir -p /app/range_monitor
COPY range_monitor/__init__.py /app/range_monitor/
RUN poetry install --no-cache --no-interaction --no-ansi --without dev

# Final stage
FROM base AS final

# Create and switch to non-root user
ARG PEAK_USER_ID=8877
RUN useradd -r -d /app -u $PEAK_USER_ID peak-user

# Copy artifacts from builder
COPY --from=builder --chown=$PEAK_USER_ID /app/.venv /app/.venv

# Environment setup
ENV TZ=UTC \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    DEBIAN_FRONTEND=noninteractive

COPY --chown=$PEAK_USER_ID . /app
WORKDIR /app

# Build and install the package
RUN /app/.venv/bin/pip install --no-deps .

RUN chown -R peak-user:peak-user /app

USER $PEAK_USER_ID

EXPOSE 8050

CMD ["streamlit", "run", "app.py", "--server.port=8050", "--server.address=0.0.0.0", "--server.headless=true"]
