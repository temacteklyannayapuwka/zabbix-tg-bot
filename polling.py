import time
import sys


def run_polling(cycle, interval: int) -> int:
    failures = 0
    try:
        while True:
            status = cycle()
            if status == 2:
                failures += 1
                if failures > 3:
                    print("Temporary failure retry limit reached.", file=sys.stderr)
                    return status
                delay = min(interval * 2 ** (failures - 1), 300)
                print(f"Temporary failure; retry {failures}/3 in {delay} seconds.", file=sys.stderr)
                time.sleep(delay)
                continue
            if status != 0:
                return status
            failures = 0
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Polling stopped.", flush=True)
        return 0
