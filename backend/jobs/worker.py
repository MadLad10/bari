"""Background worker: `python -m jobs.worker`. Runs as the `worker` service in docker-compose."""
import logging
import signal
import time

from database import SessionLocal
from jobs.queue import claim_next, run_job
import jobs.handlers  # noqa: F401  registers handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bari.worker")
_stop = False


def _shutdown(*_):
    global _stop
    _stop = True


def main(poll_s: float = 1.0) -> None:
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    log.info("worker started")
    while not _stop:
        db = SessionLocal()
        try:
            job = claim_next(db)
            if job is None:
                time.sleep(poll_s)
                continue
            started = time.perf_counter()
            run_job(db, job)
            log.info("job %s %s -> %s in %.2fs", job.id, job.kind, job.status, time.perf_counter() - started)
        except Exception:  # noqa: BLE001
            log.exception("worker loop error")
            time.sleep(poll_s)
        finally:
            db.close()
    log.info("worker stopped")


if __name__ == "__main__":
    main()
