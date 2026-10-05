# -*- coding: utf-8 -*-
"""
Сборщик аналитики по объявлениям Этажей в Минск Мире на Realt.by.

Что делает за один прогон:
  1. Проходит все страницы списка каждого агентства (анонимно, с паузами).
  2. Оставляет только объявления Минск Мира.
  3. Добирает текущие просмотры по всем uuid.
  4. Для новых объявлений один раз восстанавливает историю просмотров по дням.
  5. Пишет: сырой снимок (архив), строки в snapshots.csv, реестр seen.
  6. Формирует короткий текстовый отчёт.

Запускается без аргументов: python collector.py
Авторизация НЕ используется — только публичные анонимные запросы.
"""

import os
import csv
import json
import time
import random
import datetime as dt

import requests

import config as C
import queries as Q


# ----------------------------- вспомогательное -----------------------------

def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def today_str():
    return now_utc().strftime("%Y-%m-%d")


def ensure_dirs():
    for d in (C.DATA_DIR, C.RAW_DIR, C.REPORTS_DIR):
        os.makedirs(d, exist_ok=True)


def sleep_between(bounds):
    """Пауза: либо кортеж (min,max) со случайной задержкой, либо число."""
    if isinstance(bounds, (tuple, list)):
        time.sleep(random.uniform(bounds[0], bounds[1]))
    else:
        time.sleep(bounds)


def gql(session, query, variables, op_name):
    """
    Один запрос к GraphQL с повторами. Тело — массив с одним объектом,
    как шлёт сам сайт. Возвращает первый элемент ответа (dict) или кидает.
    """
    payload = [{"operationName": op_name, "variables": variables, "query": query}]
    last_err = None
    for attempt in range(1, C.RETRIES + 1):
        try:
            r = session.post(C.GRAPHQL_URL, json=payload, timeout=30)
            r.raise_for_status()
            data = r.json()
            return data[0]
        except Exception as e:  # noqa: BLE001 - любую сетевую ошибку повторяем
            last_err = e
            wait = attempt * 3
            print(f"    [попытка {attempt}/{C.RETRIES}] ошибка: {e}; жду {wait}с")
            time.sleep(wait)
    raise RuntimeError(f"запрос {op_name} не удался после {C.RETRIES} попыток: {last_err}")


# ----------------------------- фильтр Минск Мир ----------------------------

def is_minsk_mir(obj):
    """True, если объявление относится к Минск Миру (улица из списка ИЛИ метро)."""
    if obj.get("streetUuid") in C.MINSK_MIR_STREET_UUIDS:
        return True
    if obj.get("metroStationName") == C.MINSK_MIR_METRO:
        return True
    return False


def detect_quarter(title):
    """Определяет квартал (дом) Минск Мира по слову в заголовке; '' если не найдено."""
    if not title:
        return ""
    low = title.lower()
    for q in C.MINSK_MIR_QUARTERS:
        if q.lower() in low:
            return q
    return ""


# --------------------------- сбор списка агентства -------------------------

def fetch_agency_listings(session, agency_uuid):
    """Проходит все страницы searchObjects для агентства, возвращает список объявлений."""
    variables = {
        "data": {
            "where": {
                "agencyUuids": [agency_uuid],
                "addressV2": [{"townUuid": C.TOWN_UUID}],
                "category": C.CATEGORY,
            },
            "pagination": {"page": 1, "pageSize": C.PAGE_SIZE},
            "sort": [{"by": "newAgainDate", "order": "DESC"}],
            "extraFields": None,
            "isReactAdaptiveUA": True,
        }
    }

    first = gql(session, Q.SEARCH_OBJECTS_QUERY, variables, "searchObjects")
    if first.get("errors"):
        raise RuntimeError(f"searchObjects вернул ошибку: {first['errors']}")
    body = first["data"]["searchObjects"]["body"]
    total = body["pagination"]["totalCount"]
    pages = (total + C.PAGE_SIZE - 1) // C.PAGE_SIZE
    results = list(body["results"])
    print(f"    всего по Минску: {total}, страниц: {pages}")

    for page in range(2, pages + 1):
        sleep_between(C.PAUSE_BETWEEN_PAGES)
        variables["data"]["pagination"]["page"] = page
        resp = gql(session, Q.SEARCH_OBJECTS_QUERY, variables, "searchObjects")
        if resp.get("errors"):
            print(f"    стр.{page}: ошибка, пропускаю")
            continue
        results.extend(resp["data"]["searchObjects"]["body"]["results"])
        print(f"    стр.{page}/{pages} готово, собрано {len(results)}")

    return results


# --------------------------- просмотры -------------------------------------

def fetch_views(session, uuids):
    """Текущие просмотры пачками. Возвращает dict uuid -> int(views)."""
    out = {}
    for i in range(0, len(uuids), C.VIEWS_BATCH_SIZE):
        batch = uuids[i:i + C.VIEWS_BATCH_SIZE]
        resp = gql(session, Q.VIEWS_QUERY, {"uuids": batch}, "v")
        if resp.get("errors"):
            print(f"    просмотры: пачка {i} ошибка, пропускаю")
        else:
            arr = resp["data"]["objectsViewsCountsByUuids"]
            # ответ в том же порядке, что batch
            for u, item in zip(batch, arr):
                try:
                    out[u] = int(item["views"])
                except (TypeError, ValueError, KeyError):
                    out[u] = None
        if i + C.VIEWS_BATCH_SIZE < len(uuids):
            sleep_between(C.PAUSE_BETWEEN_VIEW_BATCHES)
    return out


def fetch_view_history(session, uuid):
    """
    Для одного объявления тянет накопленные просмотры на несколько дат в прошлом.
    Возвращает dict 'YYYY-MM-DD' -> int(views). Используется один раз для новых.
    """
    hist = {}
    base = now_utc()
    for days in [0] + C.HISTORY_DAYS_BACK:
        ref = (base - dt.timedelta(days=days)).strftime("%Y-%m-%d")
        variables = {"data": {"uuid": uuid, "referenceDate": ref}}
        resp = gql(session, Q.VIEWS_BY_DATE_QUERY, variables, "d")
        if not resp.get("errors"):
            try:
                hist[ref] = int(
                    resp["data"]["objectsDetailViewsCountByUuidAndDate"]["views"]
                )
            except (TypeError, ValueError, KeyError):
                hist[ref] = None
        sleep_between(C.PAUSE_BETWEEN_HISTORY)
    return hist


# --------------------------- хранение --------------------------------------

def load_seen():
    if os.path.exists(C.SEEN_JSON):
        with open(C.SEEN_JSON, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_seen(seen):
    with open(C.SEEN_JSON, "w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=1)


# Колонки CSV: что хотим видеть в Excel. Сырой полный ответ лежит в raw/.
CSV_FIELDS = [
    "snapshot_at", "agency", "uuid", "code", "userUuid", "contactName",
    "contactEmail", "contactPhone", "is_central_only", "agencyName",
    "quarter", "streetName", "houseNumber", "address", "metroStationName",
    "price", "priceCurrency", "pricePerM2", "priceChangeDirection",
    "priceChangeDate", "areaTotal", "rooms", "storey", "storeys",
    "buildingYear", "availableQuarter", "paymentStatus", "payment_label",
    "customSorting", "isObjectInRealtyDeal", "has3dTour", "hasVideo",
    "createdAt", "updatedAt", "views", "title",
]


def obj_to_row(obj, agency_key, snapshot_at, views_map):
    phones = obj.get("contactPhones") or []
    email = obj.get("contactEmail") or ""
    central_only = 1 if email == "etagiinternational@gmail.com" else 0
    ps = obj.get("paymentStatus")
    return {
        "snapshot_at": snapshot_at,
        "agency": agency_key,
        "uuid": obj.get("uuid"),
        "code": obj.get("code"),
        "userUuid": obj.get("userUuid"),
        "contactName": obj.get("contactName"),
        "contactEmail": email,
        "contactPhone": phones[0] if phones else "",
        "is_central_only": central_only,
        "agencyName": obj.get("agencyName"),
        "quarter": detect_quarter(obj.get("title")),
        "streetName": obj.get("streetName"),
        "houseNumber": obj.get("houseNumber"),
        "address": obj.get("address"),
        "metroStationName": obj.get("metroStationName"),
        "price": obj.get("price"),
        "priceCurrency": obj.get("priceCurrency"),
        "pricePerM2": obj.get("pricePerM2"),
        "priceChangeDirection": obj.get("priceChangeDirection"),
        "priceChangeDate": obj.get("priceChangeDate"),
        "areaTotal": obj.get("areaTotal"),
        "rooms": obj.get("rooms"),
        "storey": obj.get("storey"),
        "storeys": obj.get("storeys"),
        "buildingYear": obj.get("buildingYear"),
        "availableQuarter": obj.get("availableQuarter"),
        "paymentStatus": ps,
        "payment_label": C.PAYMENT_STATUS.get(ps, str(ps)),
        "customSorting": obj.get("customSorting"),
        "isObjectInRealtyDeal": obj.get("isObjectInRealtyDeal"),
        "has3dTour": obj.get("has3dTour"),
        "hasVideo": obj.get("hasVideo"),
        "createdAt": obj.get("createdAt"),
        "updatedAt": obj.get("updatedAt"),
        "views": views_map.get(obj.get("uuid")),
        "title": obj.get("title"),
    }


def append_snapshot_rows(rows):
    new_file = not os.path.exists(C.SNAPSHOTS_CSV)
    with open(C.SNAPSHOTS_CSV, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow(r)


# --------------------------- отчёт -----------------------------------------

def build_report(agency_key, mm_objs, views_map, new_uuids):
    lines = []
    lines.append(f"Отчёт сбора — {agency_key} — {now_utc():%Y-%m-%d %H:%M} UTC")
    lines.append(f"Объявлений в Минск Мире: {len(mm_objs)}")
    lines.append(f"Новых (впервые замечены): {len(new_uuids)}")

    # по продвижению
    promo = {}
    for o in mm_objs:
        lab = C.PAYMENT_STATUS.get(o.get("paymentStatus"), "?")
        promo[lab] = promo.get(lab, 0) + 1
    lines.append("Продвижение: " + ", ".join(f"{k}: {v}" for k, v in promo.items()))

    # топ агентов по числу объявлений
    by_agent = {}
    for o in mm_objs:
        key = (o.get("userUuid"), o.get("contactName"))
        by_agent[key] = by_agent.get(key, 0) + 1
    top = sorted(by_agent.items(), key=lambda x: -x[1])[:10]
    lines.append("Топ агентов:")
    for (uid, name), cnt in top:
        lines.append(f"  {cnt:4d}  {name}  ({uid})")

    # топ по просмотрам
    with_views = [(o, views_map.get(o.get("uuid"))) for o in mm_objs]
    with_views = [(o, v) for o, v in with_views if isinstance(v, int)]
    with_views.sort(key=lambda x: -x[1])
    lines.append("Топ-10 по просмотрам:")
    for o, v in with_views[:10]:
        lines.append(f"  {v:6d}  {o.get('contactName')}  {detect_quarter(o.get('title'))}  "
                     f"{o.get('price')} {o.get('priceCurrency')}  code={o.get('code')}")

    return "\n".join(lines)


# --------------------------- основной прогон -------------------------------

def run():
    ensure_dirs()
    seen = load_seen()
    snapshot_at = now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
    stamp = now_utc().strftime("%Y-%m-%d_%H-%M")

    session = requests.Session()
    session.headers.update({
        "content-type": "application/json",
        "user-agent": C.USER_AGENT,
        "accept": "application/json",
    })

    report_parts = []

    for agency_key, agency_uuid in C.AGENCIES.items():
        print(f"=== Агентство: {agency_key} ===")
        all_objs = fetch_agency_listings(session, agency_uuid)
        mm_objs = [o for o in all_objs if is_minsk_mir(o)]
        print(f"    Минск Мир: {len(mm_objs)} из {len(all_objs)}")

        uuids = [o["uuid"] for o in mm_objs if o.get("uuid")]
        print("    тяну текущие просмотры...")
        views_map = fetch_views(session, uuids)

        # новые объявления — восстановим историю просмотров один раз
        new_uuids = [u for u in uuids if u not in seen]
        if new_uuids:
            print(f"    новых объявлений: {len(new_uuids)}, восстанавливаю историю просмотров...")
        history_store = {}
        for u in new_uuids:
            history_store[u] = fetch_view_history(session, u)

        # пишем строки снимка
        rows = [obj_to_row(o, agency_key, snapshot_at, views_map) for o in mm_objs]
        append_snapshot_rows(rows)

        # обновляем реестр seen
        for o in mm_objs:
            u = o.get("uuid")
            if not u:
                continue
            if u not in seen:
                seen[u] = {
                    "first_seen": snapshot_at,
                    "last_seen": snapshot_at,
                    "agency": agency_key,
                    "code": o.get("code"),
                    "userUuid": o.get("userUuid"),
                    "history_views": history_store.get(u, {}),
                }
            else:
                seen[u]["last_seen"] = snapshot_at

        # сырой снимок (архив) — полный ответ + просмотры
        raw_path = os.path.join(C.RAW_DIR, f"{stamp}_{agency_key}.json")
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(
                {"snapshot_at": snapshot_at,
                 "minsk_mir_objects": mm_objs,
                 "views": views_map},
                f, ensure_ascii=False
            )

        report_parts.append(build_report(agency_key, mm_objs, views_map, new_uuids))
        sleep_between(C.PAUSE_BETWEEN_AGENCIES)

    save_seen(seen)

    report = "\n\n".join(report_parts)
    report_path = os.path.join(C.REPORTS_DIR, f"{stamp}.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print("\n" + report)
    print(f"\nГотово. Снимок: {snapshot_at}. Отчёт: {report_path}")


if __name__ == "__main__":
    run()
