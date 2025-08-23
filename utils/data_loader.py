"""
Data loader utility for loading all_predictions.csv into the existing database structure
"""
import pandas as pd
import sqlite3
import os
import logging
from datetime import datetime
from database.models import DatabaseManager, PredictionModel
import config

logger = logging.getLogger(__name__)

class DataLoader:
    """Handles loading CSV data into the existing database structure"""
    
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.prediction_model = PredictionModel()
    
    def parse_source_file(self, source_file: str) -> tuple:
        """Extract document type and date from source_file path"""
        try:
            # Extract document type from path like "beigebook/2011/20110302_beigebook.pdf"
            parts = source_file.split('/')
            if len(parts) >= 3:
                document_type = parts[0]  # e.g., "beigebook"
                year_part = parts[1]      # e.g., "2011"
                filename = parts[2]       # e.g., "20110302_beigebook.pdf"
                
                # Extract date from filename (assume format: YYYYMMDD_)
                if len(filename) >= 8 and filename[:8].isdigit():
                    date_str = filename[:8]  # "20110302"
                    date = datetime.strptime(date_str, '%Y%m%d').strftime('%Y-%m-%d')
                    return document_type, date, year_part
            
            # Fallback: just use first part as document type
            document_type = parts[0] if parts else 'unknown'
            return document_type, None, None
            
        except Exception as e:
            logger.warning(f"Error parsing source_file {source_file}: {e}")
            return 'unknown', None, None
    
    def load_predictions_from_csv(self, csv_path: str = 'data/all_predictions.csv', limit: int = None, batch_size: int = 10000):
        """Load predictions from CSV file into database"""
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
        
        logger.info(f"Loading predictions from {csv_path}")
        
        # Read CSV file
        try:
            # First check total rows
            total_rows = sum(1 for line in open(csv_path)) - 1  # subtract header
            logger.info(f"Total rows in CSV: {total_rows}")
            
            if limit:
                logger.info(f"Limited to: {limit} rows")
                total_rows = min(total_rows, limit)
            
            # Read in chunks to handle large files
            chunk_iter = pd.read_csv(csv_path, chunksize=batch_size, nrows=limit)
            
            processed_count = 0
            with self.db_manager.get_connection() as conn:
                for chunk_num, chunk in enumerate(chunk_iter, 1):
                    logger.info(f"Processing chunk {chunk_num}, rows: {len(chunk)}")
                    
                    # Process each row
                    batch_data = []
                    for _, row in chunk.iterrows():
                        document_type, date, year = self.parse_source_file(row['source_file'])
                        
                        prediction_data = {
                            'original_id': row['id'],
                            'source_file': row['source_file'], 
                            'text': row['text'],
                            'pred_label': row['pred_label'],
                            'max_prob': float(row['max_prob']),
                            'document_type': document_type,
                            'date': date,
                            'year': year,
                            'created_at': datetime.now().isoformat()
                        }
                        batch_data.append(prediction_data)
                    
                    # Insert batch
                    if batch_data:
                        self._insert_predictions_batch(conn, batch_data)
                        processed_count += len(batch_data)
                        logger.info(f"Processed {processed_count}/{total_rows} rows")
            
            logger.info(f"Successfully loaded {processed_count} predictions")
            return processed_count
            
        except Exception as e:
            logger.error(f"Error loading CSV: {e}")
            raise
    
    def _insert_predictions_batch(self, conn: sqlite3.Connection, batch_data: list):
        """Insert a batch of predictions into database"""
        insert_sql = """
        INSERT INTO predictions (
            original_id, source_file, text, pred_label, max_prob, 
            document_type, date, year, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        values = []
        for data in batch_data:
            values.append((
                data['original_id'],
                data['source_file'],
                data['text'],
                data['pred_label'],
                data['max_prob'],
                data['document_type'],
                data['date'],
                data['year'],
                data['created_at']
            ))
        
        conn.executemany(insert_sql, values)
        conn.commit()
    
    def get_loading_stats(self) -> dict:
        """Get statistics about loaded data"""
        with self.db_manager.get_connection() as conn:
            # Total predictions
            total_result = conn.execute("SELECT COUNT(*) FROM predictions").fetchone()
            total_predictions = total_result[0]
            
            # Document types
            doc_types_result = conn.execute("""
                SELECT document_type, COUNT(*) as count 
                FROM predictions 
                GROUP BY document_type 
                ORDER BY count DESC
            """).fetchall()
            
            # Sentiment distribution
            sentiment_result = conn.execute("""
                SELECT pred_label, COUNT(*) as count 
                FROM predictions 
                GROUP BY pred_label
            """).fetchall()
            
            # Years covered
            years_result = conn.execute("""
                SELECT MIN(year) as min_year, MAX(year) as max_year 
                FROM predictions 
                WHERE year IS NOT NULL
            """).fetchone()
            
            return {
                'total_predictions': total_predictions,
                'document_types': dict(doc_types_result),
                'sentiment_distribution': dict(sentiment_result),
                'year_range': {
                    'min': years_result[0],
                    'max': years_result[1]
                } if years_result[0] else None
            }
    
    def clear_predictions(self):
        """Clear all predictions from database"""
        with self.db_manager.get_connection() as conn:
            conn.execute("DELETE FROM predictions")
            conn.commit()
        logger.info("Cleared all predictions from database")

if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    loader = DataLoader()
    
    # Load sample data (first 50000 rows for testing)
    try:
        count = loader.load_predictions_from_csv(limit=50000)
        print(f"Loaded {count} predictions")
        
        # Show stats
        stats = loader.get_loading_stats()
        print("\nDatabase Statistics:")
        print(f"Total predictions: {stats['total_predictions']:,}")
        print(f"Document types: {stats['document_types']}")
        print(f"Sentiment distribution: {stats['sentiment_distribution']}")
        print(f"Year range: {stats['year_range']}")
        
    except Exception as e:
        print(f"Error: {e}")
