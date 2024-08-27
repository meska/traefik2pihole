FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install poetry
RUN poetry install
COPY . .
CMD ["poetry", "run","python","traefik2pihole.py"]
