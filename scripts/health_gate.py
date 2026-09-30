#!/usr/bin/env python3
"""Lab 10 Pipeline Health Gate helper: rolling build success rate of this Jenkins job over its LAST N BUILDS.

Reads HEALTH_RESULTS (comma separated results of the most recent COMPLETED builds, newest first, produced by the
Jenkinsfile from the job's own build history) and HEALTH_BUILDS (N, default 20). Prints exactly one line:
    HEALTH status=ok     builds=<n> of <N> success=<s> total=<n> rate=<percent>
    HEALTH status=nodata builds=0 of <N>
Exits non-zero (message on stderr) on unusable input -- the gate must fail then, never read it as healthy.

Why Jenkins build history and not Prometheus: the Jenkins Prometheus counters (..._build_count_total) restart at 0
with every Jenkins restart and have no per-build information (measured: 2 builds counted while the job has 61), so
"the last 20 builds" cannot be derived from them. The build history is the authoritative per-build record.

Counting rules (documented so the number is reproducible):
  * SUCCESS counts as a success; FAILURE and UNSTABLE count as not successful.
  * ABORTED / NOT_BUILT / still-running builds are not health signals and are skipped (the Jenkinsfile does this).
  * Fewer than N builds: all available builds are used and reported as "<n> of <N>".
  * Zero builds: status=nodata (explicit warning in the Jenkinsfile), never a fake 100%.
"""
import os
import sys

VALID = {"SUCCESS", "UNSTABLE", "FAILURE"}

n_max = int(os.environ.get("HEALTH_BUILDS", "20"))
raw = os.environ.get("HEALTH_RESULTS")
if raw is None:
    sys.exit("HEALTH_RESULTS is not set")
results = [r.strip() for r in raw.split(",") if r.strip()]
bad = [r for r in results if r not in VALID]
if bad:
    sys.exit("unexpected build result(s): %s" % ",".join(sorted(set(bad))))
results = results[:n_max]

if not results:
    print("HEALTH status=nodata builds=0 of %d" % n_max)
else:
    ok = sum(1 for r in results if r == "SUCCESS")
    total = len(results)
    print("HEALTH status=ok builds=%d of %d success=%d total=%d rate=%.1f" % (total, n_max, ok, total, 100.0 * ok / total))
