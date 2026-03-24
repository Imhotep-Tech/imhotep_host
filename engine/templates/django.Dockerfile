FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/

RUN pip install --no-cache-dir -r requirements.txt gunicorn whitenoise

COPY . /app/

EXPOSE 8000

CMD ["sh", "-c", "python /app/templates_utils/Django.py; python manage.py makemigrations --noinput || true; python manage.py migrate --run-syncdb --noinput && python manage.py collectstatic --noinput && gunicorn --bind 0.0.0.0:8000 ${WSGI_MODULE:-imhotep_finance.wsgi}:application"]