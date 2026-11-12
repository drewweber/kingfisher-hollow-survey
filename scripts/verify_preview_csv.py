#!/usr/bin/env python3
"""Allow only the public, content-addressed moth frequency aggregate in previews."""
import csv
from datetime import date
import hashlib
import io
from pathlib import Path
import re


COLUMNS = ['date', 'once', 'twice', 'three_plus', 'total']


def verify(public):
    count = 0
    for path in Path(public).rglob('*'):
        if not path.is_file() or path.suffix.lower() != '.csv':
            continue
        relative = path.relative_to(public).as_posix()
        match = re.fullmatch(r'assets/moth-frequency-([0-9a-f]{16})\.csv', relative)
        if not match or path.is_symlink():
            raise ValueError(f'CSV is not an allowed public aggregate: {relative}')
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest()[:16] != match[1]:
            raise ValueError(f'CSV content hash mismatch: {relative}')
        rows = csv.reader(io.StringIO(content.decode('utf-8')), strict=True)
        if next(rows, None) != COLUMNS:
            raise ValueError(f'Unexpected aggregate columns: {relative}')
        previous = None
        for row in rows:
            if len(row) != len(COLUMNS):
                raise ValueError(f'Unexpected aggregate row shape: {relative}')
            day = date.fromisoformat(row[0])
            if day.isoformat() != row[0] or (previous is not None and day <= previous):
                raise ValueError(f'Aggregate dates must be chronological ISO dates: {relative}')
            if not all(re.fullmatch(r'0|[1-9][0-9]*', value) for value in row[1:]):
                raise ValueError(f'Aggregate counts must be nonnegative integers: {relative}')
            once, twice, three_plus, total = map(int, row[1:])
            if once + twice + three_plus != total:
                raise ValueError(f'Aggregate categories must sum to total: {relative}')
            previous = day
        count += 1
    return count


if __name__ == '__main__':
    print(f'Validated {verify(Path("public"))} public frequency CSV aggregates; no other CSVs allowed.')
