FROM python:3.13-slim
WORKDIR /app
COPY energytool /app/energytool
COPY web /app/web
COPY solution.py requirements.txt /app/
RUN useradd --create-home app && mkdir /app/data && chown app:app /app/data
USER app
ENV HOST=0.0.0.0 PORT=8000 PYTHONUNBUFFERED=1 KB_PATH=/knowledge-base DB_PATH=/app/data/energytool.sqlite3
EXPOSE 8000
CMD ["python", "-m", "energytool.server"]
