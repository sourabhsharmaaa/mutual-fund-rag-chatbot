from __future__ import annotations

import asyncio
import json
import logging
import sys
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add the project root to sys.path so we can import internal modules
ROOT = Path(__file__).parent.absolute()
sys.path.append(str(ROOT))

from scrapers.runner import ScraperRunner # type: ignore
from embedder.pipeline import EmbeddingPipeline # type: ignore

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(ROOT / "logs" / "scheduler.log")
    ]
)
logger = logging.getLogger("scheduler")

IST = timezone(timedelta(hours=5, minutes=30))

# ---------------------------------------------------------------------------
# Scheduler Logic
# ---------------------------------------------------------------------------

async def run_update_pipeline():
    """
    Sequentially runs:
    1. Phase 1: Scraper (Data Ingestion)
    2. Phase 2: Indexer (Vector Embeddings)
    3. Phase 3: Link Validation (Source Health)
    4. Updates metadata with the completion timestamp.
    """
    logger.info("Starting Automated Update Pipeline...")
    
    try:
        # Step 1: Phase 1 — Scraper
        logger.info(">>> RUNNING PHASE 1: Scraper Ingestion...")
        scraper = ScraperRunner()
        await scraper.run_all()
        logger.info("Phase 1 Complete.")
        
        # Step 2: Phase 2 — Embeddings
        logger.info(">>> RUNNING PHASE 2: ChromaDB Indexing...")
        # We run with reset=True to ensure a clean, up-to-date index
        pipeline = EmbeddingPipeline(use_seed=False, reset=True)
        pipeline.run()
        logger.info("Phase 2 Complete.")

        # Step 3: Phase 3 — Link Validation
        logger.info(">>> RUNNING PHASE 3: Link Health Validation...")
        try:
            from scripts.link_validator import main as run_validator # type: ignore
            # validator exit(1) if broken, but we don't want to stop the whole pipeline
            # we just want to log it
            run_validator()
            logger.info("Phase 3 Complete (All links OK).")
        except SystemExit as e:
            if e.code == 0:
                logger.info("Phase 3 Complete (All links OK).")
            else:
                logger.warning("Phase 3 Complete (Some broken links detected! Check logs.)")
        except Exception as e:
            logger.error(f"Validator failed to run: {e}")
        
        # Step 3: Update metadata
        timestamp = datetime.now(IST).strftime("%d %b %Y, %I:%M %p")
        metadata_path = ROOT / "data" / "metadata.json"
        
        metadata = {
            "last_updated": timestamp,
            "status": "success",
            "version": "1.0.0"
        }
        
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        
        logger.info(f"Successfully updated metadata: {timestamp}")
        print(f"\n✅ UPDATE SUCCESSFUL. Data last updated: {timestamp}")
        
    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}", exc_info=True)
        print(f"\n❌ UPDATE FAILED: {str(e)}")
        sys.exit(1)

# ---------------------------------------------------------------------------
# Manual Testing Instructions
# ---------------------------------------------------------------------------
"""
HOW TO TEST MANUALLY:
1. Open a terminal in the project root.
2. Run the scheduler script:
   python scheduler.py
3. Verify the output:
   - Check 'logs/scheduler.log' for details.
   - Verify 'data/metadata.json' contains the new timestamp.
   - Verify ChromaDB was updated (logs will show 'Upserting X chunks').
4. Backend Check:
   - Call the status endpoint (once implemented):
     curl http://localhost:8000/api/status
"""

from apscheduler.schedulers.blocking import BlockingScheduler # type: ignore

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PPFAS RAG Scheduler")
    parser.add_argument("--once", action="store_true", help="Run the pipeline once and exit (for cron/CI)")
    args = parser.parse_args()

    if args.once:
        print("Running pipeline once (--once flag provided)...")
        asyncio.run(run_update_pipeline())
        sys.exit(0)

    scheduler = BlockingScheduler(timezone="Asia/Kolkata")

    # Run immediately on startup so data is fresh right away
    asyncio.run(run_update_pipeline())

    # Then schedule to run every day at 10:00 AM IST
    scheduler.add_job(
        lambda: asyncio.run(run_update_pipeline()),
        trigger="cron",
        hour=10,
        minute=0,
    )

    print("Scheduler started. Pipeline will run daily at 10:00 AM IST.")
    print("Press Ctrl+C to stop.")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler stopped.")
