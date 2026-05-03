import subprocess
import time
from datetime import datetime

SPIDERS = [
    "vnexpress",
    "dantri",
    "thanhnien",
    "vietnamnet",
    "baomoi",
    "kenh14",
]

INTERVAL_SECONDS = 300  # 5 phút

while True:
    print(f"\n===== Crawl cycle started at {datetime.now()} =====")

    for spider in SPIDERS:
        print(f"\n>>> Running spider: {spider}")
        subprocess.run(["scrapy", "crawl", spider], check=False)

    print(f"\n===== Crawl cycle finished. Sleeping {INTERVAL_SECONDS}s =====")
    time.sleep(INTERVAL_SECONDS)