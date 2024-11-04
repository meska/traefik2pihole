FROM python:3.12-slim

# Install cron
RUN apt-get update && apt-get install -y cron && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml .
RUN pip install poetry && poetry install
COPY . .

# Add the cron job and create the log file
RUN echo "0 */3 * * * cd /app && /usr/local/bin/poetry run python traefik2pihole.py >> /var/log/cron.log 2>&1" > /etc/cron.d/traefik2pihole && \
    chmod 0644 /etc/cron.d/traefik2pihole && \
    crontab /etc/cron.d/traefik2pihole && \
    touch /var/log/cron.log

CMD ["sh", "-c", "cron && tail -f /var/log/cron.log"]