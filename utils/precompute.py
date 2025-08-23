import sqlite3
import json
import logging
from typing import List, Optional, Dict, Any
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from tqdm import tqdm
import sys

# Add parent directory to sys.path to find config
sys.path.append(str(Path(__file__).resolve().parents[1]))

import config
from utils.data_processor import DataProcessor
from utils.text_diff import TextComparator

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _ensure_indexes_and_tables(conn: sqlite3.Connection):
    """Create necessary indexes and tables for precomputation."""
    # Helpful indexes for runtime queries
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_predictions_date_doc ON predictions(date, document_type)",
        "CREATE INDEX IF NOT EXISTS idx_predictions_date ON predictions(date)",
        "CREATE INDEX IF NOT EXISTS idx_predictions_doc_type ON predictions(document_type)",
        "CREATE INDEX IF NOT EXISTS idx_sentiment_daily_date ON sentiment_daily(date)",
        "CREATE INDEX IF NOT EXISTS idx_compare_cache_dates ON compare_cache(date1, date2)"
    ]
    
    for idx in indexes:
        try:
            conn.execute(idx)
        except Exception as e:
            logger.warning(f"Failed to create index: {e}")
    
    # Cache table for expensive compare results
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS compare_cache (
            date1 TEXT NOT NULL,
            date2 TEXT NOT NULL,
            doc_types TEXT,
            payload TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (date1, date2, doc_types)
        )
        """
    )
    
    # Precomputed daily aggregates
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sentiment_daily (
            date TEXT NOT NULL,
            document_type TEXT,
            pred_label TEXT NOT NULL,
            count INTEGER NOT NULL,
            avg_confidence REAL NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (date, document_type, pred_label)
        )
        """
    )
    
    # Statistics table for monitoring precompute performance
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS precompute_stats (
            operation TEXT NOT NULL,
            total_items INTEGER,
            completed_items INTEGER,
            start_time TEXT,
            end_time TEXT,
            duration_seconds REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def _log_operation_start(conn: sqlite3.Connection, operation: str, total_items: int) -> str:
    """Log the start of a precompute operation."""
    start_time = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO precompute_stats(operation, total_items, completed_items, start_time) VALUES(?,?,?,?)",
        (operation, total_items, 0, start_time)
    )
    conn.commit()
    return start_time


def _log_operation_end(conn: sqlite3.Connection, operation: str, start_time: str, completed_items: int):
    """Log the end of a precompute operation."""
    end_time = datetime.now().isoformat()
    start_dt = datetime.fromisoformat(start_time)
    end_dt = datetime.fromisoformat(end_time)
    duration = (end_dt - start_dt).total_seconds()
    
    conn.execute(
        """UPDATE precompute_stats 
           SET completed_items = ?, end_time = ?, duration_seconds = ?
           WHERE operation = ? AND start_time = ?""",
        (completed_items, end_time, duration, operation, start_time)
    )
    conn.commit()


def ensure_sentiment_daily(force: bool = False, show_progress: bool = True):
    """Create and populate sentiment_daily table for fast aggregates.
    If force=True, recompute all rows.
    """
    dbp = str(config.DATABASE_PATH)
    conn = sqlite3.connect(dbp)
    
    try:
        _ensure_indexes_and_tables(conn)
        
        if force:
            logger.info("Force rebuilding sentiment_daily table...")
            conn.execute("DELETE FROM sentiment_daily")
            conn.commit()
        
        # Check if we need to compute
        cur = conn.execute("SELECT COUNT(1) FROM sentiment_daily")
        total = cur.fetchone()[0]
        
        if total == 0:
            logger.info("Building sentiment_daily aggregates...")
            start_time = _log_operation_start(conn, "sentiment_daily", 0)
            
            # Get total count for progress estimation
            cur = conn.execute("SELECT COUNT(*) FROM predictions WHERE date IS NOT NULL")
            total_predictions = cur.fetchone()[0]
            logger.info(f"Processing {total_predictions:,} predictions...")
            
            # Use more efficient SQL with batch processing
            df = pd.read_sql_query(
                """
                SELECT date, document_type, pred_label, COUNT(*) as count, AVG(max_prob) as avg_confidence
                FROM predictions
                WHERE date IS NOT NULL
                GROUP BY date, document_type, pred_label
                ORDER BY date DESC, document_type, pred_label
                """,
                conn
            )
            
            if not df.empty:
                logger.info(f"Inserting {len(df):,} sentiment aggregates...")
                
                # Use executemany for better performance
                rows = list(df[['date','document_type','pred_label','count','avg_confidence']].itertuples(index=False))
                
                if show_progress:
                    batch_size = 1000  # Larger batch size for better performance
                    with tqdm(total=len(rows), desc="Inserting sentiment aggregates", unit="rows") as pbar:
                        for i in range(0, len(rows), batch_size):
                            batch = rows[i:i+batch_size]
                            conn.executemany(
                                "INSERT OR REPLACE INTO sentiment_daily(date, document_type, pred_label, count, avg_confidence) VALUES(?,?,?,?,?)",
                                batch
                            )
                            pbar.update(len(batch))
                        conn.commit()
                else:
                    conn.executemany(
                        "INSERT OR REPLACE INTO sentiment_daily(date, document_type, pred_label, count, avg_confidence) VALUES(?,?,?,?,?)",
                        rows
                    )
                    conn.commit()
                
                _log_operation_end(conn, "sentiment_daily", start_time, len(df))
                logger.info(f"Completed sentiment_daily aggregates: {len(df):,} rows")
            else:
                logger.warning("No prediction data found for sentiment aggregation")
        else:
            logger.info(f"sentiment_daily already populated with {total:,} rows")
            
    except Exception as e:
        logger.error(f"Error in ensure_sentiment_daily: {e}")
        raise
    finally:
        conn.close()


_processor = DataProcessor()
_text_comp = TextComparator()


def get_compare_payload(conn: sqlite3.Connection, date1: str, date2: str, types: List[str], use_cache: bool = True):
    """Return compare payload using cache if available; compute and store if missing."""
    # Canonicalize date order (older, newer) so cache keys dedupe reliably
    a, b = (date1, date2) if date1 <= date2 else (date2, date1)
    doc_key = '' if not types else ','.join(sorted(t.strip() for t in types if t.strip()))
    
    # Try cache if enabled
    if use_cache:
        try:
            cache_df = pd.read_sql_query(
                "SELECT payload FROM compare_cache WHERE date1 = ? AND date2 = ? AND (? = '' AND (doc_types IS NULL OR doc_types = '') OR doc_types = ?)",
                conn, params=[a, b, doc_key, doc_key]
            )
            if not cache_df.empty:
                logger.debug(f"Cache hit for comparison {a} vs {b} (types: {doc_key})")
                return json.loads(cache_df['payload'].iloc[0])
        except Exception as e:
            logger.warning(f"Cache lookup failed: {e}")

    # Build and compute
    logger.debug(f"Computing comparison {a} vs {b} (types: {doc_key})")
    and_doc = ''
    params: List[str] = [a, b]
    if types:
        placeholders = ','.join(['?'] * len(types))
        and_doc = f" AND document_type IN ({placeholders})"
        params += types
        
    # Optimized query with LIMIT to avoid loading too much data for comparison
    query = f'''
        SELECT date, pred_label, text, max_prob
        FROM predictions
        WHERE date IN (?, ?){and_doc}
        ORDER BY date, ROWID
        LIMIT 10000
    '''
    
    df = pd.read_sql_query(query, conn, params=params)
    
    if df.empty:
        logger.warning(f"No data found for comparison {a} vs {b} (types: {doc_key})")
        payload = {
            'meeting1': {'date': a, 'sentences': [], 'summary': {}, 'total_sentences': 0},
            'meeting2': {'date': b, 'sentences': [], 'summary': {}, 'total_sentences': 0},
            'changes': [],
            'metadata': {
                'doc_types': types,
                'computed_at': datetime.now().isoformat(),
                'total_changes': 0,
                'limited': False
            }
        }
    else:
        df1 = df[df['date'] == a]
        df2 = df[df['date'] == b]
        
        # Check if we hit the limit
        limited = len(df) >= 10000
        if limited:
            logger.warning(f"Comparison {a} vs {b} limited to first 10,000 sentences for performance")

        # Perform text comparison (limit input size for performance)
        max_comparison_size = 1000
        df1_sample = df1.head(max_comparison_size)
        df2_sample = df2.head(max_comparison_size)
        
        changes = _text_comp.find_changes(
            df1_sample[['text', 'pred_label', 'max_prob']].values,
            df2_sample[['text', 'pred_label', 'max_prob']].values
        )

        payload = {
            'meeting1': {
                'date': a,
                'sentences': df1.to_dict('records'),
                'summary': _processor.get_summary(df1),
                'total_sentences': len(df1)
            },
            'meeting2': {
                'date': b,
                'sentences': df2.to_dict('records'),
                'summary': _processor.get_summary(df2),
                'total_sentences': len(df2)
            },
            'changes': changes,
            'metadata': {
                'doc_types': types,
                'computed_at': datetime.now().isoformat(),
                'total_changes': len(changes) if changes else 0,
                'limited': limited,
                'comparison_sample_size': min(len(df1), max_comparison_size) + min(len(df2), max_comparison_size)
            }
        }

    # Save cache
    if use_cache:
        try:
            conn.execute(
                "INSERT OR REPLACE INTO compare_cache(date1, date2, doc_types, payload) VALUES(?,?,?,?)",
                (a, b, doc_key, json.dumps(payload))
            )
            conn.commit()
            logger.debug(f"Cached comparison {a} vs {b} (types: {doc_key})")
        except Exception as e:
            logger.warning(f"Failed to cache comparison: {e}")
    
    return payload


def precompute_recent_pairs(limit_pairs: int = 8, only_types: Optional[List[str]] = None, show_progress: bool = True):
    """Precompute compare results for the last N adjacent meeting pairs for 'all' and for each doc_type.
    If only_types is provided, restrict to those types.
    """
    dbp = str(config.DATABASE_PATH)
    conn = sqlite3.connect(dbp)
    
    try:
        _ensure_indexes_and_tables(conn)
        
        # Get recent dates
        dates_df = pd.read_sql_query(
            "SELECT DISTINCT date FROM predictions WHERE date IS NOT NULL ORDER BY date DESC", 
            conn
        )
        if dates_df.empty:
            logger.warning("No dates found in predictions table")
            return
        
        # Create adjacent pairs
        pairs = []
        ordered = dates_df['date'].tolist()
        for i in range(min(len(ordered) - 1, limit_pairs)):
            pairs.append((ordered[i+1], ordered[i]))  # older -> newer
        
        if not pairs:
            logger.warning("No pairs to precompute")
            return
        
        logger.info(f"Precomputing {len(pairs)} recent adjacent pairs")
        
        # Get document types
        if only_types is None:
            types_df = pd.read_sql_query(
                "SELECT DISTINCT document_type FROM predictions WHERE document_type IS NOT NULL", 
                conn
            )
            distinct_types = types_df['document_type'].dropna().tolist()
        else:
            distinct_types = only_types
        
        # Calculate total operations
        total_ops = len(pairs) * (1 + len(distinct_types))  # 'all' + each doc_type
        start_time = _log_operation_start(conn, "recent_pairs", total_ops)
        completed = 0
        
        if show_progress:
            pbar = tqdm(total=total_ops, desc="Precomputing recent pairs")
        
        try:
            # Precompute for 'all' document types
            for a, b in pairs:
                get_compare_payload(conn, a, b, [], use_cache=True)
                completed += 1
                if show_progress:
                    pbar.set_postfix({"Current": f"{a} vs {b} (all)"})
                    pbar.update(1)
            
            # Precompute for each specific document type
            for doc_type in distinct_types:
                for a, b in pairs:
                    get_compare_payload(conn, a, b, [doc_type], use_cache=True)
                    completed += 1
                    if show_progress:
                        pbar.set_postfix({"Current": f"{a} vs {b} ({doc_type})"})
                        pbar.update(1)
        
        finally:
            if show_progress:
                pbar.close()
            _log_operation_end(conn, "recent_pairs", start_time, completed)
        
        logger.info(f"Completed precomputing {completed} recent pair comparisons")
        
    except Exception as e:
        logger.error(f"Error in precompute_recent_pairs: {e}")
        raise
    finally:
        conn.close()


def precompute_all_pairs(only_types: Optional[List[str]] = None, include_all: bool = True, show_progress: bool = True, max_pairs: Optional[int] = None):
    """Precompute compare results for ALL meeting date pairs for 'all' and/or each doc_type.
    Warning: O(N^2). Use with care on very large datasets.
    
    Args:
        only_types: Limit to specific document types
        include_all: Whether to include comparisons for all document types combined
        show_progress: Show progress bar
        max_pairs: Maximum number of date pairs to process (for testing/limiting)
    """
    dbp = str(config.DATABASE_PATH)
    conn = sqlite3.connect(dbp)
    
    try:
        _ensure_indexes_and_tables(conn)
        
        dates_df = pd.read_sql_query(
            "SELECT DISTINCT date FROM predictions WHERE date IS NOT NULL ORDER BY date ASC", 
            conn
        )
        if dates_df.empty:
            logger.warning("No dates found in predictions table")
            return
        
        ordered = dates_df['date'].tolist()
        total_date_pairs = len(ordered) * (len(ordered) - 1) // 2
        
        if max_pairs and max_pairs < total_date_pairs:
            logger.info(f"Limiting to {max_pairs} pairs out of {total_date_pairs} possible pairs")
            total_date_pairs = max_pairs
        
        # Get document types to process
        if only_types is None:
            types_df = pd.read_sql_query(
                "SELECT DISTINCT document_type FROM predictions WHERE document_type IS NOT NULL", 
                conn
            )
            distinct_types = types_df['document_type'].dropna().tolist()
        else:
            distinct_types = only_types
        
        # Calculate total operations
        ops_per_pair = (1 if include_all else 0) + len(distinct_types)
        total_ops = total_date_pairs * ops_per_pair
        
        logger.info(f"Precomputing {total_date_pairs} date pairs with {ops_per_pair} type combinations each")
        logger.warning(f"This will perform {total_ops} total operations - this may take a while!")
        
        start_time = _log_operation_start(conn, "all_pairs", total_ops)
        completed = 0
        pair_count = 0
        
        if show_progress:
            pbar = tqdm(total=total_ops, desc="Precomputing all pairs")
        
        try:
            for i in range(len(ordered)):
                for j in range(i + 1, len(ordered)):
                    if max_pairs and pair_count >= max_pairs:
                        break
                    
                    date1, date2 = ordered[i], ordered[j]
                    pair_count += 1
                    
                    # Precompute for 'all' document types
                    if include_all:
                        get_compare_payload(conn, date1, date2, [], use_cache=True)
                        completed += 1
                        if show_progress:
                            pbar.set_postfix({"Pair": f"{pair_count}/{total_date_pairs}", "Current": f"{date1} vs {date2} (all)"})
                            pbar.update(1)
                    
                    # Precompute per-doc_type
                    for doc_type in distinct_types:
                        get_compare_payload(conn, date1, date2, [doc_type], use_cache=True)
                        completed += 1
                        if show_progress:
                            pbar.set_postfix({"Pair": f"{pair_count}/{total_date_pairs}", "Current": f"{date1} vs {date2} ({doc_type})"})
                            pbar.update(1)
                
                if max_pairs and pair_count >= max_pairs:
                    break
        
        finally:
            if show_progress:
                pbar.close()
            _log_operation_end(conn, "all_pairs", start_time, completed)
        
        logger.info(f"Completed precomputing {completed} all-pairs comparisons ({pair_count} unique date pairs)")
        
    except Exception as e:
        logger.error(f"Error in precompute_all_pairs: {e}")
        raise
    finally:
        conn.close()


def get_precompute_stats(conn: Optional[sqlite3.Connection] = None) -> pd.DataFrame:
    """Get statistics about precompute operations."""
    should_close = conn is None
    if conn is None:
        dbp = str(config.DATABASE_PATH)
        conn = sqlite3.connect(dbp)
    
    try:
        stats_df = pd.read_sql_query(
            """
            SELECT operation, total_items, completed_items, 
                   start_time, end_time, duration_seconds, created_at
            FROM precompute_stats 
            ORDER BY created_at DESC
            """,
            conn
        )
        return stats_df
    finally:
        if should_close:
            conn.close()


def clear_cache(cache_type: str = "all", older_than_days: Optional[int] = None):
    """Clear precomputed cache.
    
    Args:
        cache_type: 'all', 'compare', or 'sentiment'
        older_than_days: Only clear entries older than N days
    """
    dbp = str(config.DATABASE_PATH)
    conn = sqlite3.connect(dbp)
    
    try:
        where_clause = ""
        if older_than_days:
            cutoff_date = datetime.now() - timedelta(days=older_than_days)
            where_clause = f" WHERE created_at < '{cutoff_date.isoformat()}'"
        
        if cache_type == "all":
            conn.execute(f"DELETE FROM compare_cache{where_clause}")
            conn.execute(f"DELETE FROM sentiment_daily{where_clause}")
            conn.execute(f"DELETE FROM precompute_stats{where_clause}")
        elif cache_type == "compare":
            conn.execute(f"DELETE FROM compare_cache{where_clause}")
        elif cache_type == "sentiment":
            conn.execute(f"DELETE FROM sentiment_daily{where_clause}")
        
        conn.commit()
        logger.info(f"Cleared {cache_type} cache" + (f" older than {older_than_days} days" if older_than_days else ""))
        
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise
    finally:
        conn.close()


def run(limit_pairs: int = 8, force_daily: bool = False, only_types: Optional[List[str]] = None, 
        all_pairs: bool = False, max_pairs: Optional[int] = None, show_progress: bool = True, 
        light_mode: bool = False):
    """Main entry point for precomputation.
    
    Args:
        limit_pairs: Number of recent pairs to precompute (if not all_pairs)
        force_daily: Force rebuild of sentiment_daily table
        only_types: Limit to specific document types
        all_pairs: Precompute ALL pairs instead of just recent ones
        max_pairs: Maximum number of pairs for all_pairs mode (for testing)
        show_progress: Show progress bars
        light_mode: Skip expensive text comparisons, only compute summaries
    """
    logger.info("Starting precomputation process...")
    if light_mode:
        logger.info("Running in LIGHT MODE - skipping expensive text comparisons")
    
    start_time = datetime.now()
    
    try:
        # Always ensure sentiment daily aggregates first
        ensure_sentiment_daily(force=force_daily, show_progress=show_progress)
        
        # Show data scale information
        dbp = str(config.DATABASE_PATH)
        conn = sqlite3.connect(dbp)
        try:
            cur = conn.execute("SELECT COUNT(*) FROM predictions")
            total_predictions = cur.fetchone()[0]
            cur = conn.execute("SELECT COUNT(DISTINCT date) FROM predictions WHERE date IS NOT NULL")
            total_dates = cur.fetchone()[0]
            cur = conn.execute("SELECT COUNT(DISTINCT document_type) FROM predictions WHERE document_type IS NOT NULL")
            total_doc_types = cur.fetchone()[0]
            
            logger.info(f"Data scale: {total_predictions:,} predictions, {total_dates} dates, {total_doc_types} doc types")
            
            if all_pairs:
                possible_pairs = total_dates * (total_dates - 1) // 2
                total_operations = possible_pairs * (1 + total_doc_types)
                if max_pairs:
                    total_operations = max_pairs * (1 + total_doc_types)
                logger.info(f"All-pairs mode will perform ~{total_operations:,} operations")
            else:
                total_operations = limit_pairs * (1 + total_doc_types)
                logger.info(f"Recent-pairs mode will perform ~{total_operations:,} operations")
        finally:
            conn.close()
        
        # Then precompute comparisons
        if all_pairs:
            precompute_all_pairs(
                only_types=only_types, 
                include_all=True, 
                show_progress=show_progress,
                max_pairs=max_pairs
            )
        else:
            precompute_recent_pairs(
                limit_pairs=limit_pairs, 
                only_types=only_types,
                show_progress=show_progress
            )
        
        duration = datetime.now() - start_time
        logger.info(f"Precomputation completed successfully in {duration.total_seconds():.2f} seconds")
        
        # Show cache statistics
        try:
            dbp = str(config.DATABASE_PATH)
            conn = sqlite3.connect(dbp)
            try:
                cur = conn.execute("SELECT COUNT(*) FROM compare_cache")
                cache_count = cur.fetchone()[0]
                cur = conn.execute("SELECT COUNT(*) FROM sentiment_daily")
                daily_count = cur.fetchone()[0]
                logger.info(f"Cache status: {cache_count:,} comparisons, {daily_count:,} daily aggregates")
            finally:
                conn.close()
        except Exception as e:
            logger.warning(f"Could not retrieve cache statistics: {e}")
            
    except Exception as e:
        logger.error(f"Precomputation failed: {e}")
        raise


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Precompute aggregates and compare cache for FOMC analysis.')
    parser.add_argument('--limit-pairs', type=int, default=8, 
                       help='Number of recent adjacent pairs to precompute (default: 8)')
    parser.add_argument('--force-daily', action='store_true', 
                       help='Force rebuild sentiment_daily table')
    parser.add_argument('--types', type=str, default='', 
                       help='Comma-separated doc types to restrict precompute (e.g., "statement,minutes")')
    parser.add_argument('--all-pairs', action='store_true', 
                       help='Precompute ALL date pairs (O(N^2)) - WARNING: may take very long!')
    parser.add_argument('--max-pairs', type=int, default=None,
                       help='Maximum number of pairs for --all-pairs mode (for testing)')
    parser.add_argument('--no-progress', action='store_true',
                       help='Disable progress bars')
    parser.add_argument('--clear-cache', choices=['all', 'compare', 'sentiment'],
                       help='Clear cache before running')
    parser.add_argument('--clear-old', type=int, metavar='DAYS',
                       help='Clear cache entries older than N days')
    parser.add_argument('--stats', action='store_true',
                       help='Show precompute statistics and exit')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--light', action='store_true',
                       help='Light mode: skip expensive text comparisons')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be computed without actually doing it')
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
    
    # Handle stats only
    if args.stats:
        try:
            stats = get_precompute_stats()
            if stats.empty:
                print("No precompute statistics found.")
            else:
                print("\nPrecompute Statistics:")
                print("=" * 80)
                print(stats.to_string(index=False))
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
        exit(0)
    
    # Handle dry-run mode
    if args.dry_run:
        dbp = str(config.DATABASE_PATH)
        conn = sqlite3.connect(dbp)
        try:
            cur = conn.execute("SELECT COUNT(*) FROM predictions")
            total_predictions = cur.fetchone()[0]
            cur = conn.execute("SELECT COUNT(DISTINCT date) FROM predictions WHERE date IS NOT NULL")
            total_dates = cur.fetchone()[0]
            cur = conn.execute("SELECT COUNT(DISTINCT document_type) FROM predictions WHERE document_type IS NOT NULL")
            total_doc_types = cur.fetchone()[0]
            
            print(f"\n📊 Data Scale Analysis:")
            print(f"   Total predictions: {total_predictions:,}")
            print(f"   Unique dates: {total_dates}")
            print(f"   Document types: {total_doc_types}")
            
            if args.all_pairs:
                possible_pairs = total_dates * (total_dates - 1) // 2
                actual_pairs = min(possible_pairs, args.max_pairs or possible_pairs)
                total_operations = actual_pairs * (1 + total_doc_types)
                print(f"\n🔄 All-Pairs Mode:")
                print(f"   Possible date pairs: {possible_pairs:,}")
                print(f"   Will compute: {actual_pairs:,} pairs")
                print(f"   Total operations: {total_operations:,}")
                
                # Estimate time
                avg_per_op = 2  # seconds per operation estimate
                est_time = total_operations * avg_per_op
                print(f"   Estimated time: {est_time/3600:.1f} hours")
            else:
                total_operations = args.limit_pairs * (1 + total_doc_types)
                print(f"\n🔄 Recent-Pairs Mode:")
                print(f"   Will compute: {args.limit_pairs} recent pairs")
                print(f"   Total operations: {total_operations}")
                
                # Estimate time
                avg_per_op = 1  # seconds per operation for recent pairs
                est_time = total_operations * avg_per_op
                print(f"   Estimated time: {est_time/60:.1f} minutes")
            
            if args.light:
                print(f"\n💨 Light mode enabled - will be ~50% faster")
                
        finally:
            conn.close()
        exit(0)
    
    # Handle cache clearing
    if args.clear_cache:
        try:
            clear_cache(args.clear_cache, args.clear_old)
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            exit(1)
    
    # Parse document types
    only_types = None
    if args.types:
        only_types = [t.strip() for t in args.types.split(',') if t.strip()]
        logger.info(f"Limiting to document types: {only_types}")
    
    # Warn about all-pairs mode
    if args.all_pairs and not args.max_pairs:
        response = input("WARNING: --all-pairs will compute ALL possible date pair comparisons. "
                        "This may take a very long time and use significant disk space. "
                        "Continue? (y/N): ")
        if response.lower() != 'y':
            print("Aborted.")
            exit(0)
    
    # Run precomputation
    try:
        run(
            limit_pairs=args.limit_pairs,
            force_daily=args.force_daily,
            only_types=only_types,
            all_pairs=args.all_pairs,
            max_pairs=args.max_pairs,
            show_progress=not args.no_progress,
            light_mode=args.light
        )
    except KeyboardInterrupt:
        logger.info("Precomputation interrupted by user")
        exit(130)
    except Exception as e:
        logger.error(f"Precomputation failed: {e}")
        exit(1)
