#!/usr/bin/env python3
"""Pull the calorie counter sheet from Google Sheets and rebuild the weight data.

Run:  python3 update_weight.py

Writes:
  data/calories.csv   the whole sheet, exactly as Google exports it
  data/weight.js      weekly data + calibration for the "Weight" and "Goals" tabs in index.html

To change how a food's calories split into macros, edit FOOD_MACROS below.

Uses only the Python standard library.
"""
import csv
import io
import json
import statistics
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from update_sheet import parse_cost, parse_date

SHEET_ID = "1LqOzKup2XJUcKq8mY2su2XTyEukgkxhLAM7C6UTgNjk"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "data" / "calories.csv"
JS_PATH = ROOT / "data" / "weight.js"

# Height comes from the BMR formula in the sheet: (10 * kg) + (6.25 * 180) - (5 * age) + 5
AGE = 27
HEIGHT_CM = 180

KCAL_PER_KG = 7700
# A calorie total repeated this many days in a row looks filled in rather than logged
REPEAT_DAYS = 5
BEST_STRETCH_WEEKS = 7
HABIT_DAYS = 28
TREND_WEEKS = 8

# Share of each food's calories from (carbs, protein, fat, alcohol), in percent. These are typical
# values for that food, not measurements. Edit a row to change a food, or add a row for a new one.
# Names match the sheet's column headers, ignoring upper and lower case.
FOOD_MACROS = {
    "Biriyani": (42, 19, 39, 0),
    "Ice Cream": (45, 7, 48, 0),
    "Fanta": (100, 0, 0, 0),
    "Cookies/ Choc": (52, 5, 43, 0),
    "Chicken": (0, 65, 35, 0),
    "Eggs": (2, 34, 64, 0),
    "Candy": (95, 1, 4, 0),
    "Pizza": (45, 17, 38, 0),
    "Subway": (48, 20, 32, 0),
    "Salmon": (0, 45, 55, 0),
    "Oranges": (90, 8, 2, 0),
    "Ramen": (55, 9, 36, 0),
    "BK Sandwich": (30, 17, 53, 0),
    "Egg Dosa": (45, 20, 35, 0),
    "Small Fries": (52, 4, 44, 0),
    "Chicken Sandwich JITB": (38, 17, 45, 0),
    "Oreo Milkshake": (58, 7, 35, 0),
    "Chicken 65": (15, 35, 50, 0),
    "Protein Powder": (10, 80, 10, 0),
    "Monster": (100, 0, 0, 0),
    "Lays": (37, 5, 58, 0),
    "Smirnoff": (0, 0, 0, 100),
    "Garlic Naan": (60, 12, 28, 0),
    "Strawberries": (85, 8, 7, 0),
    "Wheat Tortilla": (65, 12, 23, 0),
    "Gulab Jamun": (60, 5, 35, 0),
    "Chicken Fajita": (30, 35, 35, 0),
    "Zero Sugar": (100, 0, 0, 0),
    "Red Bull Small": (100, 0, 0, 0),
    "French Toast": (44, 14, 42, 0),
    "Grapes": (94, 4, 2, 0),
    "Rice": (90, 8, 2, 0),
}
# A food column that isn't listed above uses this food's split until it gets its own row
DEFAULT_FOOD = "Biriyani"
SPLITS = {name.strip().lower(): split for name, split in FOOD_MACROS.items()}
for name, split in FOOD_MACROS.items():
    if sum(split) != 100:
        sys.exit(f"FOOD_MACROS: the shares for {name} add up to {sum(split)}, not 100.")

KCAL_PER_G = {"carbs": 4, "protein": 4, "fat": 9}


def food_split(name):
    return SPLITS.get(name.strip().lower(), SPLITS[DEFAULT_FOOD.lower()])


def macro_grams(foods):
    """Grams of carbs, protein and fat, plus calories from alcohol, for {food: kcal}."""
    out = {"carbs": 0.0, "protein": 0.0, "fat": 0.0, "alcoholKcal": 0.0}
    for name, kcal in foods.items():
        carbs, protein, fat, alcohol = food_split(name)
        out["carbs"] += kcal * carbs / 100 / KCAL_PER_G["carbs"]
        out["protein"] += kcal * protein / 100 / KCAL_PER_G["protein"]
        out["fat"] += kcal * fat / 100 / KCAL_PER_G["fat"]
        out["alcoholKcal"] += kcal * alcohol / 100
    return out


# The same three formulas are in index.html, which runs the projection in the browser.
def rest_kcal(kg):
    return 10 * kg + 6.25 * HEIGHT_CM - 5 * AGE + 5


def steps_kcal(kg, steps):
    return kg * 2.20462 * 0.57 * 0.00046666666 * steps


def cycling_kcal(kg, minutes):
    return 6.8 * 3.5 * kg * minutes / 200


def formula_burn(kg, steps, minutes):
    return rest_kcal(kg) + steps_kcal(kg, steps) + cycling_kcal(kg, minutes)


def download():
    print(f"Downloading {CSV_URL}")
    req = urllib.request.Request(CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode("utf-8")
    if not text.startswith("METRICS,"):
        sys.exit("The download did not look like the calorie sheet (is the sheet still shared by link?).")
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    CSV_PATH.write_text(text, encoding="utf-8")
    print(f"Saved {CSV_PATH.relative_to(ROOT)} ({text.count(chr(10))} rows)")
    return text


def read_sheet(text):
    """Daily rows up to the last day with anything logged, the Sunday weigh-ins, and the food column names."""
    grid = list(csv.reader(io.StringIO(text)))
    head = [h.strip() for h in grid[0]]
    # Every column after DEFICIT is a food, including ones added later
    food_cols = [(i, head[i]) for i in range(head.index("DEFICIT") + 1, len(head)) if head[i]]
    days, weighins = [], []
    for row in grid[1:]:
        r = dict(zip(head, row))
        d = parse_date((r.get("DATE") or "").strip())
        if d is None:
            continue
        steps_raw = (r.get("STEPS") or "").strip()
        foods = {name: parse_cost(row[i]) for i, name in food_cols if i < len(row) and row[i].strip()}
        days.append({"date": d, "kcal": parse_cost(r.get("TOTAL") or ""),
                     "steps": parse_cost(steps_raw) if steps_raw else None,
                     "cycling": parse_cost(r.get("CYCLING") or ""), "foods": foods})
        if (r.get("METRICS") or "").strip() == "Weight in KG":
            kg = parse_cost(r.get("STATS") or "")
            if kg > 0:
                weighins.append((d, kg))
    # The sheet is pre-filled with future dates, so stop at the last day with data
    last = max((i for i, x in enumerate(days) if x["kcal"] > 0 or x["steps"] is not None), default=-1)
    return days[:last + 1], weighins, [name for _, name in food_cols]


def mark_repeats(days):
    i = 0
    while i < len(days):
        j = i
        while j + 1 < len(days) and days[j + 1]["kcal"] == days[i]["kcal"]:
            j += 1
        for x in days[i:j + 1]:
            x["repeated"] = j - i + 1 >= REPEAT_DAYS and x["kcal"] > 0
        i = j + 1


def averages(days):
    kcal = [x["kcal"] for x in days if x["kcal"] > 0]
    steps = [x["steps"] for x in days if x["steps"] is not None]
    return {"kcal": round(statistics.fmean(kcal)) if kcal else None,
            "steps": round(statistics.fmean(steps)) if steps else None,
            "cycling": round(statistics.fmean(x["cycling"] for x in days), 1) if days else 0}


def average_macros(days):
    """Average per day, over the same days as the calorie average."""
    eaten = [x for x in days if x["kcal"] > 0]
    if not eaten:
        return None
    totals = [macro_grams(x["foods"]) for x in eaten]
    return {key: round(sum(m[key] for m in totals) / len(eaten)) for key in totals[0]}


def macro_table(days, food_names):
    """Every food in the sheet with the split it uses, most calories first."""
    eaten = {name: sum(x["foods"].get(name, 0) for x in days) for name in food_names}
    rows = []
    for name in sorted(food_names, key=lambda n: eaten[n], reverse=True):
        carbs, protein, fat, alcohol = food_split(name)
        rows.append({"food": name, "carbs": carbs, "protein": protein, "fat": fat, "alcohol": alcohol})
    return {"default": DEFAULT_FOOD, "foods": rows,
            "assumed": [n for n in food_names if n.strip().lower() not in SPLITS]}


def build_weeks(days, weighins):
    weeks = []
    for i, (start, kg) in enumerate(weighins):
        next_kg = weighins[i + 1][1] if i + 1 < len(weighins) else None
        end = start + timedelta(days=7)
        span = [x for x in days if start <= x["date"] < end]
        avg = averages(span)
        repeated = sum(x["repeated"] for x in span)
        weeks.append({"start": start.isoformat(), "kg": kg,
                      "change": round(next_kg - kg, 1) if next_kg is not None else None,
                      "kcal": avg["kcal"], "macros": average_macros(span), "steps": avg["steps"],
                      "cyclingMin": round(sum(x["cycling"] for x in span)),
                      "cyclingDays": sum(x["cycling"] > 0 for x in span),
                      "days": len(span), "repeatedDays": repeated,
                      "estimated": repeated >= 4})
    return weeks


def week_gap(w):
    """Calories a day the weigh-ins imply were burned, minus what the formulas say was burned."""
    kg_mid = w["kg"] + w["change"] / 2
    implied = w["kcal"] - w["change"] * KCAL_PER_KG / 7
    return implied - formula_burn(kg_mid, w["steps"], w["cyclingMin"] / 7)


def calibrate(weeks):
    """The formulas never match the scale exactly, so measure the gap on weeks with real logs only.
    Returns the gap, plus a check: fit on the earlier logged blocks, predict the latest block."""
    real = [w for w in weeks if w["change"] is not None and w["kcal"] and w["steps"] is not None
            and w["days"] == 7 and w["repeatedDays"] == 0]
    if len(real) < 4:
        print("  WARNING: fewer than 4 fully logged weeks, so the projection isn't calibrated")
        return {"offset": 0, "weeks": len(real), "check": None}
    offset = statistics.fmean(week_gap(w) for w in real)

    # Latest unbroken run of logged weeks
    block = [real[-1]]
    for w in reversed(real[:-1]):
        if date.fromisoformat(block[0]["start"]) - date.fromisoformat(w["start"]) != timedelta(days=7):
            break
        block.insert(0, w)
    earlier = [w for w in real if w not in block]
    check = None
    if len(block) >= 3 and len(earlier) >= 4:
        fit = statistics.fmean(week_gap(w) for w in earlier)
        predicted = sum((w["kcal"] - formula_burn(w["kg"] + w["change"] / 2, w["steps"], w["cyclingMin"] / 7) - fit)
                        * 7 / KCAL_PER_KG for w in block)
        check = {"from": block[0]["start"], "weeks": len(block), "offset": round(fit),
                 "predicted": round(predicted, 1), "actual": round(sum(w["change"] for w in block), 1)}
    return {"offset": round(offset), "weeks": len(real), "check": check}


def best_stretch(weeks, days):
    """The run of weeks with the most weight lost, and what you were doing during it."""
    done = [w for w in weeks if w["change"] is not None]
    if len(done) < BEST_STRETCH_WEEKS:
        return None
    runs = [done[i:i + BEST_STRETCH_WEEKS] for i in range(len(done) - BEST_STRETCH_WEEKS + 1)]
    run = min(runs, key=lambda rs: sum(w["change"] for w in rs))
    start = date.fromisoformat(run[0]["start"])
    end = start + timedelta(days=7 * BEST_STRETCH_WEEKS)
    avg = averages([x for x in days if start <= x["date"] < end])
    change = sum(w["change"] for w in run)
    return {**avg, "from": start.isoformat(), "to": (end - timedelta(days=1)).isoformat(),
            "kg": round(change, 1), "perWeek": round(change / BEST_STRETCH_WEEKS, 2)}


def build(text):
    days, weighins, food_names = read_sheet(text)
    if not days or len(weighins) < 2:
        sys.exit("Not enough dated rows or weigh-ins found in the sheet.")
    mark_repeats(days)
    weeks = build_weeks(days, weighins)
    recent = days[-HABIT_DAYS:]
    trend = weighins[-TREND_WEEKS:]
    slope = statistics.linear_regression(range(len(trend)), [kg for _, kg in trend]).slope
    repeats = [x for x in days if x["repeated"]]
    return {
        "generated": date.today().isoformat(),
        "source": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}",
        "profile": {"age": AGE, "sex": "male", "heightCm": HEIGHT_CM},
        "asOf": days[-1]["date"].isoformat(),
        "weeks": weeks,
        "calibration": calibrate(weeks),
        "habits": {**averages(recent), "from": recent[0]["date"].isoformat(), "days": len(recent)},
        "best": best_stretch(weeks, days),
        "trend": {"kgPerWeek": round(slope, 2), "weeks": len(trend)},
        "repeats": {"days": len(repeats), "of": len(days)},
        "macros": macro_table(days, food_names),
    }


def write_js(data):
    JS_PATH.write_text(
        "// Generated by update_weight.py - do not edit by hand.\n"
        f"window.WEIGHT = {json.dumps(data, separators=(',', ':'))};\n", encoding="utf-8")
    print(f"Saved {JS_PATH.relative_to(ROOT)}")


def main():
    data = build(download())
    write_js(data)
    last, cal, hab = data["weeks"][-1], data["calibration"], data["habits"]
    print(f"{len(data['weeks'])} weigh-ins, latest {last['kg']} kg on {last['start']}; "
          f"data through {data['asOf']}.")
    print(f"Calibration: {cal['offset']:+d} kcal/day from {cal['weeks']} logged weeks. "
          f"Last {hab['days']} days: {hab['kcal']} kcal, {hab['steps']} steps, {hab['cycling']} min cycling.")
    if data["macros"]["assumed"]:
        print(f"New foods using the {DEFAULT_FOOD} macro split until they're added to FOOD_MACROS: "
              + ", ".join(data["macros"]["assumed"]))


if __name__ == "__main__":
    main()
