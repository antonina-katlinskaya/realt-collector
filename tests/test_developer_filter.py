import unittest
from pipeline.developer_filter import developer_offer

class DeveloperOfferTest(unittest.TestCase):
    def test_dev_new_apartment(self):
        self.assertTrue(developer_offer({'title':'Напрямую от застройщика. Дом Континенталь. Рассрочка без переплат.'}))
    def test_ready_new_developer(self):
        self.assertTrue(developer_offer({'title':'Дом сдан','description':'Квартира в Minsk World напрямую от застройщика, скидка за быструю оплату.'}))
    def test_resale_with_boilerplate(self):
        self.assertFalse(developer_offer({'title':'Видовая квартира с панорамным видом','description':'Квартира с мебелью и современным ремонтом. '+('Описание квартиры. '*80)+'Агентство предлагает новостройки и рассрочку.'}))
    def test_resale_with_footer_misclassified_before(self):
        self.assertFalse(developer_offer({'title':'Продажа евротрешки в Минск-Мир','description':'Квартира полностью готова к проживанию. Современный ремонт, бытовая техника и мебель. Рассрочка от агентства.'}))
    def test_no_proof(self):
        self.assertFalse(developer_offer({'title':'Пространство для вашей будущей истории','description':'Просторная квартира в готовом районе, рядом метро.'}))
if __name__=='__main__':unittest.main()
