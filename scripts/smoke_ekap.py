"""EKAP canli smoke test: imzanin kabul edildigini ve arama calistigini dogrular."""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main() -> None:
    from app.ekap.client import EkapClient
    from app.ekap.crypto import EkapSigner
    from app.http.rate_limiter import AsyncTokenBucket
    from app.http.session import create_http_client
    from app.utils.dates import tr_today
    from app.utils.logging import logger, setup_logging

    setup_logging()
    logger.info("EKAP smoke test: searching for today's tenders...")

    today = tr_today().strftime("%Y-%m-%d")
    logger.info("today (TR) = {t}", t=today)

    async with create_http_client() as http:
        signer = EkapSigner()
        bucket = AsyncTokenBucket(rate_per_minute=30)
        client = EkapClient(http, bucket, signer)

        tenders = await client.search_tenders(
            {
                "ilanTarihSaatBaslangic": today,
                "ilanTarihSaatBitis": today,
                "paginationTake": 5,
            }
        )
        logger.info("received {n} tenders", n=len(tenders))
        for i, t in enumerate(tenders[:3], start=1):
            logger.info(
                "  [{i}] id={id} ikn={ikn} ad={ad}",
                i=i,
                id=t.id,
                ikn=t.ikn,
                ad=(t.ihale_adi or "")[:60],
            )

        if not tenders:
            logger.info("no tenders today; trying a detail call on a known id...")
            return

        first = tenders[0]
        logger.info("fetching detail for id={id}...", id=first.id)
        detail = await client.get_tender_detail(first.id)
        logger.info(
            "detail: ad={ad} idare={i} durum={d}",
            ad=(detail.ihale_adi or "")[:60],
            i=(detail.idare_adi or "")[:60],
            d=detail.ihale_durum_aciklama,
        )

    logger.success("EKAP smoke test PASSED")


if __name__ == "__main__":
    asyncio.run(main())
