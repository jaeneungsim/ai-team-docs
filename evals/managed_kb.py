#!/usr/bin/env python3
"""Retrieval comparison with Amazon Bedrock Managed Knowledge Base, on the same questions.

The managed knowledge base reads the same Confluence space through its own connector and is used
as it comes: managed embeddings, managed reranking and its own chunking. Run the steps in order.
Each step finds its resources by name, so a step that failed can be run again.

    secret    wait for the API token in the clipboard, check it, put it into Secrets Manager;
              it is never printed, and the clipboard is cleared afterwards
    create    the service role, the knowledge base and the Confluence data source
    sync      one ingestion job, waited for
    evaluate  the answerable questions, scored like evals/retrieval.py (top 5, hit@5 and MRR)
    delete    the data source, the knowledge base, the role and the secret

    AWS_PROFILE=<sso-profile> .venv/bin/python evals/managed_kb.py <step> \\
        --site "$CONFLUENCE_SITE" --email "$CONFLUENCE_EMAIL"

The connector takes the site address (https://<site>.atlassian.net) with Basic auth. Atlassian
accepts scoped API tokens only through api.atlassian.com, so the token here has no scopes: give it
the shortest expiry and revoke it after `delete`. Document permissions (ACLs) stay off: with them
on, a search that names no user returns nothing. Results, without the site address, go to
evals/results/managed-kb.json and .md. Retrieval costs $0.001 a query; the secret and the storage
cost cents while the experiment lasts.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import json
import os
import re
import statistics
import subprocess
import time
import urllib.error
import urllib.request
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError
from common import RESULTS, questions, stack_outputs

NAME = "team-docs-kb-experiment"  # the secret, the role and the knowledge base
DATA_SOURCE = "confluence"
TOP_K = 5
SEARCH = {"managedSearchConfiguration": {"numberOfResults": TOP_K, "rerankingModelType": "MANAGED"}}
POLL_SECONDS = 10
CLIPBOARD_SECONDS = 100  # a command run from Claude Code with ! may stop after two minutes
PAGE_ID = re.compile(r"/pages/(\d+)")
METHODS = ("hybrid", "managed KB")  # ours, from evals/results/retrieval.json, and the knowledge base
STEPS = ("secret", "create", "sync", "evaluate", "delete")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("step", choices=STEPS)
    parser.add_argument("--site", default=os.environ.get("CONFLUENCE_SITE"), help="https://<site>.atlassian.net")
    parser.add_argument("--email", default=os.environ.get("CONFLUENCE_EMAIL"))
    parser.add_argument("--space", default="INV")
    parser.add_argument("--stack", default="team-docs", help="stack whose table names the pages")
    parser.add_argument("--region", default="ap-southeast-2")
    parser.add_argument("--dump", type=Path, help="evaluate: write the first raw answer here (it holds the site)")
    args = parser.parse_args()
    if args.step in ("secret", "create") and not args.site:
        parser.error("--site (or CONFLUENCE_SITE) is required")
    if args.step == "secret" and not args.email:
        parser.error("--email (or CONFLUENCE_EMAIL) is required")

    session = boto3.Session(region_name=args.region)
    if args.step == "secret":
        store_secret(session, args.site.rstrip("/"), args.email, args.space)
    elif args.step == "create":
        create(session, args.site.rstrip("/"), args.space)
    elif args.step == "sync":
        sync(session)
    elif args.step == "evaluate":
        evaluate(session, args.stack, args.dump)
    else:
        delete(session)


# --- secret ---------------------------------------------------------------------------------------


def store_secret(session: Any, site: str, email: str, space: str) -> None:
    print(f"Waiting up to {CLIPBOARD_SECONDS} s for the API token: click Copy in the Atlassian dialog now.", flush=True)
    token = token_from_clipboard()
    code = http_status(f"{site}/wiki/api/v2/spaces?keys={space}", email, token)
    print(f"token: {len(token)} characters; the site answers HTTP {code}")
    if code != 200:
        raise SystemExit("The site refused the token. Scoped tokens do not work here: use one without scopes.")
    value = json.dumps({"username": email, "password": token, "hostUrl": site})
    secrets = session.client("secretsmanager")
    try:
        secrets.create_secret(Name=NAME, SecretString=value, Description="Confluence API token, Managed KB experiment")
    except secrets.exceptions.ResourceExistsException:
        secrets.put_secret_value(SecretId=NAME, SecretString=value)
    subprocess.run(["pbcopy"], input="", text=True, check=True)
    print(f"stored as the secret {NAME}; the clipboard is cleared")


def token_from_clipboard() -> str:
    """Wait until the clipboard holds something shaped like an API token.

    Copying the command that runs this step puts the command in the clipboard, so the token is
    copied after the step starts, from the dialog Atlassian shows when it creates the token.
    """
    deadline = time.monotonic() + CLIPBOARD_SECONDS
    while time.monotonic() < deadline:
        text = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True).stdout.strip()
        if len(text) >= 24 and "://" not in text and not any(char.isspace() for char in text):
            return text
        time.sleep(1)
    raise SystemExit(f"No API token in the clipboard after {CLIPBOARD_SECONDS} s. Run this again, then click Copy.")


def http_status(url: str, email: str, token: str) -> int:
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status
    except urllib.error.HTTPError as err:
        return err.code


# --- create ---------------------------------------------------------------------------------------


def create(session: Any, site: str, space: str) -> None:
    account = session.client("sts").get_caller_identity()["Account"]
    secret_arn = session.client("secretsmanager").describe_secret(SecretId=NAME)["ARN"]
    role_arn = service_role(session, account, secret_arn)
    agent = session.client("bedrock-agent")
    kb_id = knowledge_base_id(agent)
    if kb_id is None:
        made = while_the_role_propagates(
            lambda: agent.create_knowledge_base(
                name=NAME,
                description="Experiment: the team space through the managed Confluence connector",
                roleArn=role_arn,
                knowledgeBaseConfiguration={
                    "type": "MANAGED",
                    "managedKnowledgeBaseConfiguration": {"embeddingModelType": "MANAGED"},
                },
            )
        )
        kb_id = made["knowledgeBase"]["knowledgeBaseId"]
    wait_for("knowledge base", lambda: agent.get_knowledge_base(knowledgeBaseId=kb_id)["knowledgeBase"], "ACTIVE")
    if data_source_id(agent, kb_id) is None:
        agent.create_data_source(
            knowledgeBaseId=kb_id,
            name=DATA_SOURCE,
            dataDeletionPolicy="DELETE",
            dataSourceConfiguration={
                "type": "MANAGED_KNOWLEDGE_BASE_CONNECTOR",
                "managedKnowledgeBaseConnectorConfiguration": {
                    "deletionProtectionConfiguration": {
                        "deletionProtectionStatus": "ENABLED",
                        "deletionProtectionThreshold": 15,
                    },
                    "connectorParameters": {
                        "type": "CONFLUENCE",
                        "version": "1",
                        "aclEnabled": False,  # on by default with Basic auth, and fixed once created
                        "connectionConfiguration": {
                            "secretArn": secret_arn,
                            "type": "SAAS",
                            "authType": "BASIC",
                            "hostUrl": site,
                        },
                        "dataEntityConfiguration": {
                            "crawlPage": True,
                            "crawlBlog": False,
                            "crawlPageAttachment": False,
                            "crawlBlogAttachment": False,
                            "crawlArchivedSpace": False,
                            "crawlArchivedPage": False,
                            "crawlPersonalSpace": False,
                        },
                        "filterConfiguration": {"inclusionSpaceKeys": [space]},
                    },
                },
            },
        )
    ds_id = data_source_id(agent, kb_id)
    wait_for(
        "data source",
        lambda: agent.get_data_source(knowledgeBaseId=kb_id, dataSourceId=ds_id)["dataSource"],
        "AVAILABLE",
    )
    print(f"knowledge base {kb_id} is active, data source {ds_id} is available")


def service_role(session: Any, account: str, secret_arn: str) -> str:
    """A role Bedrock can assume for knowledge bases of this account, allowed to read the one secret."""
    iam = session.client("iam")
    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "bedrock.amazonaws.com"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": account},
                    "ArnLike": {"aws:SourceArn": f"arn:aws:bedrock:{session.region_name}:{account}:knowledge-base/*"},
                },
            }
        ],
    }
    try:
        arn = iam.create_role(
            RoleName=NAME,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description="Managed KB experiment: reads the Confluence secret",
        )["Role"]["Arn"]
    except iam.exceptions.EntityAlreadyExistsException:
        arn = iam.get_role(RoleName=NAME)["Role"]["Arn"]
    read = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": "secretsmanager:GetSecretValue", "Resource": secret_arn}],
    }
    iam.put_role_policy(RoleName=NAME, PolicyName="read-the-confluence-secret", PolicyDocument=json.dumps(read))
    return arn


def while_the_role_propagates(call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """A new role takes a few seconds before Bedrock may assume it."""
    for attempt in range(7):
        try:
            return call()
        except ClientError as err:
            if err.response["Error"]["Code"] not in ("ValidationException", "AccessDeniedException") or attempt == 6:
                raise
            time.sleep(POLL_SECONDS)
    raise AssertionError("unreachable")


# --- sync -----------------------------------------------------------------------------------------


def sync(session: Any) -> None:
    agent = session.client("bedrock-agent")
    kb_id, ds_id = ids(agent)
    job = agent.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)["ingestionJob"]
    job_id = job["ingestionJobId"]
    while job["status"] not in ("COMPLETE", "FAILED", "STOPPED"):
        time.sleep(POLL_SECONDS)
        job = agent.get_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id, ingestionJobId=job_id)["ingestionJob"]
    print(json.dumps(job_summary(job), indent=2))
    for reason in job.get("failureReasons", []):
        print("failure:", reason)
    if job["status"] != "COMPLETE":
        raise SystemExit(f"the ingestion job ended {job['status']}")


def job_summary(job: dict[str, Any]) -> dict[str, Any]:
    started = job["startedAt"]
    summary: dict[str, Any] = {
        "status": job["status"],
        "started_at": started.isoformat(timespec="seconds"),
        "seconds": round((job["updatedAt"] - started).total_seconds()),
        "statistics": job.get("statistics", {}),
    }
    if job.get("textReadyAt"):
        summary["text_ready_s"] = round((job["textReadyAt"] - started).total_seconds())
    return summary


# --- evaluate -------------------------------------------------------------------------------------


def evaluate(session: Any, stack: str, dump: Path | None) -> None:
    agent = session.client("bedrock-agent")
    kb_id, ds_id = ids(agent)
    jobs = agent.list_ingestion_jobs(
        knowledgeBaseId=kb_id,
        dataSourceId=ds_id,
        sortBy={"attribute": "STARTED_AT", "order": "DESCENDING"},
        maxResults=1,
    )["ingestionJobSummaries"]
    if not jobs or jobs[0]["status"] != "COMPLETE":
        raise SystemExit("run the sync step first")
    job = agent.get_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id, ingestionJobId=jobs[0]["ingestionJobId"])
    titles = page_titles(session, stack_outputs(session, stack)["TableName"])
    ours = {row["id"]: row for row in json.loads((RESULTS / "retrieval.json").read_text())["questions"]}
    runtime = session.client("bedrock-agent-runtime")
    rows = []
    for question in [q for q in questions() if q["pages"]]:
        started = time.monotonic()
        answer = runtime.retrieve(
            knowledgeBaseId=kb_id, retrievalQuery={"text": question["question"]}, retrievalConfiguration=SEARCH
        )
        ms = round((time.monotonic() - started) * 1000)
        if dump is not None and not rows:
            dump.write_text(json.dumps(answer["retrievalResults"], indent=2, default=str, ensure_ascii=False) + "\n")
        found = [page_title(result, titles) for result in answer["retrievalResults"]]
        expected = set(question["pages"])
        rank = next((rank for rank, title in enumerate(found, 1) if title in expected), None)
        rows.append(
            {key: question[key] for key in ("id", "by", "kind", "question", "pages")}
            | {"rank": {"hybrid": ours[question["id"]]["rank"]["hybrid"], "managed KB": rank}, "top": found, "ms": ms}
        )
    report = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "knowledge_base": {
            "embedding": "MANAGED",
            "reranking": "MANAGED",
            "chunking": "default",
            "acl": False,
            "ingestion": job_summary(job["ingestionJob"]),
        },
        "ours": "hybrid search from evals/results/retrieval.json: the same questions and pages",
        "top_k": TOP_K,
        "queries": len(rows),
        "median_ms": statistics.median(row["ms"] for row in rows),
        "unknown_pages": sum(title == "?" for row in rows for title in row["top"]),
        "summary": summarize(rows),
        "questions": rows,
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "managed-kb.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    (RESULTS / "managed-kb.md").write_text(markdown(report))
    print(markdown(report))


def page_titles(session: Any, table: str) -> dict[str, str]:
    """Title by page id, from the PAGE items of our own sync."""
    pages = session.resource("dynamodb").Table(table)
    items: list[dict[str, Any]] = []
    query: dict[str, Any] = {"KeyConditionExpression": "pk = :pk", "ExpressionAttributeValues": {":pk": "PAGE"}}
    while True:
        answer = pages.query(**query)
        items.extend(answer["Items"])
        if "LastEvaluatedKey" not in answer:
            return {item["sk"]: item["title"] for item in items}
        query["ExclusiveStartKey"] = answer["LastEvaluatedKey"]


def page_title(result: dict[str, Any], titles: dict[str, str]) -> str:
    """The page a result comes from: a page id in its links, else a metadata value that is a title."""
    links = json.dumps([result.get("location", {}), result.get("metadata", {})], default=str)
    for page_id in PAGE_ID.findall(links):
        if page_id in titles:
            return titles[page_id]
    values = {str(value) for value in result.get("metadata", {}).values()}
    return next((title for title in titles.values() if title in values), "?")


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups["all"].append(row)
        groups[f"kind: {row['kind']}"].append(row)
        groups[f"by: {row['by']}"].append(row)
    summary = {}
    for group, members in groups.items():
        summary[group] = {"questions": len(members)}
        for method in METHODS:
            found = [row["rank"][method] for row in members]
            summary[group][method] = {
                "hit@5": sum(rank is not None for rank in found) / len(found),
                "mrr": sum(1 / rank for rank in found if rank) / len(found),
            }
    return summary


def markdown(report: dict[str, Any]) -> str:
    ingestion = report["knowledge_base"]["ingestion"]
    stats = ingestion["statistics"]
    lines = [
        f"# Managed Knowledge Base comparison, {report['run_at'][:10]}",
        "",
        "Amazon Bedrock Managed Knowledge Base with its Confluence connector, used as it comes: managed "
        "embeddings, managed reranking, default chunking, document permissions off. Our hybrid search is "
        "the run in retrieval.json, on the same pages. Top 5 per question; questions the docs do not "
        "answer are left out.",
        "",
        f"Ingestion: {stats.get('numberOfDocumentsScanned', 0)} documents scanned, "
        f"{stats.get('numberOfNewDocumentsIndexed', 0)} indexed, {stats.get('numberOfDocumentsFailed', 0)} failed, "
        f"{ingestion['seconds']} s. Retrieve: {report['queries']} queries, median {report['median_ms']} ms. "
        f"Results whose page could not be told: {report['unknown_pages']}.",
        "",
        "| Questions | n | " + " | ".join(f"{m} hit@5 / MRR" for m in METHODS) + " |",
        "|---|---|" + "---|" * len(METHODS),
    ]
    for group, values in report["summary"].items():
        cells = [f"{values[m]['hit@5']:.0%} / {values[m]['mrr']:.2f}" for m in METHODS]
        lines.append(f"| {group} | {values['questions']} | " + " | ".join(cells) + " |")
    lines += ["", "Rank of the first right result, per question (- means not in the top 5):", ""]
    lines.append("| id | by | kind | " + " | ".join(METHODS) + " | question |")
    lines.append("|---|---|---|" + "---|" * len(METHODS) + "---|")
    for row in report["questions"]:
        cells = [str(row["rank"][m] or "-") for m in METHODS]
        lines.append(f"| {row['id']} | {row['by']} | {row['kind']} | " + " | ".join(cells) + f" | {row['question']} |")
    return "\n".join(lines) + "\n"


# --- delete ---------------------------------------------------------------------------------------


def delete(session: Any) -> None:
    agent = session.client("bedrock-agent")
    kb_id = knowledge_base_id(agent)
    if kb_id is not None:
        ds_id = data_source_id(agent, kb_id)
        if ds_id is not None:
            agent.delete_data_source(knowledgeBaseId=kb_id, dataSourceId=ds_id)
            wait_gone("data source", lambda: agent.get_data_source(knowledgeBaseId=kb_id, dataSourceId=ds_id))
        agent.delete_knowledge_base(knowledgeBaseId=kb_id)
        wait_gone("knowledge base", lambda: agent.get_knowledge_base(knowledgeBaseId=kb_id))
    iam = session.client("iam")
    with contextlib.suppress(iam.exceptions.NoSuchEntityException):
        iam.delete_role_policy(RoleName=NAME, PolicyName="read-the-confluence-secret")
        iam.delete_role(RoleName=NAME)
    secrets = session.client("secretsmanager")
    with contextlib.suppress(secrets.exceptions.ResourceNotFoundException):
        secrets.delete_secret(SecretId=NAME, RecoveryWindowInDays=7)
    print("deleted the data source, the knowledge base, the role and the secret (recoverable for 7 days)")
    print("now revoke the API token in Atlassian")


# --- shared ---------------------------------------------------------------------------------------


def knowledge_base_id(agent: Any) -> str | None:
    for page in agent.get_paginator("list_knowledge_bases").paginate():
        for summary in page["knowledgeBaseSummaries"]:
            if summary["name"] == NAME:
                return summary["knowledgeBaseId"]
    return None


def data_source_id(agent: Any, kb_id: str) -> str | None:
    for page in agent.get_paginator("list_data_sources").paginate(knowledgeBaseId=kb_id):
        for summary in page["dataSourceSummaries"]:
            if summary["name"] == DATA_SOURCE:
                return summary["dataSourceId"]
    return None


def ids(agent: Any) -> tuple[str, str]:
    kb_id = knowledge_base_id(agent)
    ds_id = data_source_id(agent, kb_id) if kb_id else None
    if kb_id is None or ds_id is None:
        raise SystemExit("run the create step first")
    return kb_id, ds_id


def wait_for(what: str, get: Callable[[], dict[str, Any]], status: str, minutes: int = 15) -> None:
    deadline = time.monotonic() + minutes * 60
    while True:
        current = get()
        if current["status"] == status:
            return
        if "FAIL" in current["status"] or "UNSUCCESSFUL" in current["status"]:
            raise SystemExit(f"the {what} is {current['status']}: {current.get('failureReasons')}")
        if time.monotonic() > deadline:
            raise SystemExit(f"the {what} is still {current['status']} after {minutes} minutes")
        time.sleep(POLL_SECONDS)


def wait_gone(what: str, get: Callable[[], Any], minutes: int = 15) -> None:
    deadline = time.monotonic() + minutes * 60
    while time.monotonic() < deadline:
        try:
            get()
        except ClientError as err:
            if err.response["Error"]["Code"] == "ResourceNotFoundException":
                return
            raise
        time.sleep(POLL_SECONDS)
    raise SystemExit(f"the {what} still exists after {minutes} minutes")


if __name__ == "__main__":
    main()
