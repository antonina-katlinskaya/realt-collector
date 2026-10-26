import datetime as dt
import json
from pathlib import Path


def choose(history,budget,now):
    valid=[r for r in history if r.get("status")=="ok"]
    if not valid:return 60,"Начальный часовой этап"
    first=dt.datetime.fromisoformat(valid[0]["started_at"])
    if now-first<dt.timedelta(hours=24) or len(valid)<15:
        return 60,"Нужно не менее 24 часов и 15 успешных сборов часового этапа"
    recent=history[-15:]
    if any(r.get("status")!="ok" or r.get("http_403") or r.get("http_429") for r in recent):
        return 60,"В последних запусках есть ошибки или блокировка источника"
    if any(float(r.get("duration_seconds",99999))>1200 for r in recent):
        return 60,"Длительность сбора превышает 20 минут"
    if not budget.get("safe"):return 60,budget.get("reason") or "Недостаточно запаса ресурсов архива"
    return 30,"Часовой этап пройден, расходы ниже безопасного порога"


def load_history():
    file=Path("data/health/collection_runs.json")
    return json.loads(file.read_text()) if file.exists() else []
