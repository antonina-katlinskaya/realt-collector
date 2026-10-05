# -*- coding: utf-8 -*-
"""
Тексты GraphQL-запросов. Взяты в том виде, в каком их шлёт сам сайт Realt.
Менять поля в SEARCH_OBJECTS_QUERY без необходимости не нужно —
здесь перечислены все ~90 полей, которые отдаёт список.
"""

# Запрос 1: список объявлений агентства (с фильтрами и постраничностью)
SEARCH_OBJECTS_QUERY = """
query searchObjects($data: GetObjectsByAddressInput!) {
  searchObjects(data: $data) {
    body {
      results {
        companyName
        companyUuid
        uuid
        title
        description
        headline
        createdAt
        updatedAt
        metroTime
        metroTimeType
        price
        priceCurrency
        pricePerM2
        pricePerM2Max
        pricePerPerson
        priceMin
        priceMax
        priceChangeDirection
        priceChangeDate
        storeys
        storey
        rooms
        contactPhones
        images
        areaTotal
        areaLiving
        areaMax
        areaMin
        areaLand
        objectType
        code
        stateRegionName
        stateDistrictName
        townType
        townName
        streetUuid
        streetName
        address
        contactName
        contactEmail
        agencyName
        metroStationName
        metroLineId
        houseNumber
        buildingNumber
        paymentStatus
        comments
        isFavorite
        category
        has3dTour
        hasVideo
        stateRegionUuid
        numberOfBeds
        directionName
        townDistance
        customSorting
        specialComment
        userUuid
        agencyUuid
        location
        townUuid
        buildingYear
        levels
        roofMaterial
        wallMaterial
        heating
        infrastructure
        balconyType
        houseType
        furniture
        areaKitchen
        appliances
        objectCategory
        realEstateDevUuid
        availableYear
        availableQuarter
        availableAlready
        availableText
        isSellingCompleted
        communicationMethod
        interactiveCatalogToken
        interactiveCatalogBaseToken
        isObjectInRealtyDeal
        repairState
        __typename
      }
      pagination {
        page
        pageSize
        totalCount
        __typename
      }
      rates {
        from
        to
        rate
        __typename
      }
      extraFields {
        minPriceAggregation
        __typename
      }
      __typename
    }
    ...StatusAndErrors
    __typename
  }
}

fragment StatusAndErrors on INullResponse {
  success
  errors {
    code
    title
    message
    field
    __typename
  }
  __typename
}
""".strip()

# Запрос 2: текущие просмотры по списку uuid
VIEWS_QUERY = (
    "query v($uuids:[UUID!]!){objectsViewsCountsByUuids(uuids:$uuids){views}}"
)

# Запрос 3: просмотры на конкретную дату (для восстановления истории
# у новых объявлений). views на дату = накопленные просмотры за период
# от referenceDate до сегодня.
VIEWS_BY_DATE_QUERY = (
    "query d($data:ObjectsDetailViewsCountByUuidAndDateInput!)"
    "{objectsDetailViewsCountByUuidAndDate(data:$data){views}}"
)
