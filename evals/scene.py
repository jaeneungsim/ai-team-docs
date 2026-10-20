#!/usr/bin/env python3
"""The comparison scene: one question, three agents, before and after the rollback runbook changed.

    copy        the runbook as someone copied it into the repo earlier (demo-docs/)
    managed KB  the top 5 results of the Managed Knowledge Base from evals/managed_kb.py
    team-docs   the search tool, called and rendered exactly as the MCP server does

Each agent is the same model with the same prompt as evals/answers.py (prompt v2), plus one line
asking it to give the page version and edit time when the docs show them. The edit itself is
scripts/edit_for_scene.py. Each run is appended to evals/results/scene.json and all runs are
written to scene.md under the label you give. Site addresses in the answers are masked.

    AWS_PROFILE=<sso-profile> .venv/bin/python evals/scene.py --label "after the edit"

The search tool is called with the search-only profile (--search-profile), like the MCP server.
A run costs about one cent: three short model calls and one knowledge base query.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from typing import Any

import boto3
from answers import MODEL_ID, PRICES, PROMPTS, with_retries
from common import RESULTS, ROOT, mask_site, mentions, questions
from managed_kb import SEARCH, knowledge_base_id

from render import answer as render_answer

QUESTION_ID = "q01"  # "dev broke right after something got merged. What is the quickest way ..."
COPY = ROOT / "demo-docs" / "runbooks" / "roll-back-dev.md"
RULES = PROMPTS["v2"] + " When the docs show a page version or an edit time, give them."
AGENTS = ("copy", "managed KB", "team-docs")
DO_NOT_RERUN = re.compile(r"\b(do not|don't|no longer|stopped|not to)\b[^.]{0,40}\bre-?run", re.I)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--label", required=True, help="what changed before this run, for the report")
    parser.add_argument("--region", default="ap-southeast-2")
    parser.add_argument("--search-profile", default="team-docs-search")
    parser.add_argument("--function", default="team-docs-search")
    parser.add_argument("--agents", default=",".join(AGENTS), help=f"comma-separated, from: {', '.join(AGENTS)}")
    args = parser.parse_args()
    agents = args.agents.split(",")
    if not set(agents) <= set(AGENTS):
        parser.error(f"--agents takes {', '.join(AGENTS)}")

    session = boto3.Session(region_name=args.region)
    search = boto3.Session(profile_name=args.search_profile, region_name=args.region).client("lambda")
    question = next(q for q in questions() if q["id"] == QUESTION_ID)
    context_of = {
        "copy": copy_context,
        "managed KB": lambda: kb_context(session, question["question"]),
        "team-docs": lambda: tool_context(search, args.function, question["question"]),
    }
    contexts = {name: context_of[name]() for name in AGENTS if name in agents}
    bedrock = session.client("bedrock-runtime")
    run = {
        "label": args.label,
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "question": question["question"],
        "agents": {name: ask(bedrock, question["question"], context) for name, context in contexts.items()},
    }
    path = RESULTS / "scene.json"
    runs = json.loads(path.read_text()) if path.exists() else []
    runs.append(run)
    path.write_text(json.dumps(runs, indent=2, ensure_ascii=False) + "\n")
    (RESULTS / "scene.md").write_text(markdown(runs))
    print(markdown([run]))


def copy_context() -> str:
    """The file as an agent finds it in the repo."""
    return f"File docs/runbooks/roll-back-dev.md, copied from the wiki:\n\n{COPY.read_text(encoding='utf-8')}"


def kb_context(session: Any, question: str) -> str:
    """The knowledge base results with what the knowledge base says about each: title and last update."""
    agent = session.client("bedrock-agent")
    found = session.client("bedrock-agent-runtime").retrieve(
        knowledgeBaseId=knowledge_base_id(agent), retrievalQuery={"text": question}, retrievalConfiguration=SEARCH
    )["retrievalResults"]
    parts = []
    for number, result in enumerate(found, 1):
        meta = result.get("metadata", {})
        title, updated = meta.get("_document_title", "?"), meta.get("_last_updated_at", "?")
        parts.append(f"[{number}] {title} (last updated {updated})\n\n{result['content']['text']}")
    return "\n\n".join(parts)


def tool_context(client: Any, function: str, question: str) -> str:
    """What the search_team_docs tool returns to the agent."""
    answer = client.invoke(FunctionName=function, Payload=json.dumps({"query": question, "top_k": 5}).encode())
    return render_answer(json.loads(answer["Payload"].read()))


def ask(bedrock: Any, question: str, documents: str) -> dict[str, Any]:
    response = with_retries(
        lambda: bedrock.converse(
            modelId=MODEL_ID,
            system=[{"text": RULES}, {"text": f"Team docs:\n\n{documents}"}],
            messages=[{"role": "user", "content": [{"text": question}]}],
            inferenceConfig={"maxTokens": 400, "temperature": 0},
        )
    )
    text = "".join(block.get("text", "") for block in response["output"]["message"]["content"])
    usage = response.get("usage", {})
    usd = (usage.get("inputTokens", 0) * PRICES["input"] + usage.get("outputTokens", 0) * PRICES["output"]) / 1e6
    return {
        "suggests_rerun": mentions(text, "gh run rerun") and not DO_NOT_RERUN.search(text),
        "says_do_not_rerun": bool(DO_NOT_RERUN.search(text)),
        "says_revert": mentions(text, "revert"),
        "usd": round(usd, 5),
        "answer": mask_site(text),
    }


def markdown(runs: list[dict[str, Any]]) -> str:
    lines = ["# Comparison scene", "", f"Question: {runs[0]['question']}", ""]
    for run in runs:
        lines += [
            f"## {run['label']} ({run['run_at']})",
            "",
            "| Agent | Suggests `gh run rerun` | Says not to re-run | Mentions revert |",
            "|---|---|---|---|",
        ]
        for name, agent in run["agents"].items():
            cells = [agent["suggests_rerun"], agent["says_do_not_rerun"], agent["says_revert"]]
            lines.append(f"| {name} | " + " | ".join("yes" if cell else "no" for cell in cells) + " |")
        lines.append("")
        for name, agent in run["agents"].items():
            lines += [f"**{name}**", "", agent["answer"].strip(), ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
