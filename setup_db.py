import sqlite3
import pandas as pd
from pathlib import Path
import logging
import sys
from typing import Optional
import config
from utils.file_parsers import parse_source_file
from database.migrations import MigrationManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def validate_data_integrity(conn: sqlite3.Connection) -> bool:
    """Validate data integrity and consistency"""
    logger.info("Validating data integrity...")
    
    issues = []
    
    try:
        # Check for null dates in predictions
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM predictions WHERE date IS NULL")
        null_dates = cursor.fetchone()[0]
        if null_dates > 0:
            issues.append(f"Found {null_dates} predictions with null dates")
        
        # Check for invalid confidence scores
        cursor.execute("SELECT COUNT(*) FROM predictions WHERE max_prob < 0 OR max_prob > 1")
        invalid_probs = cursor.fetchone()[0]
        if invalid_probs > 0:
            issues.append(f"Found {invalid_probs} predictions with invalid confidence scores")
        
        # Check for orphaned document changes
        cursor.execute("""
            SELECT COUNT(*) FROM document_changes dc 
            LEFT JOIN predictions p1 ON dc.date_from = p1.date 
            LEFT JOIN predictions p2 ON dc.date_to = p2.date 
            WHERE p1.date IS NULL OR p2.date IS NULL
        """)
        orphaned_changes = cursor.fetchone()[0]
        if orphaned_changes > 0:
            issues.append(f"Found {orphaned_changes} orphaned document changes")
        
        # Check for duplicate FOMC dates
        cursor.execute("SELECT date, COUNT(*) FROM fomc_dates GROUP BY date HAVING COUNT(*) > 1")
        duplicate_dates = cursor.fetchall()
        if duplicate_dates:
            issues.append(f"Found {len(duplicate_dates)} duplicate FOMC dates")
        
        if issues:
            logger.warning("Data integrity issues found:")
            for issue in issues:
                logger.warning(f"  - {issue}")
            return False
        else:
            logger.info("Data integrity validation passed")
            return True
            
    except Exception as e:
        logger.error(f"Error during data validation: {e}")
        return False

def optimize_database(conn: sqlite3.Connection) -> None:
    """Optimize database performance"""
    logger.info("Optimizing database performance...")
    
    try:
        cursor = conn.cursor()
        
        # Analyze tables for better query planning
        cursor.execute("ANALYZE")
        
        # Update table statistics
        cursor.execute("PRAGMA optimize")
        
        # Vacuum to reclaim space and defragment
        cursor.execute("VACUUM")
        
        logger.info("Database optimization completed")
        
    except Exception as e:
        logger.warning(f"Database optimization failed: {e}")

def create_enhanced_views(conn: sqlite3.Connection) -> None:
    """Create enhanced database views for common queries"""
    logger.info("Creating enhanced database views...")
    
    views = [
        # Meeting documents view with aggregated stats
        """
        CREATE VIEW IF NOT EXISTS meeting_summary AS
        SELECT 
            p.date,
            p.document_type,
            COUNT(*) as total_predictions,
            COUNT(CASE WHEN p.pred_label = 'hawkish' THEN 1 END) as hawkish_count,
            COUNT(CASE WHEN p.pred_label = 'neutral' THEN 1 END) as neutral_count,
            COUNT(CASE WHEN p.pred_label = 'dovish' THEN 1 END) as dovish_count,
            AVG(p.max_prob) as avg_confidence,
            MAX(p.max_prob) as max_confidence,
            MIN(p.max_prob) as min_confidence,
            CASE WHEN p.document_type = 'statement' THEN 1 ELSE 0 END AS is_statement,
            CASE WHEN p.document_type = 'press_conf' THEN 1 ELSE 0 END AS is_press_conf,
            CASE WHEN p.document_type = 'minutes' THEN 1 ELSE 0 END AS is_minutes
        FROM predictions p
        WHERE p.date IS NOT NULL
        GROUP BY p.date, p.document_type
        """,
        
        # High-level sentiment trends
        """
        CREATE VIEW IF NOT EXISTS sentiment_trends AS
        SELECT 
            date,
            AVG(CASE 
                WHEN pred_label = 'hawkish' THEN 1 
                WHEN pred_label = 'neutral' THEN 0 
                ELSE -1 
            END) as sentiment_score,
            COUNT(*) as total_statements,
            AVG(max_prob) as avg_confidence,
            strftime('%Y', date) as year,
            strftime('%Y-%m', date) as month
        FROM predictions
        WHERE date IS NOT NULL
        GROUP BY date
        """,
        
        # Document completeness view
        """
        CREATE VIEW IF NOT EXISTS document_completeness AS
        SELECT 
            fd.date,
            fd.has_statement,
            fd.has_press_conf,
            fd.has_minutes,
            CASE WHEN ms_st.date IS NOT NULL THEN 1 ELSE 0 END as has_statement_predictions,
            CASE WHEN ms_pc.date IS NOT NULL THEN 1 ELSE 0 END as has_press_conf_predictions,
            CASE WHEN ms_min.date IS NOT NULL THEN 1 ELSE 0 END as has_minutes_predictions,
            COALESCE(ms_st.total_predictions, 0) + 
            COALESCE(ms_pc.total_predictions, 0) + 
            COALESCE(ms_min.total_predictions, 0) as total_predictions
        FROM fomc_dates fd
        LEFT JOIN meeting_summary ms_st ON fd.date = ms_st.date AND ms_st.document_type = 'statement'
        LEFT JOIN meeting_summary ms_pc ON fd.date = ms_pc.date AND ms_pc.document_type = 'press_conf'
        LEFT JOIN meeting_summary ms_min ON fd.date = ms_min.date AND ms_min.document_type = 'minutes'
        """
    ]
    
    try:
        cursor = conn.cursor()
        for view_sql in views:
            # Drop existing view first
            view_name = view_sql.split("CREATE VIEW IF NOT EXISTS ")[1].split(" AS")[0].strip()
            cursor.execute(f"DROP VIEW IF EXISTS {view_name}")
            cursor.execute(view_sql)
        
        logger.info(f"Created {len(views)} database views")
        
    except Exception as e:
        logger.warning(f"Failed to create some views: {e}")

def init_database(validate: bool = True, optimize: bool = True) -> bool:
    """Initialize SQLite database with FOMC data and improvements"""
    logger.info("Initializing FOMC Analysis database...")
    
    try:
        # Run migrations first
        migration_manager = MigrationManager()
        if not migration_manager.run_migrations():
            logger.error("Database migrations failed")
            return False
        
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()
        
        # Create main tables with improved schema
        logger.info("Creating main tables...")
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT,
                pred_label TEXT NOT NULL,
                max_prob REAL NOT NULL CHECK (max_prob >= 0 AND max_prob <= 1),
                text TEXT NOT NULL,
                date TEXT,
                document_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fomc_dates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE NOT NULL,
                has_statement BOOLEAN DEFAULT FALSE,
                has_press_conf BOOLEAN DEFAULT FALSE,
                has_minutes BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS document_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_from TEXT NOT NULL,
                date_to TEXT NOT NULL,
                sentence_from TEXT,
                sentence_to TEXT,
                change_type TEXT,
                similarity_score REAL CHECK (similarity_score >= 0 AND similarity_score <= 1),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS compare_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date1 TEXT NOT NULL,
                date2 TEXT NOT NULL,
                doc_types TEXT,
                payload TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date1, date2, doc_types)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                series TEXT NOT NULL,
                value REAL NOT NULL,
                source TEXT DEFAULT 'manual',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date, series)
            )
        ''')
        
        # Create enhanced views
        create_enhanced_views(conn)
        
        # Load and validate data
        logger.info("Loading CSV data...")
        
        # Load predictions data
        if config.PREDICTIONS_FILE.exists():
            try:
                df = pd.read_csv(config.PREDICTIONS_FILE)
                logger.info(f"Loaded {len(df)} predictions from CSV")
                
                # Parse date and document type from source_file consistently
                parsed = df['source_file'].fillna('').apply(parse_source_file)
                df['date'] = parsed.apply(lambda t: t[0])
                df['document_type'] = parsed.apply(lambda t: t[1])
                
                # Avoid inserting explicit IDs to respect AUTOINCREMENT PK
                if 'id' in df.columns:
                    df = df.drop(columns=['id'])

                # Clean data
                df = df.dropna(subset=['pred_label', 'max_prob', 'text'])
                df = df[(df['max_prob'] >= 0) & (df['max_prob'] <= 1)]
                
                logger.info(f"Cleaned data: {len(df)} valid predictions remaining")
                
                # Load in batches for better performance
                batch_size = 10000
                for i in range(0, len(df), batch_size):
                    batch = df.iloc[i:i+batch_size]
                    batch.to_sql('predictions', conn, if_exists='append', index=False)
                    logger.info(f"Loaded batch {i//batch_size + 1}/{(len(df)-1)//batch_size + 1}")
                
            except Exception as e:
                logger.error(f"Failed to load predictions data: {e}")
                return False
        else:
            logger.warning(f"Predictions file not found: {config.PREDICTIONS_FILE}")
        
        # Load FOMC dates
        if config.FOMC_DATES_FILE.exists():
            try:
                dates_df = pd.read_csv(config.FOMC_DATES_FILE)
                logger.info(f"Loaded {len(dates_df)} FOMC dates from CSV")
                
                # Normalize dates and ensure expected columns
                dates_df['date'] = pd.to_datetime(dates_df['date'], errors='coerce').dt.strftime('%Y-%m-%d')
                dates_df = dates_df.dropna(subset=['date'])
                
                # Ensure boolean columns exist
                for col in ['has_statement', 'has_press_conf', 'has_minutes']:
                    if col not in dates_df.columns:
                        dates_df[col] = False
                    else:
                        dates_df[col] = dates_df[col].fillna(False).astype(bool)
                
                dates_df.to_sql('fomc_dates', conn, if_exists='replace', index=False)
                logger.info(f"Loaded {len(dates_df)} FOMC dates")
                
            except Exception as e:
                logger.error(f"Failed to load FOMC dates: {e}")
                return False
        else:
            logger.warning(f"FOMC dates file not found: {config.FOMC_DATES_FILE}")
        
        conn.commit()
        
        # Validate data integrity
        if validate:
            if not validate_data_integrity(conn):
                logger.warning("Data integrity issues detected")
        
        # Optimize database
        if optimize:
            optimize_database(conn)
        
        conn.close()
        logger.info("Database initialization completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False

def reset_database() -> bool:
    """Reset database by removing existing file and reinitializing"""
    logger.warning("Resetting database - all data will be lost!")
    
    try:
        if config.DATABASE_PATH.exists():
            config.DATABASE_PATH.unlink()
            logger.info("Removed existing database file")
        
        return init_database()
        
    except Exception as e:
        logger.error(f"Database reset failed: {e}")
        return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='FOMC Database Setup and Management')
    parser.add_argument('--reset', action='store_true', 
                       help='Reset database (removes all data)')
    parser.add_argument('--no-validate', action='store_true',
                       help='Skip data integrity validation')
    parser.add_argument('--no-optimize', action='store_true',
                       help='Skip database optimization')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       default='INFO', help='Set logging level')
    
    args = parser.parse_args()
    
    # Configure logging
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    try:
        if args.reset:
            success = reset_database()
        else:
            success = init_database(
                validate=not args.no_validate,
                optimize=not args.no_optimize
            )
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        logger.info("Database setup interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)