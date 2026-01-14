FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["sh", "-c", "python manage.py collectstatic --noinput && python manage.py migrate --noinput && python manage.py load_initial_data && python manage.py sync_workout_to_templates && python manage.py recalculate_task_priorities && gunicorn config.wsgi --bind 0.0.0.0:8000 --preload --log-file -"]
