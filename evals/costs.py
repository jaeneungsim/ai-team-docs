#!/usr/bin/env python3
"""What the deployed stack costs: one sync run, one search, and a month.

Measured, from CloudWatch: the billed Lambda time of every run (cold starts included), whether a
sync run changed anything, its embedding tokens, and the log bytes the functions wrote. Counted
from the code: the DynamoDB, S3 and KMS requests of a run (see `requests_per_run`). Priced with
the AWS Price List API for Sydney, at the highest tier and before any free tier. A month is the
10-minute schedule plus the edits and searches you pass:

    AWS_PROFILE=<sso-profile> .venv/bin/python evals/costs.py --edits 100 --searches 1000

Results go to evals/results/costs.json and .md. The Logs Insights queries scan well under 1 MB.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
from common import RESULTS, stack_outputs

MEMORY_GB = 512 / 1024  # both functions
RUNS_PER_MONTH = 6 * 24 * 30  # rate(10 minutes) for 30 days
QUESTION_TOKENS = 25  # about a 20-word question; the search function does not log its embedding tokens
LOG_RETENTION_DAYS = 14
PRICES = {  # name: (service code, usage type) in the Price List API, Sydney
    "lambda_gb_s": ("AWSLambda", "APS2-Lambda-GB-Second-ARM"),
    "lambda_request": ("AWSLambda", "APS2-Request-ARM"),
    "dynamodb_read": ("AmazonDynamoDB", "APS2-ReadRequestUnits"),
    "dynamodb_write": ("AmazonDynamoDB", "APS2-WriteRequestUnits"),
    "s3_put": ("AmazonS3", "APS2-Requests-Tier1"),
    "s3_get": ("AmazonS3", "APS2-Requests-Tier2"),
    "s3_gb_month": ("AmazonS3", "APS2-TimedStorage-ByteHrs"),
    "kms_request": ("awskms", "ap-southeast-2-KMS-Requests"),
    "titan_1k_tokens": ("AmazonBedrock", "APS2-TitanEmbeddingV2-Text-input-tokens"),
    "logs_ingest_gb": ("AmazonCloudWatch", "APS2-DataProcessing-Bytes"),
    "logs_gb_month": ("AmazonCloudWatch", "APS2-TimedStorage-ByteHrs"),
    "schedule_invocation": ("AWSEvents", "APS2-ScheduledInvocation"),
}
REPORTS = (
    'filter type = "platform.report" | fields record.requestId as rid, '
    "record.metrics.billedDurationMs as billed, record.metrics.initDurationMs as init"
)
SYNC_LINES = (
    'filter message = "sync" | fields requestId as rid, result.build as build, '
    "result.embedding_tokens as tokens, result.created as created, result.updated as updated, "
    "result.removed as removed"
)
SEARCH_LINES = 'filter message = "search" | fields requestId as rid, method'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--edits", type=int, default=100, help="sync runs a month that change one page")
    parser.add_argument("--searches", type=int, default=1000, help="searches a month")
    parser.add_argument("--days", type=float, default=3, help="how far back to read the logs")
    parser.add_argument("--stack", default="team-docs")
    parser.add_argument("--region", default="ap-southeast-2")
    args = parser.parse_args()

    session = boto3.Session(region_name=args.region)
    outputs = stack_outputs(session, args.stack)
    groups = log_groups(session, args.stack)
    end = datetime.now(UTC)
    start = end - timedelta(days=args.days)
    prices = {name: price(session, *key) for name, key in PRICES.items()}

    sync_runs = joined(session, groups["SyncLogs"], SYNC_LINES, start, end)
    unchanged = [run for run in sync_runs if not run.get("build")]
    one_page = [run for run in sync_runs if run.get("build") and pages_changed(run) == 1]
    all_searches = joined(session, groups["SearchLogs"], SEARCH_LINES, start, end)
    searches = [run for run in all_searches if run.get("method") == "hybrid"]  # what the MCP tool asks for
    log_bytes = {name: incoming_bytes(session, group, start, end) for name, group in groups.items()}
    sizes = item_sizes(session, outputs["TableName"])
    requests = requests_per_run(**sizes)

    sync_log = log_bytes["SyncLogs"] / max(len(sync_runs), 1)
    search_log = log_bytes["SearchLogs"] / max(len(all_searches), 1)
    cold_loads = sum(1 for run in searches if run.get("init")) / max(len(searches), 1)
    units = {
        "sync run, nothing changed": unit(unchanged, requests["sync, unchanged"], 0, sync_log, prices, scheduled=True),
        "sync run, one page changed": unit(
            one_page,
            requests["sync, one page changed"],
            statistics.mean(float(run.get("tokens") or 0) for run in one_page) if one_page else 0,
            sync_log,
            prices,
            scheduled=True,
        ),
        "search": unit(
            searches,
            requests["search"] | {"s3_get": 2 * cold_loads},  # a new container downloads the index: two GETs
            QUESTION_TOKENS,
            search_log,
            prices,
            scheduled=False,
        ),
    }
    bucket_gb = bucket_bytes(session, outputs["BucketName"]) / 1e9
    stored_logs_gb = stored_log_bytes(session, groups, args.stack) / 1e9
    month = {
        "sync runs, nothing changed": (RUNS_PER_MONTH - args.edits, units["sync run, nothing changed"]["usd"]),
        "sync runs, one page changed": (args.edits, units["sync run, one page changed"]["usd"]),
        "searches": (args.searches, units["search"]["usd"]),
        f"S3 storage ({bucket_gb * 1000:.1f} MB)": (1, bucket_gb * prices["s3_gb_month"]),
        f"log storage, {LOG_RETENTION_DAYS} days ({stored_logs_gb * 1000:.1f} MB)": (
            1,
            stored_logs_gb * prices["logs_gb_month"],
        ),
    }
    report = {
        "run_at": end.isoformat(timespec="seconds"),
        "window": {"from": start.isoformat(timespec="seconds"), "to": end.isoformat(timespec="seconds")},
        "measured": {
            "sync_runs": len(sync_runs),
            "unchanged_runs": len(unchanged),
            "one_page_runs": len(one_page),
            "searches": len(all_searches),
            "hybrid_searches": len(searches),
            "log_bytes_per_sync_run": round(sync_log),
            "log_bytes_per_search": round(search_log),
        },
        "prices_usd": prices,
        "requests_per_run": requests,
        "units": units,
        "month": {
            "edits": args.edits,
            "searches": args.searches,
            "rows": {name: {"count": count, "usd": count * usd} for name, (count, usd) in month.items()},
            "total_usd": sum(count * usd for count, usd in month.values()),
        },
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "costs.json").write_text(json.dumps(report, indent=2) + "\n")
    (RESULTS / "costs.md").write_text(markdown(report))
    print(markdown(report))


def price(session: Any, service: str, usage_type: str) -> float:
    """The highest unit price for the usage type: the first tier, before any free tier."""
    pricing = boto3.Session(profile_name=session.profile_name, region_name="us-east-1").client("pricing")
    found = []
    for page in pricing.get_paginator("get_products").paginate(
        ServiceCode=service, Filters=[{"Type": "TERM_MATCH", "Field": "usagetype", "Value": usage_type}]
    ):
        for raw in page["PriceList"]:
            for term in json.loads(raw)["terms"].get("OnDemand", {}).values():
                found += [float(dim["pricePerUnit"]["USD"]) for dim in term["priceDimensions"].values()]
    if not found:
        raise SystemExit(f"no price for {service} {usage_type}")
    return max(found)


def log_groups(session: Any, stack: str) -> dict[str, str]:
    resources = session.client("cloudformation").describe_stack_resources(StackName=stack)["StackResources"]
    groups = {}
    for resource in resources:
        if resource["ResourceType"] == "AWS::Logs::LogGroup":
            for name in ("SyncLogs", "SearchLogs"):
                if resource["LogicalResourceId"].startswith(name):
                    groups[name] = resource["PhysicalResourceId"]
    return groups


def insights(session: Any, group: str, query: str, start: datetime, end: datetime) -> list[dict[str, str]]:
    logs = session.client("logs")
    query_id = logs.start_query(
        logGroupName=group,
        startTime=int(start.timestamp()),
        endTime=int(end.timestamp()),
        queryString=query,
        limit=10000,
    )["queryId"]
    while True:
        answer = logs.get_query_results(queryId=query_id)
        if answer["status"] not in ("Scheduled", "Running"):
            break
        time.sleep(1)
    if answer["status"] != "Complete":
        raise SystemExit(f"Logs Insights query {answer['status']} on {group}")
    return [{field["field"]: field["value"] for field in row} for row in answer["results"]]


def joined(session: Any, group: str, lines: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
    """The app's own line for each invocation, with the billed time from the platform report."""
    reports = {row["rid"]: row for row in insights(session, group, REPORTS, start, end) if "rid" in row}
    runs = []
    for row in insights(session, group, lines, start, end):
        report = reports.get(row.get("rid", ""))
        if report is not None:
            runs.append(row | {"billed": float(report["billed"]), "init": report.get("init")})
    return runs


def pages_changed(run: dict[str, Any]) -> int:
    return sum(int(run.get(key) or 0) for key in ("created", "updated", "removed"))


def incoming_bytes(session: Any, group: str, start: datetime, end: datetime) -> float:
    points = session.client("cloudwatch").get_metric_statistics(
        Namespace="AWS/Logs",
        MetricName="IncomingBytes",
        Dimensions=[{"Name": "LogGroupName", "Value": group}],
        StartTime=start,
        EndTime=end,
        Period=3600,
        Statistics=["Sum"],
    )["Datapoints"]
    return sum(point["Sum"] for point in points)


def item_sizes(session: Any, table: str) -> dict[str, int]:
    """Rough DynamoDB sizes: the JSON of the PAGE items and of the STATE item."""
    pages = session.resource("dynamodb").Table(table)
    items: list[dict[str, Any]] = []
    query: dict[str, Any] = {"KeyConditionExpression": "pk = :pk", "ExpressionAttributeValues": {":pk": "PAGE"}}
    while True:
        answer = pages.query(**query)
        items.extend(answer["Items"])
        if "LastEvaluatedKey" not in answer:
            break
        query["ExclusiveStartKey"] = answer["LastEvaluatedKey"]
    state = pages.get_item(Key={"pk": "STATE", "sk": "STATE"})["Item"]
    return {
        "page_bytes": sum(len(json.dumps(item, default=str)) for item in items),
        "state_bytes": len(json.dumps(state, default=str)),
        "pages": len(items),
    }


def requests_per_run(page_bytes: int, state_bytes: int, pages: int) -> dict[str, dict[str, float]]:
    """DynamoDB, S3 and KMS requests of one run, counted from src/team_docs/sync.py and handlers.py.

    Consistent reads cost one read unit per 4 KB, writes one write unit per 1 KB. Every sync run
    takes and releases the lock, reads the STATE item and all PAGE items, writes the STATE item,
    and decrypts the token (one KMS request; the two SSM reads of standard parameters are free).
    """
    query = math.ceil(page_bytes / 4096)
    state_read, state_write = math.ceil(state_bytes / 4096), math.ceil(state_bytes / 1024)
    page_write = math.ceil(page_bytes / max(pages, 1) / 1024)
    unchanged = {"dynamodb_read": state_read + query, "dynamodb_write": 1 + state_write + 1, "kms_request": 1}
    # One changed page also: writes its four files and its item, reads its old chunks and vectors,
    # tags the old version's four files, reads every page's chunks and vectors again to build the
    # index (a second PAGE query), uploads the two index files and tags the old index's two files.
    changed = {
        "dynamodb_read": state_read + 2 * query,
        "dynamodb_write": 1 + page_write + state_write + 1,
        "kms_request": 1,
        "s3_put": 4 + 4 + 2 + 2,
        "s3_get": 2 + 2 * pages,
    }
    return {"sync, unchanged": unchanged, "sync, one page changed": changed, "search": {"dynamodb_read": state_read}}


def unit(
    runs: list[dict[str, Any]],
    requests: dict[str, float],
    tokens: float,
    log_bytes: float,
    prices: dict[str, float],
    *,
    scheduled: bool,
) -> dict[str, Any]:
    """The cost of one run of this kind, from its mean billed time and its requests."""
    billed = [run["billed"] for run in runs] or [0.0]
    parts = {
        "lambda": statistics.mean(billed) / 1000 * MEMORY_GB * prices["lambda_gb_s"] + prices["lambda_request"],
        "requests": sum(count * prices[name] for name, count in requests.items()),
        "embeddings": tokens / 1000 * prices["titan_1k_tokens"],
        "logs": log_bytes / 1e9 * prices["logs_ingest_gb"],
        "schedule": prices["schedule_invocation"] if scheduled else 0.0,
    }
    return {
        "runs": len(runs),
        "billed_ms": {
            "median": statistics.median(billed),
            "mean": round(statistics.mean(billed)),
            "max": max(billed),
        },
        "cold_starts": sum(1 for run in runs if run.get("init")),
        "embedding_tokens": round(tokens),
        "parts_usd": parts,
        "usd": sum(parts.values()),
    }


def bucket_bytes(session: Any, bucket: str) -> int:
    pages = session.client("s3").get_paginator("list_objects_v2").paginate(Bucket=bucket)
    return sum(item["Size"] for page in pages for item in page.get("Contents", []))


def stored_log_bytes(session: Any, groups: dict[str, str], stack: str) -> float:
    """Log storage once the retention is full: what is stored now, scaled to the retention period."""
    created = session.client("cloudformation").describe_stacks(StackName=stack)["Stacks"][0]["CreationTime"]
    days = max((datetime.now(UTC) - created).total_seconds() / 86400, 1)
    logs = session.client("logs")
    found = [logs.describe_log_groups(logGroupNamePrefix=group)["logGroups"][0] for group in groups.values()]
    return sum(group.get("storedBytes", 0) for group in found) * max(LOG_RETENTION_DAYS / days, 1)


def money(usd: float) -> str:
    return f"${usd:.4f}" if usd >= 0.0001 else f"${usd:.6f}"


def markdown(report: dict[str, Any]) -> str:
    measured, units, month = report["measured"], report["units"], report["month"]
    lines = [
        f"# Cost, {report['run_at'][:10]}",
        "",
        f"Measured from CloudWatch between {report['window']['from'][:16]} and {report['window']['to'][:16]} UTC: "
        f"{measured['sync_runs']} sync runs ({measured['unchanged_runs']} with nothing to do, "
        f"{measured['one_page_runs']} that changed one page) and {measured['hybrid_searches']} hybrid searches, "
        f"the kind the MCP tool makes ({measured['searches'] - measured['hybrid_searches']} keyword searches "
        "from the freshness probe are left out). DynamoDB, S3 and KMS requests are counted from the code. "
        "Prices are Sydney list prices from the AWS Price List API, at the highest tier and before any free tier.",
        "",
        "| Unit of work | Runs measured | Billed ms (median / mean / max) | Cold starts | Cost per 1,000 |",
        "|---|---|---|---|---|",
    ]
    for name, value in units.items():
        ms = value["billed_ms"]
        lines.append(
            f"| {name} | {value['runs']} | {ms['median']:.0f} / {ms['mean']} / {ms['max']:.0f} | "
            f"{value['cold_starts']} | {money(value['usd'] * 1000)} |"
        )
    lines += [
        "",
        f"A month: the 10-minute schedule, {month['edits']} edits and {month['searches']} searches.",
        "",
        "| Item | Count | Cost |",
        "|---|---|---|",
    ]
    for name, row in month["rows"].items():
        lines.append(f"| {name} | {row['count']:,} | {money(row['usd'])} |")
    lines.append(f"| total | | {money(month['total_usd'])} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
