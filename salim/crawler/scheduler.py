"""Container entrypoint: run every registered crawler on the CRON_SCHEDULE.

Runs one crawl cycle immediately on startup (so we don't wait for the first
cron tick), then hands off to a blocking scheduler for subsequent runs.
"""
import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

import orchestrator

log = logging.getLogger("salim.crawler.scheduler")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    schedule = os.environ.get("CRON_SCHEDULE", "0 */6 * * *")

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(orchestrator.run, CronTrigger.from_crontab(schedule))
    log.info("crawler scheduled: '%s' (UTC)", schedule)

    # Kick off one run on startup instead of waiting for the first tick.
    try:
        orchestrator.run()
    except Exception:
        log.exception("initial crawl failed")

    scheduler.start()


if __name__ == "__main__":
    main()
