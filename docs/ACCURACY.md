# Accuracy design

**Rule:** the model only *reads* messages: what was bought, where, which category and bucket, who paid, and
how it was split ("even", "2:1", "for vanisa"). Every number is parsed, checked, computed, stored and
formatted by deterministic code.

| Risk | Guard | Where |
|---|---|---|
| Wrong person | The sender comes from the gateway's Telegram user ID, never from the model. Strangers are rejected. | `tools._sender`, plugin `_context` |
| Misread or invented amount | Every amount the model passes must appear in the original message, which the gateway captures before the model sees it. Headcounts, ratios, times, dates and `#ids` don't count as money. | `textcheck`, `tools._verify`, plugin `pre_gateway_dispatch` |
| Model-computed split | The model passes `split: "even"` / `"2:1"` / `for_person`, and code computes the shares, with the leftover sen assigned so parts add up exactly. Shares the model works out itself fail the text check. | `tools._amounts`, `money.split_even/split_ratio` |
| A total next to shares that don't add up | If the shares leave an unexplained bigger number in the message, the bot asks "is that the total?". | `tools._amounts` |
| Wrong numbers in the chat | The model's final text is replaced by the ledger's reply lines for that message. The model's own words only get through when no tool replied (a question), or as a question after a refusal. | plugin `transform_llm_output` |
| Model sums search results | `list_spends` and `status` return finished text with code-computed totals. | `replies.spends_text/status_text/bucket_text` |
| Wrong date or bucket after a delay | The date comes from the Telegram send time (`yesterday` is relative to it). Weekday/weekend comes from that date. | `tools._day`, plugin `pre_gateway_dispatch` |
| Missing bucket | If the model gives a category but no bucket and no options, the bucket comes from the category (Groceries→grocery, Pet/Toiletries→chuchu, Family→parents, else everyday). With options, the bot asks. | `tools._bucket` |
| Bot answers its own question | Payer/bucket answers from the same message as the spend are rejected. | `tools._not_own_question` |
| Float rounding | Money is integer sen end to end. Decimal parsing, exact split remainders, strings into the ledger. | `money`, `tools._rm` |
| Duplicates on retry | One entry per chat message (`msg_id`, `msg_id:2` for several spends in one message). | `entries_msg` unique index |
| Half-written changes | Each write is one SQLite transaction (`BEGIN IMMEDIATE`). WAL and busy timeout handle the bot and dashboard together. | `ledger._tx`, `db.connect` |
| Untraceable mistakes | Every tool call (args, result, sender, message) is stored in `audit`. Deletes are soft. | `tools._audit` |
| Silent corruption | `python -m duit check`: shares = totals, known people/buckets, weekday/weekend matches the date, balance nets to zero, every month has a plan. It runs nightly. | `integrity.check` |
| Data loss | Nightly online SQLite backup, keeping 30 (`data/backups/`). | `integrity.backup`, `deploy/kura-kira-nightly.*` |

Tests: `tests/test_accuracy.py` pins each guard. `eval/` runs real messages through the live model.
