#!/usr/bin/env python3
"""Lab 10 Pipeline Health Gate helper: build success rate of this Jenkins job from Prometheus.

Reads PROM_URL, JOB_NAME, HEALTH_WINDOW from the environment and prints exactly one line:
    HEALTH status=ok     success=<n> total=<n> rate=<percent>
    HEALTH status=nodata success=<n|None> total=<n|None>
Exits non-zero (message on stderr) if Prometheus is unreachable or answers with an error -- the gate
must fail then; a monitoring outage is never read as a healthy pipeline.

The Jenkins counters are sparse, so rate()/increase() under-count them (a 0 -> 1 step is invisible to
increase(); measured on this setup). The exact count of builds in the window is the difference between now
and WINDOW ago; a series that did not exist WINDOW ago counts as 0.
"""
import json
import os
import sys
import urllib.parse
import urllib.request

prom, job, window = os.environ["PROM_URL"], os.environ["JOB_NAME"], os.environ["HEALTH_WINDOW"]


def delta(metric):
    sel = metric + '{jenkins_job="' + job + '"}'
    q = "sum(" + sel + ") - (sum(" + sel + " offset " + window + ") or vector(0))"
    url = prom + "/api/v1/query?" + urllib.parse.urlencode({"query": q})
    try:
        body = json.load(urllib.request.urlopen(url, timeout=10))
    except Exception as e:  # unreachable, HTTP error (bad window -> 400), bad JSON
        sys.exit("Prometheus query failed (%s): %s" % (type(e).__name__, e))
    if body.get("status") != "success":
        sys.exit("Prometheus returned status=%r" % body.get("status"))
    res = body["data"]["result"]
    return float(res[0]["value"][1]) if res else None


ok = delta("default_jenkins_builds_success_build_count_total")
total = delta("default_jenkins_builds_total_build_count_total")
# The success counter only exists after the first successful build (measured: total=1, success series absent after one
# failed build). Builds were counted but none succeeded => 0 successes (0%), not "no data".
if total is not None and total > 0 and ok is None:
    ok = 0.0
if total is None or ok is None or total <= 0:
    print("HEALTH status=nodata success=%s total=%s" % (ok, total))
else:
    print("HEALTH status=ok success=%d total=%d rate=%.1f" % (ok, total, 100.0 * ok / total))
