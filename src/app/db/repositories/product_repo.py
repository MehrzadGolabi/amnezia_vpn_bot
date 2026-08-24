import uuid
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.models.product import Product


class ProductRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, product_id: uuid.UUID) -> Optional[Product]:
        return await self.session.get(Product, product_id)

    async def get_by_code(self, code: str) -> Optional[Product]:
        stmt = select(Product).where(Product.code == code)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_enabled(self) -> List[Product]:
        stmt = select(Product).where(Product.enabled.is_(True)).order_by(Product.sort_order, Product.duration_days)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def create_or_update(
        self,
        code: str,
        title: str,
        duration_days: int,
        price_amount: Decimal,
        price_currency: str = "EUR",
        device_limit: int = 1,
        enabled: bool = True,
        sort_order: int = 0,
    ) -> Product:
        product = await self.get_by_code(code)
        if product is None:
            product = Product(
                code=code,
                title=title,
                duration_days=duration_days,
                device_limit=device_limit,
                price_amount=price_amount,
                price_currency=price_currency,
                enabled=enabled,
                sort_order=sort_order,
            )
            self.session.add(product)
        else:
            product.title = title
            product.duration_days = duration_days
            product.device_limit = device_limit
            product.price_amount = price_amount
            product.price_currency = price_currency
            product.enabled = enabled
            product.sort_order = sort_order
        await self.session.flush()
        return product
