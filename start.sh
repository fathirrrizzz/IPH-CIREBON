#!/usr/bin/env bash
set -o errexit

gunicorn config.wsgi:application