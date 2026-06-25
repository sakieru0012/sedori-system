import sys
sys.path.insert(0, '.')
import config
from sedori_engine import SedoriEngine
from models import Product

engine = SedoriEngine()

# リサーチDBに登録済みの商品でテスト
p = Product(
    name='PS1 ストリートファイターZERO3',
    price=100, condition='中古', url='', image_url='',
    category='PS1', category_short='PS1',
    source='ヤフオク', current_price=100, shipping_fee=360
)
r = engine.process(p)
print(f'商品: {p.name}')
print(f'verdict: {r.verdict}')
print(f'recommended_max_bid: {r.recommended_max_bid}')
print(f'sell_price: {r.sell_price}')
print(f'basis: {r.basis}')
print(f'sales_summary: {r.sales_summary}')
print(f'research_item: {r.research_item}')
