"""Create a fresh demo DB from public questions, refusing to overwrite any data."""
import argparse
import json
import sqlite3
from pathlib import Path


def create_database(target):
    target = Path(target).resolve()
    if target.exists():
        raise FileExistsError(f'Refusing to overwrite existing database: {target}')
    bank = json.loads((Path(__file__).parent / 'question_bank.json').read_text(encoding='utf-8'))
    target.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(target)
    try:
        for statement in bank['schema']:
            db.execute(statement)
        for table in ('courses', 'questions'):
            for row in bank[table]:
                columns = ','.join('"' + col + '"' for col in row)
                db.execute(f'INSERT INTO {table} ({columns}) VALUES ({",".join("?" for _ in row)})', list(row.values()))
        db.commit()
    finally:
        db.close()
    print('Created clean demo database:', target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[2] / 'bountycoders.db')
    create_database(parser.parse_args().output)
