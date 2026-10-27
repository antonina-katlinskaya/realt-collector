"""Conservative filter for developer-offer ads in Minsk Mir.

A matching street or metro station is necessary for geographic relevance,
but not sufficient to distinguish primary-market offers from resales.
Unknown listings are excluded from the developer-only radar, not deleted.
"""
import re

POSITIVE = re.compile(
    r"застройщик|первичн(?:ое|ый|ая|ого)?\s+жиль"
    r"|новостройк|отдел\s+продаж|жилищн(?:ые|ый)\s+облигац"
    r"|продаж.{0,40}от\s+застройщика",
    re.I | re.S,
)
NEGATIVE = re.compile(
    r"вторичк|вторичн(?:ый|ое|ая)\s+(?:рынок|жиль)|от\s+собственника"
    r"|с\s+(?:дизайнерским|авторским|капитальным|хорошим|современным|качественным)\s+ремонтом"
    r"|современн(?:ый|ым)\s+ремонт|дизайнерск(?:ий|им|ого)\s+ремонт"
    r"|с\s+мебелью|с\s+техникой|мебель\s+остае|оснащен.{0,40}мебел"
    r"|после\s+ремонта|полностью\s+готова\s+к\s+проживани"
    r"|чистая\s+продажа|отделк.{0,40}сантехник|жил(?:и|ая|ое)\s+в\s+квартир",
    re.I | re.S,
)

def developer_offer(item):
    # Agency's generic sales footer often advertises new builds even in resale listings.
    # Only use the headline and the opening object-specific portion of the description.
    title = " ".join(str(item.get(k) or "") for k in ("title", "headline"))
    description = str(item.get("description") or "")[:850]
    object_text = title + " " + description
    return bool(POSITIVE.search(object_text)) and not bool(NEGATIVE.search(object_text))

def classification(item):
    return "developer" if developer_offer(item) else "excluded_unverified"
