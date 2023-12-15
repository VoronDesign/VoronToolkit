FROM python:3.11.6-slim as builder

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential libadmesh-dev

RUN pip install poetry==1.7.0
RUN poetry config virtualenvs.in-project true

COPY ./pyproject.toml ./poetry.lock ./README.md /app/
RUN poetry install --without dev --no-root

COPY voron_toolkit/ /app/voron_toolkit
RUN poetry install --only-root && rm ./pyproject.toml ./poetry.lock

FROM python:3.11.6-slim as test

WORKDIR /app

RUN pip install poetry==1.7.0
COPY ./pyproject.toml /app/
COPY --from=builder /app /app
RUN poetry install --only dev
RUN poetry run ruff voron_toolkit/ && poetry run ruff format --check voron_toolkit/ && poetry run mypy voron_toolkit

FROM python:3.11.6-slim as final

WORKDIR /github/workspace
ADD https://github.com/unlimitedbacon/stl-thumb/releases/download/v0.5.0/stl-thumb_0.5.0_amd64.deb /tmp
RUN apt-get update && \
    apt-get install -y --no-install-recommends git libadmesh-dev /tmp/stl-thumb_0.5.0_amd64.deb && \
    rm -rf /var/cache/apt/archives /var/lib/apt/lists /tmp/stl-thumb_0.5.0_amd64.deb

COPY --from=builder /app /app

ENV PYTHONPATH="${PYTHONPATH}:/app"
ENV GITHUB_STEP_SUMMARY=/dev/null
ENV GITHUB_OUTPUT=/dev/null
ENV PATH="/app/.venv/bin:${PATH}"

COPY entrypoint.sh /app/entrypoint.sh
RUN ["chmod", "+x", "/app/entrypoint.sh"]

RUN git config --system --replace-all safe.directory '*'
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["echo", " No command specified. Refer to the documentation on github @ https://github.com/VoronDesign/Toolkit for available commands!"]
