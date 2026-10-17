# Plan

## The monthly plan (per person)

| Bucket | Amount | Kind |
|---|---|---|
| Weekday (Mon-Fri) | RM400 (RM100 x 4 wk) | weekly cap |
| Weekend (Sat-Sun) | RM800 (RM200 x 4 wk) | weekly cap |
| Extra | RM300 | monthly cap |
| Grocery | RM200 | monthly cap |
| Chu Chu / Toiletries | RM60 | monthly cap |
| Petrol | RM200 | monthly cap |
| Toll | RM50 | monthly cap |
| Parents | RM500 | monthly cap |
| House | RM1,000 | fixed: Vanisa always Paid; Hanz Due until Hanz says "house paid" |
| Car | RM300 | fixed: same as House |

Goals RM2,510 + fixed RM1,300 = RM3,810 per person, RM7,620 combined.

## Rules

- **Who spent:** the shares in the message; a plain message belongs to the sender.
- **Who paid:** as stated; a plain message means the sender paid. Two people involved, or someone else named,
  with no payer -> the bot asks in the group (`[Hanz] [Vanisa] [Each paid own]`).
- **Bucket:** purpose buckets (grocery, petrol, toll, chu chu, parents, extra) by what it was; everything else is
  everyday spending -> Weekday or Weekend by the date (Malaysia time). Weekend = Sat-Sun only.
- **Unsure about category/bucket** -> the entry is saved as Unsorted and the bot asks; the answer is learned per place.
- **Extra** only when the message says "extra" or the bot asks (an everyday spend share over RM100).
- **Weekly allowance:** the monthly total is fixed. Each week gets (left this month / bucket days left) x bucket days
  in the week, so underspend carries forward and the month never exceeds the plan.
- **Pace:** spent / cap compared with how far through the month (or week) we are: ok / ahead / over.
- **Alerts:** at 80% and when a cap is exceeded (week scope for weekday/weekend, month scope otherwise).
- **Balance:** payer is owed the other person's share; settle-ups (`vanisa paid hanz 86.30`) clear it and never touch
  budgets.
- Duplicate chat messages are recorded once. Deletes are soft.

## Dashboard (phase 2)

Combined card on top (goal bars per bucket, fixed Paid/Due, paid-by strip, balance); Hanz left, Vanisa right
(this week's weekday/weekend bars, then monthly buckets); "Needs answer" box; spending table with place, bucket,
category, split and payer, filters, top places, CSV export. Kopitiam pixel theme from `~/kopitiam/web/pixel.css`.
