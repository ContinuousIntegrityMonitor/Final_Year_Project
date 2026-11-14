"""Convert a whole-number length between km, mi and m (integer millimetres inside)."""

import sys

MILLIMETRES = {"km": 1_000_000, "mi": 1_609_344, "m": 1_000}
value, source, target = int(sys.argv[1]), sys.argv[2], sys.argv[3]
print(f"{value} {source} = {value * MILLIMETRES[source] // MILLIMETRES[target]} {target}")
