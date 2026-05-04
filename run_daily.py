"""
Daily pipeline orchestrator.
Steps: screener → signals → portfolio export → copy to web → data prep → KB index rebuild.
"""
import shutil, sys, time, logging
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import *

LOG_FILE = LOG_DIR / "daily.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(str(LOG_FILE), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('daily')

DATE_STR = datetime.now().strftime('%Y-%m-%d')


def step1_run_screener():
    """Run the stock screener."""
    logger.info("=" * 50)
    logger.info("Step 1/6: Running stock screener...")
    import stock_screener
    latest = SCREENER_DIR / "latest.json"
    if latest.exists():
        logger.info(f"  latest.json created: {latest.stat().st_size:,} bytes")
        return True
    else:
        logger.error("  latest.json not found after screener run!")
        return False


def step2_generate_signals():
    """Generate buy/sell/sector/position signals from today's data."""
    logger.info("Step 2/6: Generating signals...")
    try:
        from screener.signals import SignalEngine

        db_path = str(ROOT / "data" / "screener" / "screener.db")
        engine = SignalEngine(db_path)
        result = engine.run(DATE_STR)

        bs = len(result.get('buy_signals', []))
        ss = len(result.get('sell_signals', []))
        sc = len(result.get('sector_signals', []))
        ps = len(result.get('position_signals', []))
        logger.info(f"  Generated: {bs} buy, {ss} sell, {sc} sector, {ps} position signals")
        return True
    except Exception as e:
        logger.error(f"  Signal generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def step3_export_portfolio():
    """Export portfolio.json with live data and signals."""
    logger.info("Step 3/6: Exporting portfolio data...")
    try:
        from screener.portfolio import export_portfolio_json
        export_portfolio_json()
        logger.info("  portfolio.json exported")
        return True
    except Exception as e:
        logger.error(f"  Portfolio export failed: {e}")
        return False


def step4_copy_to_web():
    """Copy latest screener results to web directory."""
    logger.info("Step 4/6: Copying data to web directory...")
    src = SCREENER_DIR / "latest.json"
    dst = WEB_DIR / "latest.json"
    if not src.exists():
        logger.error(f"  Source not found: {src}")
        return False
    shutil.copy2(str(src), str(dst))
    logger.info(f"  {src} -> {dst}")
    return True


def step5_prepare_web_data():
    """Generate all web JSON files."""
    logger.info("Step 5/6: Preparing web data...")
    try:
        from web.data_prep import prepare_all
        prepare_all()
        logger.info("  Web data preparation complete")
        return True
    except Exception as e:
        logger.error(f"  Web data preparation failed: {e}")
        return False


def step6_rebuild_kb_index():
    """Rebuild knowledge base index."""
    logger.info("Step 6/6: Rebuilding knowledge base index...")
    try:
        from knowledge.builder import build
        build()
        logger.info("  KB index rebuilt")
        return True
    except Exception as e:
        logger.error(f"  KB index rebuild failed: {e}")
        return False


def main():
    start = time.time()
    logger.info(f"=== Daily pipeline start: {DATE_STR} ===")

    steps = [step1_run_screener, step2_generate_signals, step3_export_portfolio,
             step4_copy_to_web, step5_prepare_web_data, step6_rebuild_kb_index]
    results = []

    for step in steps:
        if not step():
            results.append(False)
            if step == step1_run_screener:
                logger.error("Pipeline aborted: screener failed")
                return
        else:
            results.append(True)

    elapsed = time.time() - start
    success = all(results)
    status = "SUCCESS" if success else "PARTIAL"
    logger.info(f"=== Pipeline {status}: {elapsed:.1f}s ===")


if __name__ == '__main__':
    main()
