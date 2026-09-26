#!/bin/sh

set -e

echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Starting Gunicorn..."
exec gunicorn autoservice.wsgi:application \
    --bind 0.0.0.0:8000