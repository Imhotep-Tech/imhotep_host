FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/

RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . /app/

EXPOSE 8000

# Run migrations, collect static files, and THEN boot Gunicorn
CMD ["sh", "-c", "python manage.py makemigrations accounts && python manage.py makemigrations && python manage.py migrate && python manage.py collectstatic --noinput && gunicorn --bind 0.0.0.0:8000 imhotep_finance.wsgi:application"]