import csv, collections
from pathlib import Path

dates = ["2026-05-11","2026-05-12","2026-05-13","2026-05-14","2026-05-15","2026-05-16"]
for d in dates:
    f = Path(f"results/{d}.csv")
    if not f.exists():
        print(f"{d}: NOT FOUND")
        continue
    rows = list(csv.DictReader(f.open(encoding="utf-8")))
    images = {}
    for r in rows:
        images[r["result_image_id"]] = r["overall_result"]
    total = len(images)
    ok = sum(1 for v in images.values() if v=="PASS")
    ng = total - ok
    ng_counts = collections.Counter()
    for r in rows:
        if r["result"]=="FAIL":
            ng_counts[r["inspection_name"]] += 1
    print(f"{d}: total={total} OK={ok} NG={ng} | NG={dict(ng_counts)}")
