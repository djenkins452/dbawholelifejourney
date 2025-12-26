web: gunicorn config.wsgi --log-file -
release: python manage.py migrate --noinput && python manage.py collectstatic --noinput && python manage.py create_superuser_from_env
