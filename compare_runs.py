"""Quick comparison of scores across multiple evaluation runs in output/."""

import csv
import statistics
from pathlib import Path

output_dir = Path("output")
files = sorted(output_dir.glob("tickets_evaluated_*.csv"))

if len(files) < 2:
    print(f"Found {len(files)} file(s) in output/ — need at least 2 to compare.")
    raise SystemExit(1)

print(f"Comparing {len(files)} runs\n")

# Group scores by ticket (using first 60 chars as key)
tickets: dict[str, dict[str, list[int]]] = {}

for f in files:
    with open(f, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = row["ticket"][:60]
            if key not in tickets:
                tickets[key] = {"content": [], "format": []}
            if row["content_score"]:
                tickets[key]["content"].append(int(row["content_score"]))
            if row["format_score"]:
                tickets[key]["format"].append(int(row["format_score"]))

for ticket_key, scores in tickets.items():
    print(f"Ticket: {ticket_key}...")
    for dim in ("content", "format"):
        vals = scores[dim]
        if len(vals) < 2:
            print(f"  {dim}: not enough data")
            continue
        mean = statistics.mean(vals)
        stdev = statistics.stdev(vals)
        print(f"  {dim}: scores={vals}  mean={mean:.1f}  stdev={stdev:.2f}")
    print()
