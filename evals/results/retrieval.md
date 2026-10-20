# Retrieval evaluation, 2026-10-19

Index build `20261019T045201Z-69e4b3`: 30 pages, 61 sections. Top 5 sections per question. Questions the docs do not answer are left out.

| Questions | n | keyword hit@5 / MRR | vector hit@5 / MRR | hybrid hit@5 / MRR | hybrid, no prefix hit@5 / MRR |
|---|---|---|---|---|---|
| all | 31 | 84% / 0.68 | 100% / 0.86 | 100% / 0.89 | 97% / 0.82 |
| kind: paraphrase | 24 | 79% / 0.63 | 100% / 0.87 | 100% / 0.85 | 96% / 0.81 |
| by: claude | 26 | 88% / 0.71 | 100% / 0.89 | 100% / 0.91 | 100% / 0.84 |
| kind: exact | 4 | 100% / 0.88 | 100% / 0.83 | 100% / 1.00 | 100% / 0.88 |
| kind: multi | 3 | 100% / 0.83 | 100% / 0.83 | 100% / 1.00 | 100% / 0.83 |
| by: claude-low-overlap | 5 | 60% / 0.50 | 100% / 0.73 | 100% / 0.74 | 80% / 0.70 |

Rank of the first right section, per question (- means not in the top 5):

| id | by | kind | keyword | vector | hybrid | hybrid, no prefix | question |
|---|---|---|---|---|---|---|---|
| q01 | claude | paraphrase | 4 | 1 | 1 | 1 | dev broke right after something got merged. What is the quickest way to get the previous working version running again? |
| q02 | claude | paraphrase | 1 | 1 | 1 | 2 | If I redeploy an older commit to fix dev, is that the end of it, or is there something else I have to do? |
| q03 | claude | paraphrase | 1 | 1 | 1 | 1 | The AI code review stopped running and every PR now waits for a human. How do I get the reviews going again? |
| q04 | claude | paraphrase | 1 | 1 | 1 | 1 | Someone sent me the id of a request that failed. Where can I see what the API did with it? |
| q05 | claude | paraphrase | 3 | 1 | 2 | 1 | Why does an item come back with a yes/no flag for whether it can be bought, instead of clients working that out from the quantity? |
| q06 | claude | paraphrase | 2 | 1 | 1 | 1 | Why is every endpoint handled by a single function rather than one function per endpoint? |
| q07 | claude | paraphrase | 2 | 1 | 1 | 1 | When I create a new item through the API, how many units does it have, and will the shop show it as available? |
| q08 | claude | paraphrase | - | 4 | 4 | 5 | Can a client set how many units are on hand when it creates an item? |
| q09 | claude | paraphrase | - | 1 | 2 | 2 | What happens if someone sends a DELETE request for an item? |
| q10 | claude | paraphrase | 1 | 1 | 1 | 1 | If I fetch an item with an id full of odd characters, do I get a bad request error? |
| q11 | claude | paraphrase | 1 | 1 | 1 | 1 | Which model reads our pull requests, and roughly how much does one review cost? |
| q12 | claude | paraphrase | - | 1 | 2 | 3 | When is the review bot allowed to merge a PR without a person? |
| q13 | claude | paraphrase | 1 | 1 | 1 | 1 | How do I put the reviewer back into the mode where it only labels PRs and never approves them? |
| q14 | claude | paraphrase | 2 | 1 | 1 | 1 | A review ran while the model was down. How can I have the same commit reviewed again without pushing anything? |
| q15 | claude | paraphrase | 1 | 2 | 1 | 1 | What removes a ticket's test environment if its PR is just left open? |
| q16 | claude | paraphrase | 1 | 1 | 1 | 1 | The dev deploy failed because CloudFormation was not allowed to create a new kind of resource. What is usually wrong, and where is it fixed? |
| q17 | claude | paraphrase | 1 | 1 | 1 | 1 | Why does a web preview live in a folder of a shared bucket instead of getting its own distribution? |
| q18 | claude | paraphrase | 2 | 1 | 1 | 3 | Which changes in a PR always go to a person, whatever the bot thinks? |
| q19 | claude | paraphrase | 1 | 2 | 1 | 1 | When does the summary of the overnight reviews come out? |
| q20 | claude | exact | 2 | 3 | 1 | 2 | What was INV-124? |
| q21 | claude | exact | 1 | 1 | 1 | 1 | What is invalid_cursor, and can a client get it today? |
| q22 | claude | exact | 1 | 1 | 1 | 1 | What is stored in /pr-triage/config/limits? |
| q23 | claude | exact | 1 | 1 | 1 | 1 | At what log level is a 404 response written? |
| q24 | claude | multi | 1 | 1 | 1 | 1 | Do the item endpoints return the stock quantity? I remember a decision that said they don't. |
| q25 | claude | multi | 1 | 2 | 1 | 1 | Why did the team let the bot approve PRs, and how did the first try go? |
| q26 | claude | multi | 2 | 1 | 1 | 2 | Before I open my first PR, what has to be in the branch name and in the PR description? |
| q30 | claude-low-overlap | paraphrase | - | 1 | 1 | 1 | Our coding bots keep tripping the same automated gate on different PRs. Do we patch up each one, or is there a better place to deal with it? |
| q31 | claude-low-overlap | paraphrase | 2 | 1 | 1 | 1 | I'm new and want to poke at the backend on my laptop without touching the cloud. What do I need running? |
| q32 | claude-low-overlap | paraphrase | 1 | 3 | 1 | 1 | What happens to an earlier thumbs-up when the author adds more work to the same pull request? |
| q33 | claude-low-overlap | paraphrase | 1 | 3 | 2 | 2 | What catches a PR write-up that tries to sweet-talk the bot into saying yes? |
| q34 | claude-low-overlap | paraphrase | - | 1 | 5 | - | Is there a live, customer-facing setup anywhere, or only places for trying things out? |
