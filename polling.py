import time


def run_polling(cycle, interval: int) -> int:
    try:
        while True:
            status = cycle()
            if status != 0:
                return status
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Polling stopped.", flush=True)
        return 0
