# Plan

## The monthly plan (per person)

| Bucket | Amount | Kind |
|---|---|---|
| Weekday (Mon-Fri) | RM20 per day (RM100 a full week) | weekly target + carry-over |
| Weekend (Sat-Sun) | RM100 per day (RM200 a full weekend) | weekly target + carry-over |
| Extra | RM300 | monthly cap |
| Grocery | RM200 | monthly cap |
| Chu Chu / Toiletries | RM60 | monthly cap |
| Petrol | RM200 | monthly cap |
| Toll | RM50 | monthly cap |
| Parents | RM500 | monthly cap |
| House | RM1,000 | fixed: Vanisa always Paid; Hanz Due until Hanz says "house paid" |
| Car | RM300 | fixed: same as House |

Monthly goals = weekly targets for that month's calendar + RM1,310 monthly caps (Oct 2026: 440 + 900 + 1,310 = RM2,650),
plus fixed RM1,300 per person.

## Rules

- **Who spent:** the shares in the message; a plain message belongs to the sender.
- **Who paid:** as stated; a plain message means the sender paid. Two people involved, or someone else named,
  with no payer -> the bot asks in the group (`[Hanz] [Vanisa] [Each paid own]`).
- **Bucket:** purpose buckets (grocery, petrol, toll, chu chu, parents, extra) by what it was; everything else is
  everyday spending -> Weekday or Weekend by the date (Malaysia time). Weekend = Sat-Sun only.
- **Unsure about category/bucket** -> the entry is saved as Unsorted and the bot asks; the answer is learned per place.
- **Extra** only when the message says "extra" or the bot asks (an everyday spend share over RM100).
- **Weekly budgets:** daily amounts (RM20 per weekday, RM100 per weekend day); a week's target = daily amount x
  its days in the month (full week RM100 / RM200, Thu-Fri = RM40, a lone Saturday = RM100). Under/overspend in the earlier
  weeks of the month carries into this week: **can spend = target + carry-over**, never below 0. Resets each month.
  The bot and dashboard always show all three: target, carry-over (saved / overspent), can spend.
- **Starting mid-month:** `python -m duit backfill FROM TO` adds on-budget "Before tracking" placeholder spends
  (used for 1-16 Oct 2026). Alternatively `rules.tracking_start` + `before_start = "maxed"` count the earlier weekday/weekend days as
  exactly on budget (full monthly targets, pre-start share assumed spent, no carry-over). `"ignore"` prorates instead.
- **Pace:** spent / cap compared with how far through the month (or week) we are: ok / ahead / over.
- **Alerts:** at 80% and when a cap is exceeded (week scope for weekday/weekend, month scope otherwise).
- **Balance:** payer is owed the other person's share; settle-ups (`vanisa paid hanz 86.30`) clear it and never touch
  budgets.
- Duplicate chat messages are recorded once. Deletes are soft.

## Dashboard (phase 2)

Combined card on top (goal bars per bucket, fixed Paid/Due, paid-by strip, balance); Hanz left, Vanisa right
(this week's weekday/weekend bars, then monthly buckets); "Needs answer" box; spending table with place, bucket,
category, split and payer, filters, top places, CSV export. Kopitiam pixel theme from `~/kopitiam/web/pixel.css`.
