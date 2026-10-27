import unittest
from pipeline.developer_filter import developer_offer

class FilterTests(unittest.TestCase):
    def test_generic_installment_offer_not_proof(self):
        self.assertFalse(developer_offer({'title':'Квартира с ремонтом','description':'Рассрочка и любая форма оплаты'}))
    def test_developer_direct_offer(self):
        self.assertTrue(developer_offer({'title':'Квартира напрямую от застройщика','description':''}))
    def test_resale_with_agency_footer_excluded(self):
        self.assertFalse(developer_offer({'title':'Готовая квартира с дизайнерским ремонтом','description':'Большой выбор новостроек от застройщика'}))
    def test_unknown_excluded(self):
        self.assertFalse(developer_offer({'title':'Минск Мир, рядом с метро','description':'Хорошая локация'}))
if __name__=='__main__':unittest.main()
