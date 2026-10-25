import argparse
import logging
from contextlib import contextmanager
from datetime import date, timedelta

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import engine
from app.sync import backfill_day, enqueue_history, sync_latest, worker


@contextmanager
def migration_lock():
    with engine().connect() as connection:
        postgres = connection.dialect.name == "postgresql"
        if postgres:
            connection.execute(text("SELECT pg_advisory_lock(714004)"))
            connection.commit()
        try:
            yield
        finally:
            if postgres:
                connection.execute(text("SELECT pg_advisory_unlock(714004)"))
                connection.commit()


def migrate():
    with migration_lock():
        command.upgrade(Config("alembic.ini"), "head")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="GridBricks data and operations commands")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate")
    commands.add_parser("worker")
    commands.add_parser("sync")
    commands.add_parser("demo")
    backfill = commands.add_parser("backfill")
    backfill.add_argument("--start", type=date.fromisoformat, required=True)
    backfill.add_argument("--end", type=date.fromisoformat, required=True)
    backfill.add_argument("--enqueue", action="store_true")
    args = parser.parse_args()
    if args.command == "migrate":
        migrate()
    elif args.command == "worker":
        migrate()
        worker()
    elif args.command == "sync":
        sync_latest()
    elif args.command == "demo":
        with Session(engine()) as session:
            count = enqueue_history(session, date(2025, 12, 1), date(2026, 2, 1))
            session.commit()
        print(
            f"Queued {count} daily imports for January decisions and boundary records. Run the worker to process them."
        )
    elif args.command == "backfill":
        if args.start > args.end:
            parser.error("--start must be on or before --end")
        if args.enqueue:
            with Session(engine()) as session:
                count = enqueue_history(session, args.start, args.end)
                session.commit()
            print(f"Queued {count} daily imports")
        else:
            day = args.start
            while day <= args.end:
                backfill_day(day)
                print(f"Imported {day}", flush=True)
                day += timedelta(days=1)


if __name__ == "__main__":
    main()
