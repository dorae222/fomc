import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
PROCESSED_DIR = DATA_DIR / 'processed'
DATABASE_PATH = BASE_DIR / 'fomc_analysis.db'

# Flask settings
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
DEBUG = True

# Data files
PREDICTIONS_FILE = DATA_DIR / 'all_predictions.csv'
FOMC_DATES_FILE = DATA_DIR / 'fomc_dates_template.csv'

# Visualization settings
SENTIMENT_COLORS = {
    'hawkish': '#FF6B6B',
    'neutral': '#95A5A6',
    'dovish': '#4ECDC4'
}

CONFIDENCE_THRESHOLDS = {
    'high': 0.8,
    'medium': 0.6,
    'low': 0.4
}