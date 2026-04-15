#!/bin/bash

# Install dependencies
pip install -r requirements.txt

# Collect static files
python manage.py collectstatic --noinput

# Run migrations (only works if a remote DB is configured in env vars)
python manage.py migrate
