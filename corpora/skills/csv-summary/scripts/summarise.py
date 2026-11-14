"""Sum and average one numeric column of a CSV file."""

import csv
import sys

path, column = sys.argv[1], sys.argv[2]
with open(path, newline="", encoding="utf-8") as handle:
    values = [int(row[column]) for row in csv.DictReader(handle)]
print(f"rows={len(values)} sum={sum(values)} mean={sum(values) // len(values)}")
