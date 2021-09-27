FROM python:3.7-slim
LABEL maintainer="Italo Santos <italux.santos@gmail.com>"
LABEL description="Sentry Issues & Events Exporter"

WORKDIR /app

COPY helpers/ /app/helpers/
COPY libs/ /app/libs/
COPY exporter.py requirements.txt /app/

RUN pip install -r requirements.txt && apt update -y && apt-get install -y netcat wget

USER nobody

EXPOSE 9790
CMD ["python","/app/exporter.py"]
