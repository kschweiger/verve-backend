#!/bin/sh
set -e

# Configuration (defaults can be overridden by env vars)
DB_HOST=${POSTGRES_SERVER:-db}
DB_PORT=${POSTGRES_PORT:-5432}

echo "--- 🐢 Waiting for Postgres at $DB_HOST:$DB_PORT ---"

# Loop until we can connect to the DB port
# using nc (netcat) which we install in the Dockerfile
while ! nc -z $DB_HOST $DB_PORT; do
  sleep 0.5
done

echo "--- 🚀 Postgres is up! Starting application... ---"

# Run the command passed to docker
exec "$@"
