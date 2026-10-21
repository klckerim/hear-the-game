FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY htg htg
COPY services services
COPY schemas schemas
COPY web web
COPY data/calibration data/calibration
COPY data/cache data/cache
RUN pip install --no-cache-dir -e ".[azure]"
# The demo match is deterministic from its seed, so it is generated here instead of being committed
RUN python -m htg.generate --seeds 7
ENV HTG_ENV=azure PYTHONUNBUFFERED=1 PORT=8000
EXPOSE 8000
CMD ["python", "-m", "services.engine.serve"]
