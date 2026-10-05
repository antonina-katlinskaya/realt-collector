# -*- coding: utf-8 -*-
"""
Аналитика по накопленным снимкам (data/snapshots.csv).
Запуск: python analytics.py

Считает динамику, которую видно только при сравнении снимков во времени:
  - прирост просмотров за сутки по каждому объявлению;
  - новые объявления (появились);
  - снятые объявления (пропали);
  - изменения цены;
  - смена тарифа продвижения;
  - сводка по агентам и по кварталам Минск Мира.

Пишет CSV-витрины в data/analytics/ — их удобно открывать в Excel.
Пока истории мало (1-2 снимка), динамика будет пустой — это нормально,
она копится вперёд.
"""

import os
import csv
import collections
import datetime as dt

import config as C

ANALYTICS_DIR = "data/analytics"


def read_snapshots():
    if not os.path.exists(C.SNAPSHOTS_CSV):
        print("Нет данных:", C.SNAPSHOTS_CSV)
        return []
    with open(C.SNAPSHOTS_CSV, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def to_int(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def write_csv(name, fieldnames, rows):
    os.makedirs(ANALYTICS_DIR, exist_ok=True)
    path = os.path.join(ANALYTICS_DIR, name)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print("записано:", path, f"({len(rows)} строк)")


def latest_two_snapshot_times(rows):
    """Два последних момента снятия (snapshot_at)."""
    times = sorted({r["snapshot_at"] for r in rows})
    return times[-2:] if len(times) >= 2 else times


def run():
    rows = read_snapshots()
    if not rows:
        return
    times = sorted({r["snapshot_at"] for r in rows})
    print(f"Снимков во времени: {len(times)}. "
          f"Период: {times[0]} .. {times[-1]}")

    # индекс: (snapshot_at, uuid) -> row
    by_time = collections.defaultdict(dict)
    for r in rows:
        by_time[r["snapshot_at"]][r["uuid"]] = r

    # --- Витрина 1: последнее состояние каждого объявления ---
    last_time = times[-1]
    current = by_time[last_time]
    cur_rows = list(current.values())
    write_csv("current_listings.csv", list(cur_rows[0].keys()), cur_rows)

    # --- Витрина 2: сводка по агентам (на последнем снимке) ---
    agents = collections.defaultdict(lambda: {
        "contactName": "", "contactPhone": "", "contactEmail": "",
        "listings": 0, "promo_spec": 0, "promo_raise": 0,
        "promo_highlight": 0, "free": 0, "views_sum": 0, "central_only": 0,
    })
    for r in cur_rows:
        a = agents[r["userUuid"]]
        a["contactName"] = r.get("contactName", "")
        a["contactPhone"] = r.get("contactPhone", "")
        a["contactEmail"] = r.get("contactEmail", "")
        a["listings"] += 1
        ps = to_int(r.get("paymentStatus"))
        if ps == 4:
            a["promo_spec"] += 1
        elif ps == 3:
            a["promo_raise"] += 1
        elif ps == 2:
            a["promo_highlight"] += 1
        else:
            a["free"] += 1
        v = to_int(r.get("views"))
        if v:
            a["views_sum"] += v
        if r.get("is_central_only") == "1":
            a["central_only"] += 1
    agent_rows = []
    for uid, a in sorted(agents.items(), key=lambda x: -x[1]["listings"]):
        row = {"userUuid": uid}
        row.update(a)
        agent_rows.append(row)
    write_csv("agents_summary.csv",
              ["userUuid"] + list(agents[next(iter(agents))].keys()) if agents else ["userUuid"],
              agent_rows)

    # --- Витрина 3: сводка по кварталам Минск Мира ---
    quarters = collections.defaultdict(lambda: {"listings": 0, "views_sum": 0,
                                                "promo": 0})
    for r in cur_rows:
        q = r.get("quarter") or "(не определён)"
        quarters[q]["listings"] += 1
        v = to_int(r.get("views"))
        if v:
            quarters[q]["views_sum"] += v
        if to_int(r.get("paymentStatus")) in (2, 3, 4):
            quarters[q]["promo"] += 1
    q_rows = [{"quarter": q, **vals}
              for q, vals in sorted(quarters.items(), key=lambda x: -x[1]["listings"])]
    write_csv("quarters_summary.csv",
              ["quarter", "listings", "views_sum", "promo"], q_rows)

    # --- Динамика между двумя последними снимками ---
    two = latest_two_snapshot_times(rows)
    if len(two) < 2:
        print("Для динамики нужно минимум 2 снимка — пока только накапливаем.")
        return
    prev_t, cur_t = two
    prev, cur = by_time[prev_t], by_time[cur_t]

    # просмотры за период, изменения цены и тарифа
    changes = []
    for u, c in cur.items():
        p = prev.get(u)
        if not p:
            continue
        dv = None
        if to_int(c.get("views")) is not None and to_int(p.get("views")) is not None:
            dv = to_int(c["views"]) - to_int(p["views"])
        price_changed = c.get("price") != p.get("price")
        promo_changed = c.get("paymentStatus") != p.get("paymentStatus")
        if dv or price_changed or promo_changed:
            changes.append({
                "uuid": u, "code": c.get("code"),
                "contactName": c.get("contactName"),
                "quarter": c.get("quarter"),
                "views_delta": dv,
                "price_old": p.get("price") if price_changed else "",
                "price_new": c.get("price") if price_changed else "",
                "promo_old": p.get("payment_label") if promo_changed else "",
                "promo_new": c.get("payment_label") if promo_changed else "",
            })
    changes.sort(key=lambda x: -(x["views_delta"] or 0))
    write_csv("changes_last_period.csv",
              ["uuid", "code", "contactName", "quarter", "views_delta",
               "price_old", "price_new", "promo_old", "promo_new"], changes)

    # появились / пропали
    appeared = [{"uuid": u, "code": c.get("code"), "contactName": c.get("contactName"),
                 "quarter": c.get("quarter"), "price": c.get("price")}
                for u, c in cur.items() if u not in prev]
    disappeared = [{"uuid": u, "code": p.get("code"), "contactName": p.get("contactName"),
                    "quarter": p.get("quarter"), "price": p.get("price")}
                   for u, p in prev.items() if u not in cur]
    write_csv("appeared.csv",
              ["uuid", "code", "contactName", "quarter", "price"], appeared)
    write_csv("disappeared.csv",
              ["uuid", "code", "contactName", "quarter", "price"], disappeared)

    print(f"\nДинамика {prev_t} -> {cur_t}:")
    print(f"  появилось: {len(appeared)}, пропало: {len(disappeared)}, "
          f"с изменениями: {len(changes)}")


if __name__ == "__main__":
    run()
