# ChatGPT design prompt

## Prompt 1: five layout concepts

```
I'm building a personal web dashboard that tracks spending for a couple, me (Hanz) and my girlfriend (Vanisa), against our monthly budget. Please design 5 different layout concepts as full-screen mockup images. Show them one at a time, as separate images, so I can compare and pick one.

STYLE (all 5)
- Pixel art / retro game UI: chunky pixel borders, hard 4px drop shadows, no rounded corners, no gradients except dithering, pixel fonts for headings, crisp readable text for numbers.
- Couple themed: two small pixel characters, Hanz and Vanisa, and our cat Chu Chu as a mascot. [Optional: Hanz looks like ___, Vanisa looks like ___, Chu Chu is a ___ cat.]
- Warm and cozy, not corporate. Malaysian touches are welcome (kopitiam, shophouse, hawker vibes) but optional.
- Each concept needs its own distinct theme. Suggestions:
  1. Cozy kopitiam: we're two customers at a coffee shop counter, and the budget is the bill
  2. RPG party status screen: budgets as HP/MP bars, the two of us as party members
  3. Our little apartment / Tamagotchi home: rooms or furniture hold the budget sections, and Chu Chu walks around
  4. Arcade 2-player co-op cabinet: P1 Hanz and P2 Vanisa, with a shared "team" score on top
  5. Game Boy / handheld: limited 4-color palette, compact cards

LAYOUT (must be in every concept, same information, different styling)
Desktop 1440x900. Top to bottom:

A) Header: app name "DUIT" (Malay for money), the month "October 2026", "day 17/31", a month picker.

B) COMBINED card (big, full width): our joint budget
- One big progress bar: "RM 3,120 / RM 5,020 spent (62%)", with a small marker at 55% showing how far through the month we are
- Status colors: green = on track, yellow = spending faster than the month is passing, red = over budget
- One small bar per budget bucket (combined numbers):
  Weekday 340/800 · Weekend 900/1,600 · Extra 120/600 · Grocery 260/400 · Chu Chu & Toiletries 70/120 · Petrol 210/400 · Toll 50/100 · Parents 1,000/1,000
- Fixed bills as stamps or badges, NOT bars: House RM2,000 "PAID" · Car RM600 "1 of 2 PAID"
- A "who paid" strip: Hanz paid RM2,140 vs Vanisa paid RM1,620, with "Vanisa owes Hanz RM86.30"

C) Two cards side by side: HANZ (left) and VANISA (right), mirrored, each with their character
- "This week" section on top with two bars: Weekday 66/100 (RM34 left), Weekend 56/200 (RM144 left)
- "This month" total: RM1,690 / RM2,510
- Small bars for: Extra, Grocery, Chu Chu & Toiletries, Petrol, Toll, Parents (show one of them red/over budget, e.g. Toll 53/50)
- House and Car as badges: Hanz shows "DUE" for car, Vanisa shows both "PAID"
- A small "Unsorted RM120" chip on Vanisa's card

D) "Needs answer" box (small alert box): "Watsons RM75 · Vanisa: Toiletries or Extra?" with two pixel buttons

E) Spending table (full width), styled like a receipt or game log:
- Filters: month, who, bucket, category, search, "Export CSV" button
- Columns: Date | Day | Who | Place / item | Bucket | Category | Amount | Split | Paid by
- Example rows:
  18 Oct | Sat | Hanz | Sushi-Mentai | Weekend | Food | 56.50 | — | Hanz
  16 Oct | Thu | Vanisa | Petronas | Petrol | Transport | 50.00 | — | Vanisa
  15 Oct | Wed | Both | Zapfan (lunch) | Weekday | Food | 27.70 | Hanz 13.20 · Vanisa 14.50 | Hanz
  14 Oct | Tue | Hanz | Badminton court | Weekday | Sport | 30.00 | — | Hanz
- A side panel "Top places": Sushi-Mentai 4x RM210 · Jaya Grocer 3x RM180 · Petronas 3x RM160

REQUIREMENTS
- Text and numbers must be legible: use the exact numbers above, money as "RM".
- Show red (over budget), yellow (ahead of pace) and green (on track) states somewhere in each design.
- No real brand logos; place names as plain text only.
- After the 5 desktop images, also show a phone version (390px wide) of each, with the Hanz and Vanisa cards stacked.

For each concept, also give me: the name, the color palette as hex codes, and the fonts you would use (free pixel fonts, e.g. from Google Fonts).
```

## Prompt 2: asset pack for the chosen concept (send after picking one)

```
I pick concept #__. Please create the asset pack for building it in HTML/CSS:
- Transparent PNGs, pixel-perfect (nearest-neighbor, no anti-aliasing), each exported at 1x and 4x:
  - Hanz and Vanisa characters: idle, happy (under budget), worried (over budget), each about 32x32 at 1x
  - Chu Chu the cat: idle, walking, sleeping, about 24x24 at 1x
  - One icon per bucket (16x16): weekday, weekend, extra, grocery, chu chu & toiletries, petrol, toll, parents, house, car
  - Progress bar parts: empty frame, fill in green / yellow / red, the pace marker
  - Card frame / panel border as a 9-slice image, plus button normal / hover / pressed
  - "PAID", "DUE" and "OVER" stamps
  - Background tile (seamless) and header decoration
- A palette sheet with hex codes and the font names
- Name files clearly (e.g. hanz-happy@4x.png) and give them to me as a ZIP
```
