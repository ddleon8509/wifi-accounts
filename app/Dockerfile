FROM python:3.9
ARG DEFAULT_PORT=32001
WORKDIR /app
COPY requirements.txt .
RUN pip3 install -r requirements.txt
COPY . .
ENV PORT ${DEFAULT_PORT}
EXPOSE $PORT
CMD ["python3","app.py"]