"""Restores a database backup made by POST /internal/backup (see
app/services/backup.py).

Run from backend/, with the production environment variables (MONGO_URL,
R2_...) set:

    python -m scripts.restore_backup --list
        the available backups

    python -m scripts.restore_backup --date 2026-09-30 --target-db everbook_restore
        copies that backup into a NEW database, to look at it or pick data
        from it: the live database is not touched

    python -m scripts.restore_backup --date 2026-09-30 --target-db <live db> --replace
        replaces the live database's contents with the backup (asks you to
        type the database name to confirm)
"""
import argparse
import os
import sys

from pymongo import MongoClient

from app.services.backup import PREFIX, read_backup
from app.services.storage import list_folders


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="list the backups")
    parser.add_argument("--date", help="backup to restore (YYYY-MM-DD)")
    parser.add_argument("--target-db", help="database to restore into")
    parser.add_argument("--replace", action="store_true", help="empty the target's collections first")
    args = parser.parse_args(argv)

    if args.list:
        for folder in list_folders(PREFIX):
            print(folder[len(PREFIX):].rstrip("/"))
        return 0
    if not args.date or not args.target_db:
        parser.error("--date and --target-db are required (or --list)")

    data = read_backup(args.date)
    target = MongoClient(os.environ["MONGO_URL"])[args.target_db]
    existing = [name for name in data if target[name].estimated_document_count()]
    if existing and not args.replace:
        print(f"{args.target_db} already holds data ({', '.join(existing)}): pick an empty database, or add --replace.")
        return 1
    if args.replace:
        answer = input(f"This replaces the contents of {args.target_db} with the backup of {args.date}. Type the database name to confirm: ")
        if answer.strip() != args.target_db:
            print("Cancelled.")
            return 1
    for name, docs in data.items():
        if args.replace:
            target[name].delete_many({})
        if docs:
            target[name].insert_many(docs)
        print(f"{name}: {len(docs)} documents")
    print(f"Backup of {args.date} restored into {args.target_db}. Indexes are created when the app starts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
