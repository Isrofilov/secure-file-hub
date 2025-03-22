FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create upload directory
RUN mkdir -p uploads && chmod 777 uploads

EXPOSE 8000

# Run with gunicorn for production
CMD ["gunicorn", "--workers", "1", "--threads", "4",  "--bind", "0.0.0.0:8000", "app:app"]