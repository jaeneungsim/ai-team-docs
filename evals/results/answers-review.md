# Answer evaluation: review by reading

Code scores each answer by looking for required facts (see `evals/answers.py`). Every answer of
both runs was also read against the docs on 2026-10-19. This page lists where reading disagrees
with the code, and what the wrong answers have in common.

## Where reading disagrees with the code

| Run | Method | Question | Code | Reading | Why |
|---|---|---|---|---|---|
| v1 | whole | q23 (log level of a 404) | right | wrong | The answer concludes `INFO` (it puts 404 below 400), but it quotes the table, which contains the required `WARNING` |
| v1 | cached | q23 | right | wrong | Same answer as whole |
| v2 | cached | q23 | right | wrong | Same mistake with the second prompt |

No answer that code scored wrong was right on reading. Two answers scored wrong said `NOT IN DOCS`
and then gave the right content anyway (v1 and v2 search, q20); they stay wrong, because an agent
that reads "not in the docs" first is likely to stop there.

## Scores after reading

| Run | Prompt | search | whole | cached |
|---|---|---|---|---|
| v1 | answer only from the docs, else `NOT IN DOCS` | 82% | 68% | 68% |
| v2 | the docs usually answer in other words; `NOT IN DOCS` only when nothing answers | 85% | not run | 82% |

34 questions each; 3 of them are not answered by the docs, and every method declined all 3.

## What the wrong answers have in common (v2)

| Question | search | cached | What happened |
|---|---|---|---|
| q05 why `sold_out` is a flag | wrong | wrong | Said `NOT IN DOCS`; ADR-005 gives the reason (derived in one place, never stored, so it cannot disagree with `stock`) |
| q08 can a client set the stock | wrong | wrong | Said `NOT IN DOCS`. Search returned the Item API page, but not its "Item fields" section with the answer |
| q09 what DELETE returns | right | wrong | With the whole space, said `NOT IN DOCS` |
| q20 what INV-124 was | wrong | wrong | Said `NOT IN DOCS`; search's answer then quoted "INV-124: mark items with zero stock as sold out" |
| q23 log level of a 404 | wrong | wrong | Reasoning error in every run: 404 put in the "below 400" row |
| q34 is there a live setup | wrong | wrong | Said `NOT IN DOCS`; "Production is out of scope" was in the 5th search result and in the whole space |

- Most errors are refusals while the answer is in front of the model, on questions asked in other
  words than the docs. The v2 prompt cut them with the whole space (32% of answerable questions
  to 16%) and a little with search (16% to 13%).
- One error is a search miss at section level (q08): the right page, not the right section. Page
  level hit@5 counts it as found, so it overstates what the model gets to read.
- One answer cites the wrong page (v2 cached, q19: the digest time is on Architecture overview,
  the answer names the review check-in); the fact itself is right.
