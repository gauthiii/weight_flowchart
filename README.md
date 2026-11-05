# Craving Control

A small personal site for cutting down on junk food and keeping an eye on money. It has five tabs:

- **Craving flowchart** – an interactive decision chart for my top 10 junk foods from the expense sheet (biryani, Popeyes/KFC, Maggi, Burger King, nuggets, ice cream, Nutella, brownies & cookies, pizza, Sunny D). Each craving gets six better options, best match first: tilapia, shrimp, chicken breast or an omelette for the savory ones; blueberry Greek yogurt, a protein shake, frozen banana or grapes, strawberries or oranges for the sweet ones; and a Great Value electrolyte drink for Sunny D. It walks you through one "is it available?" question at a time and shows what giving in would cost, including how many times you've bought it.
- **Monthly trends** – charts built from my expense sheet: which unhealthy foods I buy most, how many calories they add up to, and how that changes month by month.
- **Finances** – from my first paycheck (February 2026) on: income (salary + tuition), expenses paid from salary, money sent to India, investments, and how much was saved each month and in total.
- **Weight progress** – every Sunday weigh-in in kg or lb, how much was lost or gained each week, and calories, steps, cycling and water alongside, plus how weeks with more water compare with weeks with less.
- **Goal dates** – projected dates for 120, 100 and 80 kg from calories, steps, cycling, how my weight has actually responded, and my age and sex. Includes current BMI, estimated body fat, BMI milestones and a what-if planner.

**Live site:** https://gauthiii.github.io/weight_flowchart/

## Monthly trends

The trends tab reads every purchase in my Google Sheet expense log, groups the junk food into 26 categories (biryani, burgers, soda, Nutella, …) and shows:

- totals: estimated calories, weight equivalent, money spent, and this year's daily pace
- a monthly stacked bar chart by group (takeout, drinks, sweets, snacks, cooking staples), switchable between calories, purchases and spending, or narrowed to a single item
- a ranked table of the top items (click one to see its monthly trend)
- what stands out, and how to read the numbers

The same summary is saved as [junk_food_summary.md](junk_food_summary.md).

**About the numbers:** the sheet records prices, not quantities, so calories per purchase are estimates of a typical serving or my share of a shared pack. The weight column uses 3,500 kcal ≈ 1 lb and is a ceiling, not a prediction: it only applies if those calories were eaten on top of normal needs.

## How the data stays up to date

```
Google Sheet ──► update_sheet.py ──► data/expenses.csv       (full sheet export)
                                 ├─► data/junk_food.js       (data the trends tab loads)
                                 ├─► data/finance.js         (data the finances tab loads)
                                 └─► junk_food_summary.md    (summary table + notes)

Calorie sheet ─► update_weight.py ─► data/calories.csv       (full sheet export)
                                 └─► data/weight.js          (data the weight and goals tabs load)
```

A GitHub Action ([.github/workflows/update-and-deploy.yml](.github/workflows/update-and-deploy.yml)) runs on every push to `main`, once a day, and on demand. Each run:

1. runs `update_sheet.py` and `update_weight.py` to pull the latest sheets,
2. commits the refreshed CSV, data files and summary back to `main` (only if something changed),
3. deploys `index.html`, `data/junk_food.js`, `data/finance.js` and `data/weight.js` to GitHub Pages.

Because the Action may add a commit after you push, run `git pull` before your next push.

## Finances

Built from three places in the sheet:

- **Paychecks** – the `Date | Tution | Paycheck | …` table. Months not filled in there yet are counted from the "Biweekly n" entries in the earnings list (two paychecks a month from February 2026).
- **Tuition** – the `Date | Tuition Salary` list, by payment date.
- **Spending** – the main log, by date. Only rows paid from `Earnings` count; `To India` rows are money sent to India and `Investment` rows are investments. Expenses still paid from loan money aren't counted against savings.

Saved = paychecks + tuition − expenses − sent to India − invested. A big transfer to India can make a month negative; the running total shows what's actually left.

## Weight progress and goal dates

Built from the [calorie counter sheet](https://docs.google.com/spreadsheets/d/1LqOzKup2XJUcKq8mY2su2XTyEukgkxhLAM7C6UTgNjk): the `Weight in KG` rows (one each Sunday), the daily `STEPS`, `CYCLING` and `TOTAL` columns, and a water column once you add one.

- **Burn** uses the sheet's own formulas: Mifflin-St Jeor at rest (age 27, male, 180 cm), plus steps and cycling.
- **Calibration:** `update_weight.py` compares those formulas with how the scale actually moved on fully logged weeks, and applies the average gap to every burn figure. Weeks where one calorie total repeats for 5+ days are charted but left out of this.
- **Projection** runs in the browser, day by day: (calories − burn) ÷ 7,700 kcal per kg, with burn falling as weight falls. Current habits are the last 28 days' averages.
- **Body fat** is estimated with the CUN-BAE equation from BMI, age and sex.

- **Water**: any column with "water" in its header holds the liters drunk that day (`2.5`, `2.5 L` or `2500 ml` all work; numbers over 20 are read as ml). It is never counted as a food, wherever it sits. Each week shows its average liters a day. Finished weeks with water logged on 4+ days are split at the middle amount into "more water" and "less water" weeks, and each group shows its average weekly change and its change **beyond calories**: the real change minus what that week's calories, steps and cycling predict with the calibrated model (weeks with repeated calorie totals are left out of that part). A regression gives kg per week for each extra liter a day, with its correlation. The comparison appears once 4 such weeks exist. It shows a pattern, not cause and effect.
- **Macros** (the calorie chart's tooltip): each food column's calories are split into carbs, protein and fat using `FOOD_MACROS` in `update_weight.py`, then turned into grams at 4 kcal per gram of carbs or protein and 9 kcal per gram of fat. A new food column uses the biryani split until it gets its own row, and the Action log names it.

To change age or height, edit `AGE` and `HEIGHT_CM` in `update_weight.py`. To change a food's macros, edit its row in `FOOD_MACROS`.

## Files

| File | What it is |
|---|---|
| `index.html` | The whole site: all five tabs, styles and scripts in one file. No build step. |
| `update_sheet.py` | Downloads the sheet and regenerates the data files. Python standard library only. |
| `update_weight.py` | Downloads the calorie sheet and regenerates the weight data. Python standard library only. |
| `data/calories.csv` | The full calorie sheet as exported by Google. |
| `data/weight.js` | Generated. Weekly weight, calories, steps, cycling, water, calibration and the water comparison for the weight and goals tabs. |
| `data/expenses.csv` | The full sheet as exported by Google. |
| `data/junk_food.js` | Generated. Monthly counts, spend and summary for the trends tab. |
| `data/finance.js` | Generated. Monthly income, expenses, India transfers, investments and savings for the finances tab. |
| `junk_food_summary.md` | Generated. The summary table, what stands out, how to read the numbers. |

To change which items count as junk food or their calorie estimates, edit `CATEGORIES` in `update_sheet.py`.

## Run it locally

```bash
python3 update_sheet.py   # pull the latest expense sheet (optional)
python3 update_weight.py  # pull the latest calorie sheet (optional)
open index.html           # or just double-click it
```

No server or install needed: the page loads its data from a script file, so it works straight from disk.

## Setup notes

- Both Google Sheets must stay shared as **Anyone with the link can view**, or the download fails and the script stops without overwriting anything.
- GitHub Pages must be set to deploy from **GitHub Actions**: *Settings → Pages → Build and deployment → Source: GitHub Actions*.
