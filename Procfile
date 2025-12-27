web: python manage.py migrate --noinput && python manage.py collectstatic --noinput && python manage.py create_superuser_from_env && gunicorn config.wsgi --log-file -
