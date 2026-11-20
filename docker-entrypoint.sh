#!/bin/sh
# Apply database migrations, optionally load demo data, then start the server.
set -e

echo "Applying database migrations..."
flask db upgrade

if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
    echo "Loading demo seed data and simulated scenarios..."
    flask seed
fi

exec "$@"
