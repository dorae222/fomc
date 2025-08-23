from datetime import datetime, timedelta
import sqlite3
from contextlib import contextmanager
import pandas as pd
import logging
import threading
import time
from typing import Optional, List, Dict, Any, Union
import config

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Enhanced database connection and query manager with connection pooling and better error handling"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, db_path=None):
        """Singleton pattern for database manager"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, db_path=None):
        if hasattr(self, '_initialized'):
            return
        self.db_path = db_path or config.DATABASE_PATH
        self._initialized = True
        self._setup_pragmas()
    
    def _setup_pragmas(self):
        """Setup SQLite pragmas for better performance and reliability"""
        with self.get_connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging for better concurrency
            conn.execute("PRAGMA synchronous=NORMAL")  # Balance between safety and performance
            conn.execute("PRAGMA cache_size=10000")  # Increase cache size
            conn.execute("PRAGMA temp_store=MEMORY")  # Store temp tables in memory
            conn.execute("PRAGMA foreign_keys=ON")  # Enable foreign key constraints
    
    @contextmanager
    def get_connection(self, timeout: float = 30.0):
        """Context manager for database connections with timeout"""
        conn = None
        try:
            conn = sqlite3.connect(
                self.db_path, 
                timeout=timeout,
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            yield conn
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    @contextmanager
    def transaction(self, timeout: float = 30.0):
        """Context manager for database transactions"""
        with self.get_connection(timeout=timeout) as conn:
            try:
                conn.execute("BEGIN")
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Transaction rolled back due to error: {e}")
                raise
    
    def execute_query(self, query: str, params: Optional[List] = None, timeout: float = 30.0):
        """Execute a query and return results with better error handling"""
        try:
            with self.get_connection(timeout=timeout) as conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Query execution failed: {query[:100]}... Error: {e}")
            raise
    
    def execute_many(self, query: str, data: List, batch_size: int = 1000, timeout: float = 60.0):
        """Execute many queries with batching for better performance"""
        if not data:
            return
        
        try:
            with self.transaction(timeout=timeout) as conn:
                cursor = conn.cursor()
                for i in range(0, len(data), batch_size):
                    batch = data[i:i + batch_size]
                    cursor.executemany(query, batch)
                    if len(data) > batch_size:
                        logger.debug(f"Processed batch {i//batch_size + 1}/{(len(data)-1)//batch_size + 1}")
        except sqlite3.Error as e:
            logger.error(f"Batch execution failed: {query[:100]}... Error: {e}")
            raise
    
    def get_dataframe(self, query: str, params: Optional[List] = None, timeout: float = 30.0) -> pd.DataFrame:
        """Get query results as pandas DataFrame with error handling"""
        try:
            with self.get_connection(timeout=timeout) as conn:
                return pd.read_sql_query(query, conn, params=params)
        except sqlite3.Error as e:
            logger.error(f"DataFrame query failed: {query[:100]}... Error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in get_dataframe: {e}")
            return pd.DataFrame()
    
    def upsert(self, table: str, data: Dict[str, Any], unique_columns: List[str], timeout: float = 30.0):
        """Upsert operation for SQLite"""
        columns = list(data.keys())
        placeholders = ','.join(['?' for _ in columns])
        set_clause = ','.join([f"{col}=excluded.{col}" for col in columns if col not in unique_columns])
        
        query = f"""
            INSERT INTO {table} ({','.join(columns)})
            VALUES ({placeholders})
            ON CONFLICT({','.join(unique_columns)}) DO UPDATE SET {set_clause}
        """
        
        try:
            with self.get_connection(timeout=timeout) as conn:
                cursor = conn.cursor()
                cursor.execute(query, list(data.values()))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Upsert failed for table {table}: {e}")
            raise
    
    def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """Get table schema information"""
        query = f"PRAGMA table_info({table_name})"
        try:
            result = self.execute_query(query)
            return {
                'columns': [dict(row) for row in result],
                'row_count': self.execute_query(f"SELECT COUNT(*) FROM {table_name}")[0][0]
            }
        except sqlite3.Error as e:
            logger.error(f"Failed to get table info for {table_name}: {e}")
            return {'columns': [], 'row_count': 0}


class PredictionModel:
    """Enhanced model for FOMC predictions with caching and advanced analytics"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self._cache = {}
        self._cache_timeout = 300  # 5 minutes
        self._ensure_indexes()
    
    def _ensure_indexes(self):
        """Ensure required indexes exist for optimal performance"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_predictions_date ON predictions(date)",
            "CREATE INDEX IF NOT EXISTS idx_predictions_date_doc ON predictions(date, document_type)",
            "CREATE INDEX IF NOT EXISTS idx_predictions_label ON predictions(pred_label)",
            "CREATE INDEX IF NOT EXISTS idx_predictions_prob ON predictions(max_prob)",
            "CREATE INDEX IF NOT EXISTS idx_predictions_created ON predictions(created_at)"
        ]
        
        try:
            with self.db.get_connection() as conn:
                for index_query in indexes:
                    conn.execute(index_query)
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to create some indexes: {e}")
    
    def _get_cache_key(self, method_name: str, *args) -> str:
        """Generate cache key for method and arguments"""
        return f"{method_name}:{hash(str(args))}"
    
    def _get_cached_or_compute(self, method_name: str, compute_func, *args):
        """Get result from cache or compute and cache it"""
        cache_key = self._get_cache_key(method_name, *args)
        
        # Check cache
        if cache_key in self._cache:
            timestamp, result = self._cache[cache_key]
            if time.time() - timestamp < self._cache_timeout:
                return result
        
        # Compute and cache
        result = compute_func(*args)
        self._cache[cache_key] = (time.time(), result)
        return result
    
    def get_by_date(self, date: str) -> pd.DataFrame:
        """Get all predictions for a specific date"""
        query = """
            SELECT * FROM predictions 
            WHERE date = ? 
            ORDER BY id
        """
        return self.db.get_dataframe(query, [date])
    
    def get_date_range(self, start_date: str, end_date: str, document_types: Optional[List[str]] = None) -> pd.DataFrame:
        """Get predictions within date range with optional document type filtering"""
        base_query = """
            SELECT * FROM predictions 
            WHERE date BETWEEN ? AND ?
        """
        params = [start_date, end_date]
        
        if document_types:
            placeholders = ','.join(['?' for _ in document_types])
            base_query += f" AND document_type IN ({placeholders})"
            params.extend(document_types)
        
        base_query += " ORDER BY date, id"
        return self.db.get_dataframe(base_query, params)
    
    def get_sentiment_summary(self, date: Optional[str] = None, document_type: Optional[str] = None) -> pd.DataFrame:
        """Get sentiment summary statistics with optional filtering"""
        def _compute_summary(date, document_type):
            base_query = """
                SELECT 
                    pred_label,
                    COUNT(*) as count,
                    AVG(max_prob) as avg_confidence,
                    MIN(max_prob) as min_confidence,
                    MAX(max_prob) as max_confidence,
                    STDDEV(max_prob) as std_confidence
                FROM predictions
                WHERE 1=1
            """
            params = []
            
            if date:
                base_query += " AND date = ?"
                params.append(date)
            
            if document_type:
                base_query += " AND document_type = ?"
                params.append(document_type)
            
            base_query += " GROUP BY pred_label ORDER BY count DESC"
            return self.db.get_dataframe(base_query, params)
        
        return self._get_cached_or_compute("sentiment_summary", _compute_summary, date, document_type)
    
    def get_confidence_distribution(self, bins: int = 10) -> pd.DataFrame:
        """Get confidence score distribution"""
        query = f"""
            SELECT 
                CAST((max_prob * {bins}) AS INTEGER) * (1.0/{bins}) as confidence_bin,
                COUNT(*) as count,
                pred_label
            FROM predictions
            WHERE max_prob IS NOT NULL
            GROUP BY confidence_bin, pred_label
            ORDER BY confidence_bin, pred_label
        """
        return self.db.get_dataframe(query)
    
    def get_high_confidence_statements(self, threshold: float = 0.8, limit: int = 100, 
                                     sentiment: Optional[str] = None) -> pd.DataFrame:
        """Get high confidence statements with optional sentiment filtering"""
        base_query = """
            SELECT * FROM predictions
            WHERE max_prob > ?
        """
        params = [threshold]
        
        if sentiment:
            base_query += " AND pred_label = ?"
            params.append(sentiment)
        
        base_query += " ORDER BY max_prob DESC LIMIT ?"
        params.append(limit)
        
        return self.db.get_dataframe(base_query, params)
    
    def get_sentiment_timeline(self, granularity: str = 'monthly') -> pd.DataFrame:
        """Get sentiment distribution over time with configurable granularity"""
        def _compute_timeline(granularity):
            if granularity == 'monthly':
                date_format = '%Y-%m'
            elif granularity == 'quarterly':
                date_format = '%Y-Q' 
                # SQLite doesn't have quarter function, so we'll handle this in pandas
            else:  # daily
                date_format = '%Y-%m-%d'
            
            query = f"""
                SELECT 
                    strftime('{date_format}', date) as period,
                    pred_label,
                    COUNT(*) as count,
                    AVG(max_prob) as avg_confidence
                FROM predictions
                WHERE date IS NOT NULL
                GROUP BY period, pred_label
                ORDER BY period
            """
            
            df = self.db.get_dataframe(query)
            
            if df.empty:
                return pd.DataFrame()
            
            # Handle quarterly granularity
            if granularity == 'quarterly':
                df['period'] = df['period'].apply(lambda x: f"{x[:4]}-Q{((int(x[5:7])-1)//3)+1}")
            
            # Pivot for easier use
            pivot = df.pivot_table(
                index='period',
                columns='pred_label',
                values=['count', 'avg_confidence'],
                fill_value=0
            )
            
            # Calculate percentages for count
            count_pivot = pivot['count']
            pct_pivot = count_pivot.div(count_pivot.sum(axis=1), axis=0) * 100
            
            # Combine with confidence data
            result = pd.concat([count_pivot, pct_pivot, pivot['avg_confidence']], 
                             keys=['count', 'percentage', 'avg_confidence'], axis=1)
            
            return result
        
        return self._get_cached_or_compute("sentiment_timeline", _compute_timeline, granularity)
    
    def get_document_type_comparison(self) -> pd.DataFrame:
        """Compare sentiment distribution across document types"""
        query = """
            SELECT 
                document_type,
                pred_label,
                COUNT(*) as count,
                AVG(max_prob) as avg_confidence,
                COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY document_type) as percentage
            FROM predictions
            WHERE document_type IS NOT NULL
            GROUP BY document_type, pred_label
            ORDER BY document_type, pred_label
        """
        return self.db.get_dataframe(query)
    
    def get_volatility_analysis(self, window_days: int = 30) -> pd.DataFrame:
        """Analyze sentiment volatility over time"""
        query = f"""
            WITH daily_sentiment AS (
                SELECT 
                    date,
                    AVG(CASE WHEN pred_label = 'hawkish' THEN 1 
                             WHEN pred_label = 'neutral' THEN 0 
                             ELSE -1 END) as sentiment_score,
                    AVG(max_prob) as avg_confidence
                FROM predictions
                WHERE date IS NOT NULL
                GROUP BY date
            ),
            windowed_stats AS (
                SELECT 
                    date,
                    sentiment_score,
                    avg_confidence,
                    AVG(sentiment_score) OVER (
                        ORDER BY date 
                        ROWS BETWEEN {window_days-1} PRECEDING AND CURRENT ROW
                    ) as rolling_sentiment,
                    AVG(avg_confidence) OVER (
                        ORDER BY date 
                        ROWS BETWEEN {window_days-1} PRECEDING AND CURRENT ROW
                    ) as rolling_confidence
                FROM daily_sentiment
            )
            SELECT 
                date,
                sentiment_score,
                avg_confidence,
                rolling_sentiment,
                rolling_confidence,
                ABS(sentiment_score - rolling_sentiment) as volatility
            FROM windowed_stats
            ORDER BY date
        """
        return self.db.get_dataframe(query)
    
    def get_prediction_stats(self) -> Dict[str, Any]:
        """Get comprehensive prediction statistics"""
        try:
            with self.db.get_connection() as conn:
                stats = {}
                
                # Basic counts
                stats['total_predictions'] = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
                stats['unique_dates'] = conn.execute("SELECT COUNT(DISTINCT date) FROM predictions WHERE date IS NOT NULL").fetchone()[0]
                stats['date_range'] = conn.execute("SELECT MIN(date), MAX(date) FROM predictions WHERE date IS NOT NULL").fetchone()
                
                # Document type distribution
                doc_types = conn.execute("""
                    SELECT document_type, COUNT(*) as count 
                    FROM predictions 
                    WHERE document_type IS NOT NULL
                    GROUP BY document_type
                """).fetchall()
                stats['document_types'] = {row[0]: row[1] for row in doc_types}
                
                # Confidence statistics
                conf_stats = conn.execute("""
                    SELECT 
                        AVG(max_prob) as avg_confidence,
                        MIN(max_prob) as min_confidence,
                        MAX(max_prob) as max_confidence,
                        COUNT(CASE WHEN max_prob > 0.8 THEN 1 END) as high_confidence_count
                    FROM predictions
                """).fetchone()
                
                stats['confidence'] = {
                    'average': conf_stats[0],
                    'minimum': conf_stats[1],
                    'maximum': conf_stats[2],
                    'high_confidence_count': conf_stats[3]
                }
                
                return stats
                
        except Exception as e:
            logger.error(f"Failed to get prediction stats: {e}")
            return {}
    
    def clear_cache(self):
        """Clear the internal cache"""
        self._cache.clear()


class DocumentChangeModel:
    """Enhanced model for tracking document changes between meetings with advanced analytics"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self._ensure_indexes()
    
    def _ensure_indexes(self):
        """Ensure required indexes exist for optimal performance"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_doc_changes_dates ON document_changes(date_from, date_to)",
            "CREATE INDEX IF NOT EXISTS idx_doc_changes_type ON document_changes(change_type)",
            "CREATE INDEX IF NOT EXISTS idx_doc_changes_similarity ON document_changes(similarity_score)"
        ]
        
        try:
            with self.db.get_connection() as conn:
                for index_query in indexes:
                    conn.execute(index_query)
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to create document changes indexes: {e}")
    
    def save_changes(self, date_from: str, date_to: str, changes: List[Dict], 
                    batch_size: int = 1000) -> None:
        """Save document changes to database with improved batch processing"""
        if not changes:
            return
        
        query = """
            INSERT OR IGNORE INTO document_changes 
            (date_from, date_to, sentence_from, sentence_to, change_type, similarity_score)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        
        data = []
        for change in changes:
            data.append((
                date_from,
                date_to,
                change.get('sentence_from', ''),
                change.get('sentence_to', ''),
                change.get('type', ''),
                change.get('similarity', 0.0)
            ))
        
        try:
            self.db.execute_many(query, data, batch_size=batch_size)
            logger.info(f"Saved {len(data)} document changes from {date_from} to {date_to}")
        except Exception as e:
            logger.error(f"Failed to save document changes: {e}")
            raise
    
    def get_changes(self, date_from: str, date_to: str, 
                   change_types: Optional[List[str]] = None,
                   min_similarity: Optional[float] = None,
                   limit: Optional[int] = None) -> pd.DataFrame:
        """Get changes between two dates with filtering options"""
        base_query = """
            SELECT * FROM document_changes
            WHERE date_from = ? AND date_to = ?
        """
        params = [date_from, date_to]
        
        if change_types:
            placeholders = ','.join(['?' for _ in change_types])
            base_query += f" AND change_type IN ({placeholders})"
            params.extend(change_types)
        
        if min_similarity is not None:
            base_query += " AND similarity_score >= ?"
            params.append(min_similarity)
        
        base_query += " ORDER BY similarity_score DESC"
        
        if limit:
            base_query += " LIMIT ?"
            params.append(limit)
        
        return self.db.get_dataframe(base_query, params)
    
    def get_change_summary(self, start_date: Optional[str] = None, 
                          end_date: Optional[str] = None) -> pd.DataFrame:
        """Get summary of all changes with optional date filtering"""
        base_query = """
            SELECT 
                date_from,
                date_to,
                change_type,
                COUNT(*) as count,
                AVG(similarity_score) as avg_similarity,
                MIN(similarity_score) as min_similarity,
                MAX(similarity_score) as max_similarity,
                STDDEV(similarity_score) as std_similarity
            FROM document_changes
            WHERE 1=1
        """
        params = []
        
        if start_date:
            base_query += " AND date_from >= ?"
            params.append(start_date)
        
        if end_date:
            base_query += " AND date_to <= ?"
            params.append(end_date)
        
        base_query += """
            GROUP BY date_from, date_to, change_type
            ORDER BY date_from DESC, date_to DESC, count DESC
        """
        
        return self.db.get_dataframe(base_query, params)
    
    def get_change_patterns(self) -> pd.DataFrame:
        """Analyze patterns in document changes over time"""
        query = """
            WITH change_stats AS (
                SELECT 
                    date_from,
                    date_to,
                    change_type,
                    COUNT(*) as change_count,
                    AVG(similarity_score) as avg_similarity,
                    julianday(date_to) - julianday(date_from) as days_between
                FROM document_changes
                GROUP BY date_from, date_to, change_type
            ),
            aggregated AS (
                SELECT 
                    change_type,
                    AVG(change_count) as avg_changes_per_period,
                    AVG(avg_similarity) as overall_avg_similarity,
                    AVG(days_between) as avg_days_between,
                    COUNT(*) as total_periods,
                    SUM(change_count) as total_changes
                FROM change_stats
                GROUP BY change_type
            )
            SELECT 
                change_type,
                total_changes,
                total_periods,
                avg_changes_per_period,
                overall_avg_similarity,
                avg_days_between,
                CASE 
                    WHEN avg_changes_per_period > 10 THEN 'High'
                    WHEN avg_changes_per_period > 5 THEN 'Medium'
                    ELSE 'Low'
                END as change_frequency
            FROM aggregated
            ORDER BY total_changes DESC
        """
        return self.db.get_dataframe(query)
    
    def get_similarity_distribution(self, bins: int = 10) -> pd.DataFrame:
        """Get distribution of similarity scores"""
        query = f"""
            SELECT 
                change_type,
                CAST((similarity_score * {bins}) AS INTEGER) * (1.0/{bins}) as similarity_bin,
                COUNT(*) as count
            FROM document_changes
            WHERE similarity_score IS NOT NULL
            GROUP BY change_type, similarity_bin
            ORDER BY change_type, similarity_bin
        """
        return self.db.get_dataframe(query)
    
    def get_most_volatile_periods(self, limit: int = 10) -> pd.DataFrame:
        """Identify periods with the most document changes"""
        query = """
            SELECT 
                date_from,
                date_to,
                COUNT(*) as total_changes,
                COUNT(DISTINCT change_type) as change_types_count,
                AVG(similarity_score) as avg_similarity,
                MIN(similarity_score) as min_similarity,
                MAX(similarity_score) as max_similarity,
                julianday(date_to) - julianday(date_from) as days_between
            FROM document_changes
            GROUP BY date_from, date_to
            ORDER BY total_changes DESC
            LIMIT ?
        """
        return self.db.get_dataframe(query, [limit])
    
    def cleanup_old_changes(self, days_to_keep: int = 365) -> int:
        """Clean up old document changes beyond specified days"""
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).strftime('%Y-%m-%d')
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM document_changes 
                    WHERE date_from < ?
                """, [cutoff_date])
                deleted_count = cursor.rowcount
                conn.commit()
                
                logger.info(f"Cleaned up {deleted_count} old document changes before {cutoff_date}")
                return deleted_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup old changes: {e}")
            raise


class FOMCDateModel:
    """Enhanced model for FOMC meeting dates with additional functionality"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self._ensure_indexes()
    
    def _ensure_indexes(self):
        """Ensure required indexes exist for optimal performance"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_fomc_dates_date ON fomc_dates(date)",
            "CREATE INDEX IF NOT EXISTS idx_fomc_dates_statement ON fomc_dates(has_statement)",
            "CREATE INDEX IF NOT EXISTS idx_fomc_dates_press_conf ON fomc_dates(has_press_conf)",
            "CREATE INDEX IF NOT EXISTS idx_fomc_dates_minutes ON fomc_dates(has_minutes)"
        ]
        
        try:
            with self.db.get_connection() as conn:
                for index_query in indexes:
                    conn.execute(index_query)
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to create FOMC dates indexes: {e}")
    
    def add_date(self, date: str, has_statement: bool = False, 
                has_press_conf: bool = False, has_minutes: bool = False) -> None:
        """Add a new FOMC date"""
        data = {
            'date': date,
            'has_statement': has_statement,
            'has_press_conf': has_press_conf,
            'has_minutes': has_minutes
        }
        
        try:
            self.db.upsert('fomc_dates', data, ['date'])
            logger.info(f"Added/updated FOMC date: {date}")
        except Exception as e:
            logger.error(f"Failed to add FOMC date {date}: {e}")
            raise
    
    def get_all_dates(self, include_document_counts: bool = False) -> pd.DataFrame:
        """Get all FOMC dates with optional document counts"""
        if include_document_counts:
            query = """
                SELECT 
                    fd.*,
                    COALESCE(pc.prediction_count, 0) as prediction_count,
                    COALESCE(dc.document_types, 0) as document_types_count
                FROM fomc_dates fd
                LEFT JOIN (
                    SELECT date, COUNT(*) as prediction_count
                    FROM predictions
                    GROUP BY date
                ) pc ON fd.date = pc.date
                LEFT JOIN (
                    SELECT date, COUNT(DISTINCT document_type) as document_types
                    FROM predictions
                    WHERE document_type IS NOT NULL
                    GROUP BY date
                ) dc ON fd.date = dc.date
                ORDER BY fd.date DESC
            """
        else:
            query = "SELECT * FROM fomc_dates ORDER BY date DESC"
        
        return self.db.get_dataframe(query)
    
    def get_recent_dates(self, limit: int = 12, include_future: bool = True) -> pd.DataFrame:
        """Get recent FOMC dates with option to include future dates"""
        base_query = "SELECT * FROM fomc_dates"
        params = []
        
        if not include_future:
            base_query += " WHERE date <= DATE('now')"
        
        base_query += " ORDER BY date DESC LIMIT ?"
        params.append(limit)
        
        return self.db.get_dataframe(base_query, params)
    
    def get_date_info(self, date: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive info for specific date"""
        try:
            # Basic date info
            query = "SELECT * FROM fomc_dates WHERE date = ?"
            result = self.db.execute_query(query, [date])
            
            if not result:
                return None
            
            date_info = dict(result[0])
            
            # Add prediction statistics
            pred_query = """
                SELECT 
                    COUNT(*) as total_predictions,
                    COUNT(DISTINCT document_type) as document_types,
                    AVG(max_prob) as avg_confidence
                FROM predictions
                WHERE date = ?
            """
            pred_result = self.db.execute_query(pred_query, [date])
            if pred_result:
                pred_info = dict(pred_result[0])
                date_info.update(pred_info)
            
            return date_info
            
        except Exception as e:
            logger.error(f"Failed to get date info for {date}: {e}")
            return None
    
    def get_meeting_frequency_analysis(self) -> pd.DataFrame:
        """Analyze the frequency and patterns of FOMC meetings"""
        query = """
            WITH date_diffs AS (
                SELECT 
                    date,
                    LAG(date) OVER (ORDER BY date) as prev_date,
                    julianday(date) - julianday(LAG(date) OVER (ORDER BY date)) as days_since_last
                FROM fomc_dates
                WHERE date IS NOT NULL
            )
            SELECT 
                CAST(days_since_last AS INTEGER) as days_between,
                COUNT(*) as frequency,
                MIN(date) as first_occurrence,
                MAX(date) as last_occurrence
            FROM date_diffs
            WHERE days_since_last IS NOT NULL
            GROUP BY CAST(days_since_last AS INTEGER)
            ORDER BY frequency DESC
        """
        return self.db.get_dataframe(query)
    
    def get_document_availability_summary(self) -> Dict[str, Any]:
        """Get summary of document availability across meetings"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                
                total_meetings = cursor.execute("SELECT COUNT(*) FROM fomc_dates").fetchone()[0]
                
                summary = {
                    'total_meetings': total_meetings,
                    'statement_available': cursor.execute("SELECT COUNT(*) FROM fomc_dates WHERE has_statement = 1").fetchone()[0],
                    'press_conf_available': cursor.execute("SELECT COUNT(*) FROM fomc_dates WHERE has_press_conf = 1").fetchone()[0],
                    'minutes_available': cursor.execute("SELECT COUNT(*) FROM fomc_dates WHERE has_minutes = 1").fetchone()[0]
                }
                
                # Calculate percentages
                for key in ['statement_available', 'press_conf_available', 'minutes_available']:
                    if total_meetings > 0:
                        summary[f"{key}_pct"] = (summary[key] / total_meetings) * 100
                    else:
                        summary[f"{key}_pct"] = 0
                
                return summary
                
        except Exception as e:
            logger.error(f"Failed to get document availability summary: {e}")
            return {}


class MetricsModel:
    """New model for handling financial and economic metrics"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self._ensure_indexes()
    
    def _ensure_indexes(self):
        """Ensure required indexes exist for optimal performance"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_metrics_date ON metrics(date)",
            "CREATE INDEX IF NOT EXISTS idx_metrics_series ON metrics(series)",
            "CREATE INDEX IF NOT EXISTS idx_metrics_date_series ON metrics(date, series)",
            "CREATE INDEX IF NOT EXISTS idx_metrics_value ON metrics(value)",
            "CREATE INDEX IF NOT EXISTS idx_metrics_source ON metrics(source)"
        ]
        
        try:
            with self.db.get_connection() as conn:
                for index_query in indexes:
                    conn.execute(index_query)
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to create metrics indexes: {e}")
    
    def save_metric(self, date: str, series: str, value: float, 
                   source: Optional[str] = None) -> None:
        """Save a metric value"""
        data = {
            'date': date,
            'series': series,
            'value': value,
            'source': source or 'manual',
            'created_at': datetime.now().isoformat()
        }
        
        try:
            self.db.upsert('metrics', data, ['date', 'series'])
            logger.debug(f"Saved metric {series} for {date}: {value}")
        except Exception as e:
            logger.error(f"Failed to save metric {series} for {date}: {e}")
            raise
    
    def save_metrics_batch(self, metrics_data: List[Dict[str, Any]], 
                          batch_size: int = 1000) -> None:
        """Save multiple metrics efficiently"""
        if not metrics_data:
            return
        
        query = """
            INSERT OR REPLACE INTO metrics (date, series, value, source, created_at)
            VALUES (?, ?, ?, ?, ?)
        """
        
        data = []
        for metric in metrics_data:
            data.append((
                metric['date'],
                metric['series'],
                metric['value'],
                metric.get('source', 'batch'),
                datetime.now().isoformat()
            ))
        
        try:
            self.db.execute_many(query, data, batch_size=batch_size)
            logger.info(f"Saved {len(data)} metrics in batch")
        except Exception as e:
            logger.error(f"Failed to save metrics batch: {e}")
            raise
    
    def get_series_data(self, series: str, start_date: Optional[str] = None,
                       end_date: Optional[str] = None) -> pd.DataFrame:
        """Get data for a specific metric series"""
        base_query = "SELECT * FROM metrics WHERE series = ?"
        params = [series]
        
        if start_date:
            base_query += " AND date >= ?"
            params.append(start_date)
        
        if end_date:
            base_query += " AND date <= ?"
            params.append(end_date)
        
        base_query += " ORDER BY date"
        return self.db.get_dataframe(base_query, params)
    
    def get_multiple_series(self, series_list: List[str], 
                           start_date: Optional[str] = None,
                           end_date: Optional[str] = None) -> pd.DataFrame:
        """Get data for multiple series"""
        if not series_list:
            return pd.DataFrame()
        
        placeholders = ','.join(['?' for _ in series_list])
        base_query = f"SELECT * FROM metrics WHERE series IN ({placeholders})"
        params = series_list.copy()
        
        if start_date:
            base_query += " AND date >= ?"
            params.append(start_date)
        
        if end_date:
            base_query += " AND date <= ?"
            params.append(end_date)
        
        base_query += " ORDER BY date, series"
        return self.db.get_dataframe(base_query, params)
    
    def get_available_series(self, source: Optional[str] = None) -> pd.DataFrame:
        """Get list of available metric series"""
        base_query = """
            SELECT 
                series,
                COUNT(*) as data_points,
                MIN(date) as start_date,
                MAX(date) as end_date,
                AVG(value) as avg_value,
                MIN(value) as min_value,
                MAX(value) as max_value,
                source
            FROM metrics
            WHERE 1=1
        """
        params = []
        
        if source:
            base_query += " AND source = ?"
            params.append(source)
        
        base_query += " GROUP BY series, source ORDER BY series"
        return self.db.get_dataframe(base_query, params)
    
    def get_correlation_matrix(self, series_list: List[str], 
                              start_date: Optional[str] = None,
                              end_date: Optional[str] = None) -> pd.DataFrame:
        """Calculate correlation matrix between metric series"""
        df = self.get_multiple_series(series_list, start_date, end_date)
        
        if df.empty:
            return pd.DataFrame()
        
        # Pivot the data
        pivot_df = df.pivot(index='date', columns='series', values='value')
        
        # Calculate correlation matrix
        return pivot_df.corr()
    
    def cleanup_old_metrics(self, days_to_keep: int = 1095) -> int:  # 3 years default
        """Clean up old metric data"""
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).strftime('%Y-%m-%d')
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM metrics WHERE date < ?", [cutoff_date])
                deleted_count = cursor.rowcount
                conn.commit()
                
                logger.info(f"Cleaned up {deleted_count} old metrics before {cutoff_date}")
                return deleted_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup old metrics: {e}")
            raise