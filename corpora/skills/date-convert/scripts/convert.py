"""Convert one UTC timestamp to a Unix epoch and a weekday."""

import sys
from datetime import UTC, datetime

moment = datetime.strptime(sys.argv[1], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
print(f"epoch={int(moment.timestamp())} weekday={moment.strftime('%A')}")
