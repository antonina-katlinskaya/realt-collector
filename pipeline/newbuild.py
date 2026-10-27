"""Conservative classification of primary new-build offers in Minsk Mir.

This does not infer that an apartment is primary merely because of its address.
Unknown objects are not represented as verified new-build offers.
"""
import re

PRIMARY_PHRASES = (
    'напрямую от застройщика', 'прямо от застройщика',
    'от застройщика', 'продажа от застройщика',
    'первичная недвижимость', 'прямая продажа застройщика',
)
SECONDARY_PHRASES = (
    'вторичный рынок', 'вторичка', 'собственник продает',
    'дизайнерский ремонт', 'квартира с ремонтом',
    'полностью меблирована', 'вся мебель остается',
)
DEVELOPMENT_TERMS = (
    'минск-мир', 'минск мир', 'новострой', 'жилой комплекс',
    'дом лира', 'дом вега', 'дом орион', 'дом сириус',
    'дом медитерранеан', 'дом эверест', 'дом софия',
    'дом калемегдан', 'дом континенталь',
    'дом андромеда', 'дом карибиан',
)

def is_primary_newbuild(obj):
    title=str(obj.get('title') or '').lower().replace('ё','е')
    description=str(obj.get('description') or '').lower().replace('ё','е')
    content=(title+' '+description)[:10000]
    if any(word in content for word in SECONDARY_PHRASES):
        return False
    if obj.get('realEstateDevUuid'):
        return True
    if any(word in content for word in PRIMARY_PHRASES):
        return True
    try:
        year=int(obj.get('buildingYear') or 0)
    except (TypeError, ValueError):
        year=0
    return year>=2026 and any(word in content for word in DEVELOPMENT_TERMS)
