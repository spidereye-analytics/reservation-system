import sys
import argparse
import time

import uvicorn
from fastapi import FastAPI, Depends, Request
from fastapi_sqlalchemy import DBSessionMiddleware
from prometheus_client import Counter, Histogram
from sqlalchemy import create_engine
from alembic import command
from alembic.config import Config
import os
import logging
from prometheus_fastapi_instrumentator import Instrumentator
from .app.routes import router
from .app.cache_checker import check_and_sync_cache
from .app.models import Base
from .app.dependencies import get_redis_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

app = FastAPI()

# Custom Prometheus metrics for specific routes
ROUTE_REQUEST_COUNT = Counter("route_request_count", "Total number of requests per route", ["method", "endpoint"])
ROUTE_REQUEST_LATENCY = Histogram("route_request_latency_seconds", "Request latency in seconds per route", ["method", "endpoint"])


# Instrument the app with Prometheus metrics
Instrumentator().instrument(app).expose(app, include_in_schema=False, endpoint="/metrics")

# Middleware to track custom metrics
@app.middleware("http")
async def add_metrics(request: Request, call_next):
    start_time = time.time()

    # Process the request
    response = await call_next(request)

    # Update custom metrics
    ROUTE_REQUEST_COUNT.labels(method=request.method, endpoint=request.url.path).inc()
    ROUTE_REQUEST_LATENCY.labels(method=request.method, endpoint=request.url.path).observe(time.time() - start_time)

    return response


# Database configuration: This must be done before accessing db.session anywhere
app.add_middleware(DBSessionMiddleware,
                   db_url=os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/reservation'))

# Include the main router: Ensure this is done after DBSessionMiddleware is added
app.include_router(router)

# Instrument the app with Prometheus metrics
Instrumentator().instrument(app).expose(app, include_in_schema=False, endpoint="/metrics")


def start_server():
    uvicorn.run(app, host="0.0.0.0", port=8000)


def create_tables():
    database_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/reservation')
    print(f"Using database URL: {database_url}")
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    print("Database tables created successfully.")


def run_migrations(action, revision=None, message=None):
    # Inline Alembic configuration
    database_url = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/reservation')

    alembic_cfg = Config()
    alembic_cfg.set_main_option('sqlalchemy.url', database_url)
    alembic_cfg.set_main_option('script_location',
                                'alembic')  # Adjust this if your migrations are in a different directory

    if action == "upgrade":
        command.upgrade(alembic_cfg, "head")
    elif action == "downgrade":
        if not revision:
            print("Please specify a revision to downgrade to.")
            return
        command.downgrade(alembic_cfg, revision)
    elif action == "revision":
        if not message:
            print("Please provide a message for the migration.")
            return
        command.revision(alembic_cfg, autogenerate=True, message=message)
    elif action == "current":
        command.current(alembic_cfg)
    else:
        print("Invalid action specified for migrations.")


def clear_redis_cache():
    redis_client = get_redis_client()
    redis_client.flushall()
    print("Redis cache cleared successfully.")


def main():
    parser = argparse.ArgumentParser(description="Reservation System Application")
    parser.add_argument(
        '--mode',
        type=str,
        choices=['server', 'cache-sync', 'create-tables', 'migrate', 'clear-cache'],
        required=True,
        help="Mode to run the application in. Choices are 'server' to start the FastAPI server, 'cache-sync' to run the cache synchronization, 'create-tables' to create the database tables, 'migrate' to manage database migrations, or 'clear-cache' to clear all Redis caches."
    )

    parser.add_argument(
        '--action',
        type=str,
        choices=['upgrade', 'downgrade', 'revision', 'current'],
        help="Action to perform with Alembic migrations. Required if mode is 'migrate'."
    )

    parser.add_argument(
        '--revision',
        type=str,
        help="Specify the revision for downgrade or other Alembic commands where needed."
    )

    parser.add_argument(
        '--message',
        type=str,
        help="Message to use with the 'revision' action in Alembic."
    )

    args = parser.parse_args()

    if args.mode == 'server':
        start_server()
    elif args.mode == 'cache-sync':
        check_and_sync_cache()
    elif args.mode == 'create-tables':
        create_tables()
    elif args.mode == 'migrate':
        if not args.action:
            print("Please specify an action for the 'migrate' mode.")
        else:
            run_migrations(args.action, args.revision, args.message)
    elif args.mode == 'clear-cache':
        clear_redis_cache()


if __name__ == "__main__":
    main()
