"""Conservative filter for developer-offer ads in Minsk Mir.

A matching street or metro station is necessary for geographic relevance,
but not sufficient to distinguish primary-market offers from resales.
Unknown listings are excluded from the developer-only radar, not deleted.
"""
import re

POSITIVE = re.compile(
    r"застройщик|напрямую\s+от\s+застройщика|рассрочк|первичн(?:ое|ый|ая|ого)?\s+жиль"
    r"|новостройк|без\s+переплат|отдел\s+продаж|жилищн(?:ые|ый)\s+облигац",
    re.I,
)
NEGATIVE = re.compile(
    r"вторичк|вторичн(?:ый|ое|ая)\s+(?:рынок|жиль)|от\s+собственника"
    r"|с\s+(?:дизайнерским|авторским|капитальным)\s+ремонтом"
    r"|с\s+мебелью|полностью\s+укомплектованная|после\s+ремонта"
    r"|жил(?:и|ая|ое)\s+в\s+квартир|собственник\s+прода"
    r"|дизайнерск(?:ий|им|ого)\s+ремонт|с\s+(?:хорошим|современным|свежим|качественным)\s+ремонтом"
    r"|с\s+техникой\s+и\s+мебелью|ремонт\s+делал(?:и)?\s+для\s+себя",
    re.I,
)

def developer_offer(item):
    parts = [str(item.get(key) or "") for key in ("title", "headline", "description", "specialComment")]
    text = " ".join(parts)
    return bool(POSITIVE.search(text)) and not bool(NEGATIVE.search(text))

def classification(item):
    return "developer" if developer_offer(item) else "excluded_unverified"
