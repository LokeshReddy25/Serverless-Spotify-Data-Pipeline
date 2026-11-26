"""Start the Glue crawler (one command), optionally waiting for it to finish.

Usage: python -m infra.run_crawler [--wait] [--timeout SECONDS]

Run it after the pipeline has written Parquet files to transformed_data/; with --wait it prints
the crawl result and the tables in the Glue database.
"""
import argparse
import time

from infra import config

POLL_INTERVAL_S = 15


def start_crawler(glue):
    try:
        glue.start_crawler(Name=config.GLUE_CRAWLER)
        print(f"Started crawler {config.GLUE_CRAWLER}.")
        return True
    except glue.exceptions.CrawlerRunningException:
        print(f"Crawler {config.GLUE_CRAWLER} is already running.")
        return False


def wait_for_crawler(glue, timeout_s=900, poll_interval_s=None):
    """Poll until the crawler is READY again; return its last crawl status (e.g. SUCCEEDED)."""
    interval = POLL_INTERVAL_S if poll_interval_s is None else poll_interval_s
    deadline = time.monotonic() + timeout_s
    while True:
        crawler = glue.get_crawler(Name=config.GLUE_CRAWLER)["Crawler"]
        if crawler["State"] == "READY":
            break
        if time.monotonic() > deadline:
            raise SystemExit(f"ERROR: crawler still {crawler['State']} after {timeout_s}s.")
        time.sleep(interval)

    last = crawler.get("LastCrawl", {})
    status = last.get("Status", "UNKNOWN")
    print(f"Crawler finished: {status}")
    if last.get("ErrorMessage"):
        print(f"  Error: {last['ErrorMessage']}")
    tables = [t["Name"] for t in glue.get_tables(DatabaseName=config.GLUE_DATABASE)["TableList"]]
    print(f"Tables in {config.GLUE_DATABASE}: {', '.join(tables) or '(none)'}")
    return status


def main(argv=None):
    parser = argparse.ArgumentParser(description="Start the Glue crawler")
    parser.add_argument("--wait", action="store_true", help="Wait for the crawl to finish")
    parser.add_argument("--timeout", type=int, default=900, help="Seconds to wait with --wait (default 900)")
    args = parser.parse_args(argv)
    glue = config.get_session().client("glue")
    start_crawler(glue)
    if args.wait:
        status = wait_for_crawler(glue, args.timeout)
        if status != "SUCCEEDED":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
