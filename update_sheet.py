#!/usr/bin/env python3
"""Pull the latest expense sheet from Google Sheets and rebuild the junk-food data.

Run:  python3 update_sheet.py

Writes:
  data/expenses.csv        the whole sheet, exactly as Google exports it
  data/junk_food.js        monthly data + summary for the "Monthly trends" tab in index.html
  junk_food_summary.md     the summary table, what stands out, and how to read the numbers
  data/finance.js          monthly income, spending, savings and money sent to India for the "Finances" tab

Uses only the Python standard library.
"""
import csv
import io
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

SHEET_ID = "1MqDTTYAaOMJlVUXANq-wRVnRp2D-lC3MghtbqzBi6ME"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "data" / "expenses.csv"
JS_PATH = ROOT / "data" / "junk_food.js"
MD_PATH = ROOT / "junk_food_summary.md"
FIN_PATH = ROOT / "data" / "finance.js"

# First month of regular salary; the Finances tab starts here
SALARY_START = date(2026, 2, 1)

KCAL_PER_LB = 3500
KG_PER_LB = 0.4536

GROUPS = [
    {"id": "takeout", "name": "Takeout & fast food"},
    {"id": "drinks", "name": "Drinks"},
    {"id": "sweets", "name": "Sweets"},
    {"id": "snacks", "name": "Snacks & processed"},
    {"id": "staples", "name": "Cooking staples"},
]

# Order matters: the first pattern that matches an item name wins.
# kcal is the estimated calories you eat per purchase (the typical size bought, or your share of a shared pack).
CATEGORIES = [
    {"name": "Ice cream", "plural": "ice creams", "group": "sweets", "kcal": 1200,
     "pattern": r"ice ?cream|popsicle"},
    {"name": "Oreo milkshakes", "plural": "milkshakes", "group": "takeout", "kcal": 700,
     "pattern": r"milkshake|milk shake"},
    {"name": "Fudge / brownies / cake / cookies", "plural": "desserts", "group": "sweets", "kcal": 700,
     "pattern": r"fudge|brownie|cake|cookie|chips ahoy|oreo|donut|muffin"},
    {"name": "Biryani (restaurant / Uber Eats)", "plural": "biryanis", "group": "takeout", "kcal": 1200,
     "pattern": r"biri?y?i?ani|biryani|biryiani"},
    {"name": "Burger King / burger meals", "plural": "burger meals", "group": "takeout", "kcal": 1000,
     "pattern": r"burger"},
    {"name": "Popeyes / KFC / fried chicken", "plural": "fried-chicken orders", "group": "takeout", "kcal": 1100,
     "pattern": r"popeye|kfc|fried chicken|chicken sandwh?ich|chilli chicken|chicken masala|\bwings?\b|wingstop|tenders"},
    {"name": "Subway", "plural": "Subway sandwiches", "group": "takeout", "kcal": 1000,
     "pattern": r"subway"},
    {"name": "Pizza (Pizza Hut, Domino's, frozen)", "plural": "pizzas", "group": "takeout", "kcal": 1000,
     "pattern": r"pizza"},
    {"name": "Soda (Fanta, Mtn Dew, Coke, fountain)", "plural": "sodas", "group": "drinks", "kcal": 250,
     "pattern": r"soda|fanta|dew|pepsi|coke|sprite|ginger ale|dr\.? ?pepper|root beer", "sugary": True},
    {"name": "Sunny D / orange juice", "plural": "juices", "group": "drinks", "kcal": 480,
     "pattern": r"sunny|orange juice|fruit punch|juice pops", "sugary": True},
    {"name": "Monster / Red Bull", "plural": "energy drinks", "group": "drinks", "kcal": 230,
     "pattern": r"monster|red ?bull|energy|celsius", "sugary": True},
    {"name": "Nutella / chocolate spread", "plural": "Nutella jars", "group": "sweets", "kcal": 2000,
     "pattern": r"nutella|chocolate spread"},
    {"name": "Chocolate bars (Reese's, Hershey's, Kit Kat)", "plural": "chocolate bars", "group": "sweets", "kcal": 450,
     "pattern": r"reese|hersh|kit ?kat|kisses|snicker|twix|m&m|chocolate(?!.*(spread|cereal|crunch))"},
    {"name": "Chips (Lays, Cheetos, Pringles, Kurkure, Bhujia)", "plural": "bags of chips", "group": "snacks", "kcal": 900,
     "pattern": r"lays|cheetos|pringles|kurkure|bhujia|chips|doritos|takis"},
    {"name": "Gas-station \"Snacks\" (QT, airport)", "plural": "snack runs", "group": "snacks", "kcal": 900,
     "pattern": r"^snacks$|qt snacks|^snack"},
    {"name": "Popcorn (Act II packs)", "plural": "popcorn packs", "group": "snacks", "kcal": 1500,
     "pattern": r"pop ?corn"},
    {"name": "Frozen nuggets / strips / patties", "plural": "nugget bags", "group": "snacks", "kcal": 1500,
     "pattern": r"nugget|chicken strips|patties|patty"},
    {"name": "Hot dogs / franks / bologna / sausage / buns", "plural": "hot-dog packs", "group": "snacks", "kcal": 800,
     "pattern": r"hot ?dog|frank|sausage|bologna|pepperoni|buns?\b"},
    {"name": "Maggi / Top Ramen", "plural": "noodle packs", "group": "snacks", "kcal": 1800,
     "pattern": r"maggi|ramen|noodle"},
    {"name": "Beer / alcohol", "plural": "drinks", "group": "drinks", "kcal": 900,
     "pattern": r"beer|vodka|wine|whisk|rum\b|tequila"},
    {"name": "Cheese slices", "plural": "cheese packs", "group": "snacks", "kcal": 900,
     "pattern": r"cheese"},
    {"name": "Ketchup / mayo / ranch / jelly", "plural": "condiments", "group": "staples", "kcal": 600, "staple": True,
     "pattern": r"ketchup|mayo|ranch|jelly|jam\b"},
    {"name": "Ghee / butter", "plural": "ghee/butter packs", "group": "staples", "kcal": 3000, "staple": True,
     "pattern": r"ghee|(?<!peanut )butter(?!milk)"},
    {"name": "Sugar", "plural": "sugar bags", "group": "staples", "kcal": 3000, "staple": True,
     "pattern": r"\bsugar\b"},
    {"name": "Fries", "plural": "fries", "group": "takeout", "kcal": 400,
     "pattern": r"\bfries"},
    {"name": "Buffets / parotta / other restaurant", "plural": "restaurant meals", "group": "takeout", "kcal": 1300,
     "pattern": r"parotta|buffet|fried rice|tacos?\b|del taco|panda|mcdonald|wendy|taco bell|domino|jack in|whataburger|chick-fil|shawarma"},
]
for c in CATEGORIES:
    c["re"] = re.compile(c["pattern"])

# Matched only to keep them out of the categories above; not counted as junk food.
SKIP = re.compile(r"\btax\b|drawing board|peanut butter|cereal|granola|corn flakes|kashi|raisin bran|gatorade")


def download():
    print(f"Downloading {CSV_URL}")
    req = urllib.request.Request(CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8")
    if not text.startswith("Date,"):
        sys.exit("The download did not look like the expense sheet (is the sheet still shared by link?).")
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    CSV_PATH.write_text(text, encoding="utf-8")
    print(f"Saved {CSV_PATH.relative_to(ROOT)} ({text.count(chr(10))} rows)")
    return text


def parse_cost(s):
    s = s.strip().replace("$", "").replace(",", "")
    neg = s.startswith("(") or s.startswith("-")
    s = s.strip("()-")
    try:
        v = float(s)
    except ValueError:
        return 0.0
    return -v if neg else v


MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_date(raw):
    # The sheet mixes "5-Aug-2023" with "1-June-2025" and "3-Sept-2025", so match on the first three letters
    m = re.fullmatch(r"(\d{1,2})-([A-Za-z]+)-(\d{4})", raw)
    if m and m.group(2)[:3].lower() in MONTHS:
        return date(int(m.group(3)), MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def read_rows(text):
    rows = []
    first = None
    for r in csv.DictReader(io.StringIO(text)):
        item = (r.get("One Time Expense ") or "").strip()
        raw = (r.get("Date") or "").strip()
        if not item or not raw:
            continue
        d = parse_date(raw)
        if d is None:
            print(f"  skipped row with unreadable date: {raw!r} {item!r}")
            continue
        if first is None:
            first = d
        # The log is in date order, so a date before the first row is a mistyped year (e.g. 30-Jan-2023 among Jan 2024 rows)
        while d < first:
            d = d.replace(year=d.year + 1)
        rows.append({"date": d, "item": item, "cost": parse_cost(r.get("Cost") or ""),
                     "mode": (r.get("Payment Mode") or "").strip(), "type": (r.get("Expense Type") or "").strip()})
    return rows


def categorize(item):
    s = item.lower()
    if SKIP.search(s):
        return None
    for c in CATEGORIES:
        if c["re"].search(s):
            return c
    return None


def month_key(d):
    return f"{d.year}-{d.month:02d}"


def build(rows):
    first, last = rows[0]["date"], max(r["date"] for r in rows)
    months = []
    y, m = first.year, first.month
    while (y, m) <= (last.year, last.month):
        months.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    idx = {k: i for i, k in enumerate(months)}

    stats = {c["name"]: {"n": 0, "spent": 0.0, "nYear": 0, "kcalBefore": 0,
                         "mn": [0] * len(months), "ms": [0.0] * len(months)} for c in CATEGORIES}
    year = last.year
    for r in rows:
        c = categorize(r["item"])
        if not c:
            continue
        s = stats[c["name"]]
        i = idx[month_key(r["date"])]
        s["n"] += 1
        s["spent"] += r["cost"]
        s["mn"][i] += 1
        s["ms"][i] += r["cost"]
        if r["date"].year == year:
            s["nYear"] += 1
        else:
            s["kcalBefore"] += c["kcal"]

    items = []
    for c in CATEGORIES:
        s = stats[c["name"]]
        if not s["n"]:
            continue
        total = s["n"] * c["kcal"]
        items.append({
            "name": c["name"], "plural": c["plural"], "group": c["group"], "kcal": c["kcal"],
            "staple": bool(c.get("staple")), "sugary": bool(c.get("sugary")),
            "n": s["n"], "nYear": s["nYear"], "spent": round(s["spent"], 2), "totalKcal": total,
            "lb": round(total / KCAL_PER_LB, 1), "kg": round(total / KCAL_PER_LB * KG_PER_LB, 1),
            "kcalBefore": s["kcalBefore"],
            "monthly": {"n": s["mn"], "spent": [round(v, 2) for v in s["ms"]]},
        })
    items.sort(key=lambda it: it["totalKcal"], reverse=True)

    total_kcal = sum(it["totalKcal"] for it in items)
    totals = {
        "n": sum(it["n"] for it in items),
        "spent": round(sum(it["spent"] for it in items), 2),
        "kcal": total_kcal,
        "lb": round(total_kcal / KCAL_PER_LB),
        "kg": round(total_kcal / KCAL_PER_LB * KG_PER_LB),
    }

    year_start = date(year, 1, 1)
    days_year = (last - year_start).days + 1
    days_before = (year_start - first).days
    kcal_year = sum(it["nYear"] * it["kcal"] for it in items)
    kcal_before = sum(it["kcalBefore"] for it in items)
    rate_year = round(kcal_year / days_year) if days_year > 0 else 0
    rate_before = round(kcal_before / days_before) if days_before > 0 else None
    totals.update({"year": year, "kcalPerDayYear": rate_year, "kcalPerDayBefore": rate_before})

    data = {
        "generated": date.today().isoformat(),
        "source": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}",
        "first": first.isoformat(), "last": last.isoformat(),
        "months": months, "groups": GROUPS, "items": items, "totals": totals,
        "insights": insights(items, totals, first, days_year),
        "notes": NOTES,
    }
    for it in items:
        del it["kcalBefore"]
    return data


def money(v):
    return f"${v:,.0f}"


def num(v):
    return f"{v:,.0f}"


def round_to(v, step):
    return int(round(v / step) * step)


def insights(items, totals, first, days_year):
    year = totals["year"]
    out = []
    since = first.strftime("%B %Y")

    rate_y, rate_b = totals["kcalPerDayYear"], totals["kcalPerDayBefore"]
    top_year = sorted((it for it in items if it["nYear"]), key=lambda it: it["nYear"], reverse=True)[:3]
    if rate_b and top_year:
        parts = [f"{it['nYear']} of the {it['n']} {it['plural']}" for it in top_year]
        listed = ", ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else parts[0]
        if rate_y > rate_b:
            title = f"{year} is much worse than the earlier years."
        else:
            title = f"{year} is running at or below your earlier pace."
        out.append({"title": title, "body":
                    f"Of all the purchases since {since}, {year} so far has {listed}. "
                    f"Your junk-food rate went from about {num(round_to(rate_b, 10))} kcal/day before {year} "
                    f"to about {num(round_to(rate_y, 10))} kcal/day in {year}."})

    top = items[0]
    top_money = max(items, key=lambda it: it["spent"]) is top
    per_week = top["nYear"] / (days_year / 7) if days_year else 0
    short = top["name"].split(" (")[0]
    out.append({"title": f"{short} is the biggest problem.", "body":
                f"It's the top item by calories{' and by money' if top_money else ''} ({money(top['spent'])} spent), "
                f"and you've had it about {per_week:.1f} times a week in {year}."})

    sugary = [it for it in items if it["sugary"]]
    if sugary:
        n = sum(it["n"] for it in sugary)
        k = sum(it["totalKcal"] for it in sugary)
        names = [it["name"].split(" (")[0].split(" /")[0] for it in sugary]
        listed = ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0]
        out.append({"title": "Drinks add up even though each one seems small.", "body":
                    f"{listed} together are {num(n)} purchases, about {num(round_to(k, 1000))} kcal "
                    f"or {round(k / KCAL_PER_LB)} lb."})

    takeout = [it for it in items if it["group"] == "takeout"]
    t_spent = sum(it["spent"] for it in takeout)
    pct = round(100 * t_spent / totals["spent"]) if totals["spent"] else 0
    out.append({"title": "Takeout is where the money goes.", "body":
                f"Biryani, burgers, fried chicken, pizza, Subway and other restaurant meals account for "
                f"{money(t_spent)}, {pct}% of the {money(totals['spent'])} spent on everything in this table."})
    return out


NOTES = [
    {"title": "Calories per purchase are estimates.",
     "body": "The sheet records prices, not quantities. Each estimate is based on the typical size bought, "
             "judging from the price. For grocery items marked \"Group\" it assumes you ate your share, not the whole pack."},
    {"title": "The weight column is a ceiling, not a prediction.",
     "body": "It uses 3,500 kcal ≈ 1 lb and only counts if those calories were eaten on top of your normal needs. "
             "In reality a biryani replaces a meal instead of being added to one. Read it as how much each item "
             "contributes to a surplus, for comparison, not as pounds you actually gained."},
    {"title": "Left out:",
     "body": "cereal and granola (mostly Kashi and corn flakes, which aren't really junk), peanut butter, Gatorade and tax lines."},
]


def find_cell(grid, text):
    for r, row in enumerate(grid):
        for c, v in enumerate(row):
            if v.strip() == text:
                return r, c
    return None


def parse_month(raw):
    m = re.fullmatch(r"([A-Za-z]+)-(\d{4})", raw.strip())
    if m and m.group(1)[:3].lower() in MONTHS:
        return f"{m.group(2)}-{MONTHS[m.group(1)[:3].lower()]:02d}"
    d = parse_date(raw.strip())
    return month_key(d) if d else None


def add_months(key, n):
    y, m = map(int, key.split("-"))
    m += n
    return f"{y + (m - 1) // 12}-{(m - 1) % 12 + 1:02d}"


def table_below(grid, header):
    """Rows under a header cell whose left neighbour is a date: [(date text, value text)] until the date runs out."""
    pos = find_cell(grid, header)
    if not pos:
        print(f"  note: no '{header}' table found in the sheet")
        return []
    r, c = pos
    out = []
    for row in grid[r + 1:]:
        when = row[c - 1].strip() if len(row) > c else ""
        if not when:
            break
        out.append((when, row[c].strip()))
    return out


def inferred_paychecks(grid):
    """Month totals from the undated earnings list: two "Biweekly n" paychecks a month from SALARY_START.
    Entries after a paycheck (like the tax withholding refund) count in that paycheck's month."""
    head = grid[0]
    amount_col, label_col = head.index("Earnings"), head.index("Earnings") + 1
    start = month_key(SALARY_START)
    totals, month = {}, None
    for row in grid[1:]:
        label = row[label_col].strip() if len(row) > label_col else ""
        m = re.fullmatch(r"Biweekly (\d+)", label)
        if m:
            month = add_months(start, (int(m.group(1)) - 1) // 2)
        if month and label:
            totals[month] = totals.get(month, 0) + parse_cost(row[amount_col])
    return totals


def build_finance(text, rows):
    grid = list(csv.reader(io.StringIO(text)))
    start = month_key(SALARY_START)
    last = max(r["date"] for r in rows)
    months = []
    k = start
    while k <= month_key(last):
        months.append(k)
        k = add_months(k, 1)
    f = {k: {"month": k, "paycheck": 0.0, "paycheckInferred": False, "tuition": 0.0, "expenses": 0.0,
             "loanPaid": 0.0, "india": 0.0, "invested": 0.0} for k in months}

    # Paychecks: your monthly Paycheck table where it's filled in, otherwise counted from the earnings list
    entered = {}
    for when, value in table_below(grid, "Paycheck"):
        k = parse_month(when)
        if k and value:
            entered[k] = parse_cost(value)
    inferred = inferred_paychecks(grid)
    for k in months:
        if k in entered:
            f[k]["paycheck"] = entered[k]
        elif inferred.get(k):
            f[k]["paycheck"] = inferred[k]
            f[k]["paycheckInferred"] = True

    for when, value in table_below(grid, "Tuition Salary"):
        d = parse_date(when)
        if d and month_key(d) in f:
            f[month_key(d)]["tuition"] += parse_cost(value)

    # Spending from the main log, by the date it happened. Only salary-paid ("Earnings") rows reduce savings.
    for r in rows:
        k = month_key(r["date"])
        if k not in f:
            continue
        if r["mode"] != "Earnings":
            f[k]["loanPaid"] += r["cost"]
        elif re.search(r"\bto india\b", r["item"], re.I):
            f[k]["india"] += r["cost"]
        elif r["type"] == "Investment":
            f[k]["invested"] += r["cost"]
        else:
            f[k]["expenses"] += r["cost"]

    out = []
    for k in months:
        m = f[k]
        m["income"] = m["paycheck"] + m["tuition"]
        m["saved"] = m["income"] - m["expenses"] - m["india"] - m["invested"]
        out.append({key: round(v, 2) if isinstance(v, float) else v for key, v in m.items()})

    total = lambda key: round(sum(m[key] for m in out), 2)
    return {
        "generated": date.today().isoformat(),
        "start": start,
        "asOf": last.isoformat(),
        "months": out,
        "totals": {key: total(key) for key in ("paycheck", "tuition", "income", "expenses", "loanPaid", "india", "invested", "saved")},
    }


def write_finance(data):
    FIN_PATH.write_text(
        "// Generated by update_sheet.py - do not edit by hand.\n"
        f"window.FINANCE = {json.dumps(data, separators=(',', ':'))};\n", encoding="utf-8")
    print(f"Saved {FIN_PATH.relative_to(ROOT)}")


def write_js(data):
    JS_PATH.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    JS_PATH.write_text(
        "// Generated by update_sheet.py - do not edit by hand.\n"
        f"window.JUNK_FOOD = {body};\n", encoding="utf-8")
    print(f"Saved {JS_PATH.relative_to(ROOT)}")


def write_md(data):
    t = data["totals"]
    first = datetime.fromisoformat(data["first"]).strftime("%b %Y")
    d = datetime.fromisoformat(data["last"])
    last = f"{d:%b} {d.day}, {d.year}"
    lines = [
        "# Junk food I buy most often",
        "",
        f"From my expense sheet, {first} – {last}. Generated {data['generated']} by `update_sheet.py`.",
        "",
        "## Summary table",
        "",
        "| # | Item | Times bought | $ spent | Est. kcal per purchase | Total kcal | Weight equivalent |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, it in enumerate(data["items"], 1):
        name = it["name"] + (" †" if it["staple"] else "")
        lines.append(f"| {i} | {name} | {it['n']} | {money(it['spent'])} | {num(it['kcal'])} | "
                     f"{num(it['totalKcal'])} | {it['lb']} lb / {it['kg']} kg |")
    lines += [
        f"| | **Total** | **{num(t['n'])}** | **{money(t['spent'])}** | | **{num(t['kcal'])} kcal** | "
        f"**~{t['lb']} lb / {t['kg']} kg** |",
        "",
        "† Cooking staples (ghee, butter, sugar, condiments): these last a long time and are shared, "
        "so their calorie numbers are the roughest guesses here.",
        "",
        "## What stands out",
        "",
    ]
    lines += [f"- **{x['title']}** {x['body']}" for x in data["insights"]]
    lines += ["", "## How to read these numbers", ""]
    lines += [f"- **{x['title']}** {x['body']}" for x in data["notes"]]
    MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved {MD_PATH.relative_to(ROOT)}")


def main():
    text = download()
    rows = read_rows(text)
    if not rows:
        sys.exit("No dated rows found in the sheet.")
    data = build(rows)
    write_js(data)
    write_md(data)
    fin = build_finance(text, rows)
    write_finance(fin)
    t = data["totals"]
    print(f"{t['n']} junk-food purchases, {money(t['spent'])}, ~{num(t['kcal'])} kcal "
          f"({data['first']} to {data['last']}).")
    ft = fin["totals"]
    print(f"Since {fin['start']}: income {money(ft['income'])}, saved {money(ft['saved'])}, "
          f"sent to India {money(ft['india'])}, invested {money(ft['invested'])}.")


if __name__ == "__main__":
    main()
