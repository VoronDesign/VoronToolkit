FROM python:3.11.6-slim as builder

WORKDIR /app

RUN pip install poetry==1.7.0
RUN poetry config virtualenvs.in-project true

COPY ./pyproject.toml ./poetry.lock ./README.md /app/

RUN apt-get update && apt-get install -y build-essential libadmesh-dev

RUN poetry install --only=main --no-root

COPY voron_ci/ /app/voron_ci

RUN poetry install --only-root && rm ./pyproject.toml ./poetry.lock

FROM python:3.11.6-slim as final

WORKDIR /github/workspace
ADD https://github.com/unlimitedbacon/stl-thumb/releases/download/v0.5.0/stl-thumb_0.5.0_amd64.deb /tmp
RUN apt-get update && apt-get install -y --no-install-recommends git libadmesh-dev /tmp/stl-thumb_0.5.0_amd64.deb && rm -rf /var/cache/apt/archives /var/lib/apt/lists
RUN rm /tmp/stl-thumb_0.5.0_amd64.deb

COPY --from=builder /app /app

ENV PYTHONPATH="${PYTHONPATH}:/app"
ENV GITHUB_STEP_SUMMARY=/dev/null
ENV GITHUB_OUTPUT=/dev/null

ENV PATH="/app/.venv/bin:${PATH}"
CMD ["echo" "$PATH"]