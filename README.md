# Craving Control

A small personal site for cutting down on junk food. It has two tabs:

- **Craving flowchart** – an interactive decision chart for when a craving hits (biryani, Hershey's, Nutella). It walks you through a swap first (protein shake), then fallbacks (blueberry yogurt, strawberries, oranges), and shows what giving in would cost.
- **Monthly trends** – charts built from my expense sheet: which unhealthy foods I buy most, how many calories they add up to, and how that changes month by month.

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
                                 └─► junk_food_summary.md    (summary table + notes)
```

A GitHub Action ([.github/workflows/update-and-deploy.yml](.github/workflows/update-and-deploy.yml)) runs on every push to `main`, once a day, and on demand. Each run:

1. runs `update_sheet.py` to pull the latest sheet,
2. commits the refreshed CSV, data file and summary back to `main` (only if something changed),
3. deploys `index.html` and `data/junk_food.js` to GitHub Pages.

Because the Action may add a commit after you push, run `git pull` before your next push.

## Files

| File | What it is |
|---|---|
| `index.html` | The whole site: both tabs, styles and scripts in one file. No build step. |
| `update_sheet.py` | Downloads the sheet and regenerates the data files. Python standard library only. |
| `data/expenses.csv` | The full sheet as exported by Google. |
| `data/junk_food.js` | Generated. Monthly counts, spend and summary for the trends tab. |
| `junk_food_summary.md` | Generated. The summary table, what stands out, how to read the numbers. |

To change which items count as junk food or their calorie estimates, edit `CATEGORIES` in `update_sheet.py`.

## Run it locally

```bash
python3 update_sheet.py   # pull the latest sheet (optional)
open index.html           # or just double-click it
```

No server or install needed: the page loads its data from a script file, so it works straight from disk.

## Setup notes

- The Google Sheet must stay shared as **Anyone with the link can view**, or the download fails and the script stops without overwriting anything.
- GitHub Pages must be set to deploy from **GitHub Actions**: *Settings → Pages → Build and deployment → Source: GitHub Actions*.
