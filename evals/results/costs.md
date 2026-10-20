# Cost, 2026-10-20

Measured from CloudWatch between 2026-10-17T10:01 and 2026-10-20T10:01 UTC: 179 sync runs (158 with nothing to do, 20 that changed one page) and 40 hybrid searches, the kind the MCP tool makes (461 keyword searches from the freshness probe are left out). DynamoDB, S3 and KMS requests are counted from the code. Prices are Sydney list prices from the AWS Price List API, at the highest tier and before any free tier.

| Unit of work | Runs measured | Billed ms (median / mean / max) | Cold starts | Cost per 1,000 |
|---|---|---|---|---|
| sync run, nothing changed | 158 | 2416 / 2400 / 3217 | 157 | $0.0244 |
| sync run, one page changed | 20 | 3862 / 3950 / 4778 | 20 | $0.1305 |
| search | 40 | 120 / 342 / 2485 | 4 | $0.0039 |

A month: the 10-minute schedule, 100 edits and 1000 searches.

| Item | Count | Cost |
|---|---|---|
| sync runs, nothing changed | 4,220 | $0.1030 |
| sync runs, one page changed | 100 | $0.0131 |
| searches | 1,000 | $0.0039 |
| S3 storage (9.6 MB) | 1 | $0.0002 |
| log storage, 14 days (4.1 MB) | 1 | $0.0001 |
| total | | $0.1203 |
