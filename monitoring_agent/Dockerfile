FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./app.py

EXPOSE 8502

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8502"]
