import logging
from os import getenv
from wsgiref.simple_server import make_server
import time, traceback, threading


from flask import Flask
from prometheus_client.core import REGISTRY
from prometheus_client import make_wsgi_app, start_http_server, write_to_textfile
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.serving import run_simple

from helpers.prometheus import SentryCollector, clean_registry
from libs.sentry import SentryAPI


DEFAULT_BASE_URL = "https://sentry.io/api/0/"
BASE_URL = getenv("SENTRY_BASE_URL") or DEFAULT_BASE_URL
AUTH_TOKEN = getenv("SENTRY_AUTH_TOKEN")
ORG_SLUG = getenv("SENTRY_EXPORTER_ORG")
PROJECTS_SLUG = getenv("SENTRY_EXPORTER_PROJECTS")
LOG_LEVEL = getenv("LOG_LEVEL", "DEBUG")
QUERY_SENTRY_EVERY_SECONDS = int(getenv("QUERY_SENTRY_EVERY_SECONDS", "300"))
METRICS_FILE = '/tmp/sentry.prom'

log = logging.getLogger("exporter")
level = logging.getLevelName(LOG_LEVEL)
logging.basicConfig(
    level=logging.getLevelName(level),
    format="%(asctime)s - %(process)d - %(levelname)s - %(name)s - %(message)s",
)

app = Flask(__name__)


def every(delay, task):
  next_time = time.time() + delay
  while True:
    time.sleep(max(0, next_time - time.time()))
    try:
      task()
    except Exception as e:
      traceback.print_exc()
      log.exception(f"Problem while executing repetitive task: {e}")
    next_time += (time.time() - next_time) // delay * delay + delay

def get_metric_config():
    """Get metric scraping options."""
    scrape_issue_metrics = getenv("SENTRY_SCRAPE_ISSUE_METRICS") or "True"
    scrape_events_metrics = getenv("SENTRY_SCRAPE_EVENT_METRICS") or "True"
    default_for_time_metrics = "True" if scrape_issue_metrics == "True" else "False"
    get_1h_metrics = getenv("SENTRY_ISSUES_1H") or default_for_time_metrics
    get_24h_metrics = getenv("SENTRY_ISSUES_24H") or default_for_time_metrics
    get_14d_metrics = getenv("SENTRY_ISSUES_14D") or default_for_time_metrics
    return [
        scrape_issue_metrics,
        scrape_events_metrics,
        get_1h_metrics,
        get_24h_metrics,
        get_14d_metrics,
    ]


@app.route("/")
def hello_world():
    return "<h1>Sentry Issues & Events Exporter</h1>\
    <h3>Go to <a href=/metrics/>/metrics</a></h3>\
    "

def collect_metrics():
    sentry = SentryAPI(BASE_URL, AUTH_TOKEN)
    log.info("exporter: cleaning registry collectors...")
    clean_registry()
    REGISTRY.register(SentryCollector(sentry, ORG_SLUG, get_metric_config(), PROJECTS_SLUG))
    write_to_textfile(METRICS_FILE, REGISTRY)

@app.route("/metrics/")
def return_metrics():
    try:
        with open(METRICS_FILE) as file:
            return(file.read(), 200)
    except Exception as e:
        log.debug("Metrics file missing! Returning empty response")
        return('', 204)
        # exporter = DispatcherMiddleware(app.wsgi_app, {"/metrics": make_wsgi_app()})
        # return exporter


if __name__ == "__main__":

    if not ORG_SLUG or not AUTH_TOKEN:
        log.error("ENVs: SENTRY_AUTH_TOKEN or SENTRY_EXPORTER_ORG was not found!")
        exit(1)


    threading.Thread(target=lambda: collect_metrics()).start()
    threading.Thread(target=lambda: every(QUERY_SENTRY_EVERY_SECONDS, collect_metrics)).start()

    log.info("Starting simple wsgi server...")
    # The binding port was picked from the Default port allocations documentation:
    # https://github.com/prometheus/prometheus/wiki/Default-port-allocations
    run_simple(hostname="0.0.0.0", port=9790, application=app.wsgi_app)

