# ai-team-docs

AI coding agents often work from copies of team documents that someone saved earlier, and nobody
notices when a copy goes stale. This project gives an agent the current documents instead: a
read-only sync from Confluence Cloud every 10 minutes, hybrid search in a Lambda function, and a
local MCP tool that returns every result with its source page, version and sync time.

## Status

- [x] `demo-docs/`: the demo team's Confluence pages, and the script that uploads them
- [x] v1: sync, conversion, keyword search, sources and staleness warnings, MCP tool
- [x] v2: embeddings, hybrid search, safety checks on incoming pages
- [ ] Evaluation: retrieval and answer quality, freshness, cost
- [ ] v3: team rules as evidence in [pr-triage](https://github.com/jaeneungsim/pr-triage) reviews

## How it works

```text
EventBridge Scheduler, every 10 minutes ──▶ sync function
  Confluence v2 API (GET only, read-scoped token) ──▶ convert ──▶ safety checks ──▶ chunks ──▶ Titan embeddings
  ──▶ S3 (raw pages, Markdown, chunks, vectors) ──▶ new index (SQLite FTS5 + vectors) ──▶ STATE item in DynamoDB

Claude Code ──stdio──▶ local MCP server ──▶ search-only IAM role ──▶ search function
  BM25 + cosine similarity ──▶ reciprocal rank fusion ──▶ sections with link, version, edit and sync time, warnings
```

- Only the sync function talks to Confluence, and only with GET. It uses a scoped API token with
  `read:page:confluence` and `read:space:confluence`, kept in SSM Parameter Store.
- There is no public endpoint. The MCP server invokes the search function through a role that can
  do nothing else, so the agent side never holds a Confluence token.
- What people cannot see is removed before indexing: HTML comments, white or zero-size text,
  zero-width and tag characters. Text that looks aimed at an AI is kept and flagged in the results.
- Results carry warnings when the last successful sync is more than 30 minutes old, when pages
  could not be updated, and when the token expires within 14 days.
- Pages that leave the space are removed after a per-page check. When more than 20% of the index
  leaves in one run, removals wait until a person runs the sync with `{"force": true}`.
- The S3 files of a removed page, of a page's replaced version and of a replaced index are tagged
  `superseded`, and a lifecycle rule deletes a tagged file once it is a week old. The sync function
  itself cannot delete objects.

## Layout

```text
src/team_docs/  confluence (GET only), convert, scan, chunk, embed, index, search, store, sync, handlers
mcp/            the local MCP server, a separate uv project
infra/          CDK (TypeScript): one stack, team-docs
demo-docs/      the demo corpus in Markdown, uploaded with scripts/upload_demo_docs.py
scripts/        the only code that writes to Confluence: upload, the freshness probe, the scene edit
evals/          questions, retrieval and answer evaluation, the Managed KB comparison, the scene
evals/results/  what those runs measured
tests/          storage-format fixtures from the demo site; sync and search on in-memory fakes
```

## Develop

```bash
uv venv --python 3.13 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m pytest
cd infra && npm ci && npm test
```

`requirements.txt` pins the Lambda dependencies for Linux arm64:
`uv pip compile requirements.in --python-version 3.13 --python-platform aarch64-manylinux_2_28 -o requirements.txt`

## Deploy

1. Put the read token in SSM Parameter Store as a SecureString named
   `/team-docs/confluence/read-token`, and its expiry date (`YYYY-MM-DD`) as a String named
   `/team-docs/confluence/read-token-expires`. Change both together when the token is renewed.
2. Create `infra/cdk.context.json`, which is not committed:

   ```json
   {
     "confluenceCloudId": "<from https://<site>.atlassian.net/_edge/tenant_info>",
     "confluenceEmail": "<email of the account that owns the token>",
     "searchCallerPermissionSet": "<the IAM Identity Center permission set you log in with>"
   }
   ```

3. Deploy with your SSO profile: `cd infra && AWS_PROFILE=<sso-profile> npx cdk deploy`
4. The schedule runs the first sync within 10 minutes. To run it now:

   ```bash
   aws lambda invoke --function-name team-docs-sync --cli-binary-format raw-in-base64-out \
     --payload '{}' /dev/stdout
   ```

## Use it from Claude Code

Add an AWS profile to `~/.aws/config` that switches from your SSO login to the search-only role
(`SearchCallerRoleArn` in the stack outputs):

```ini
[profile team-docs-search]
role_arn = arn:aws:iam::<account-id>:role/team-docs-search-caller
source_profile = <sso-profile>
region = ap-southeast-2
```

Then register the server for every repo on your machine:

```bash
claude mcp add team-docs --transport stdio --scope user --env AWS_PROFILE=team-docs-search \
  -- uv run --directory /path/to/ai-team-docs/mcp python server.py
```

The server name goes first: `--env` takes every following `KEY=value` until `--`.

The tool is `search_team_docs(query, top_k=5)`. When the SSO login expires, the tool says which
`aws sso login` command to run.

## Demo docs

`demo-docs/` holds about 30 pages of a fictional team that runs the demo app from pr-triage:
decision records, runbooks, conventions and reference pages. They are the corpus for the sync,
the search and the evaluation. See [demo-docs/README.md](demo-docs/README.md) for the format.

```bash
.venv/bin/python scripts/upload_demo_docs.py --cloud-id "$CONFLUENCE_CLOUD_ID" \
  --email "$CONFLUENCE_EMAIL" --space INV --dry-run
```

The upload reads a Confluence API token with `write:page:confluence` from the macOS keychain
(service `team-docs-confluence-write`). The sync uses the separate token that can only read.
