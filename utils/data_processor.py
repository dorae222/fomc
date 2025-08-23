import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sqlite3
from collections import Counter
import re
import config
from database.models import PredictionModel, DocumentChangeModel

class DataProcessor:
    def __init__(self):
        self.prediction_model = PredictionModel()
        self.change_model = DocumentChangeModel()
        
    def process_predictions(self, df):
        """Process prediction dataframe with additional features"""
        # Add rolling sentiment scores
        window = 10
        df['hawkish_rolling'] = (df['pred_label'] == 'hawkish').rolling(window, min_periods=1).mean()
        df['dovish_rolling'] = (df['pred_label'] == 'dovish').rolling(window, min_periods=1).mean()
        df['neutral_rolling'] = (df['pred_label'] == 'neutral').rolling(window, min_periods=1).mean()
        
        # Add confidence categories
        df['confidence_level'] = pd.cut(
            df['max_prob'],
            bins=[0, config.CONFIDENCE_THRESHOLDS['low'], 
                  config.CONFIDENCE_THRESHOLDS['medium'],
                  config.CONFIDENCE_THRESHOLDS['high'], 1.0],
            labels=['low', 'medium', 'high', 'very_high']
        )
        
        # Add sentiment momentum
        df['sentiment_momentum'] = self._calculate_momentum(df)
        
        # Add key phrase indicators
        df['contains_key_phrase'] = df['text'].apply(self._contains_key_phrase)
        
        return df
    
    def _calculate_momentum(self, df):
        """Calculate sentiment momentum"""
        momentum = []
        for i in range(len(df)):
            if i < 5:
                momentum.append(0)
            else:
                recent = df.iloc[i-5:i]
                hawkish_trend = (recent['pred_label'] == 'hawkish').mean()
                dovish_trend = (recent['pred_label'] == 'dovish').mean()
                momentum.append(hawkish_trend - dovish_trend)
        return momentum
    
    def _contains_key_phrase(self, text):
        """Check if text contains key monetary policy phrases"""
        key_phrases = [
            'inflation', 'employment', 'growth', 'rates', 'policy',
            'economic', 'financial', 'stability', 'outlook', 'risks',
            'target', 'objective', 'mandate', 'data', 'conditions'
        ]
        text_lower = text.lower()
        return any(phrase in text_lower for phrase in key_phrases)
    
    def get_summary(self, df):
        """Generate comprehensive summary statistics"""
        if df.empty:
            return {}
        
        # Basic statistics
        summary = {
            'total_sentences': len(df),
            'sentiment_distribution': df['pred_label'].value_counts(normalize=True).to_dict(),
            'avg_confidence': df['max_prob'].mean(),
            'confidence_std': df['max_prob'].std(),
            'high_confidence_count': (df['max_prob'] > config.CONFIDENCE_THRESHOLDS['high']).sum(),
        }
        
        # Sentiment progression
        summary['sentiment_shifts'] = self.detect_sentiment_shifts(df)
        
        # Tone calculation
        summary['tone'] = self.calculate_meeting_tone(df)
        
        # Key statistics by sentiment
        for sentiment in ['hawkish', 'dovish', 'neutral']:
            sentiment_df = df[df['pred_label'] == sentiment]
            if not sentiment_df.empty:
                summary[f'{sentiment}_stats'] = {
                    'count': len(sentiment_df),
                    'avg_confidence': sentiment_df['max_prob'].mean(),
                    'max_confidence': sentiment_df['max_prob'].max(),
                    'min_confidence': sentiment_df['max_prob'].min()
                }
        
        return summary
    
    def detect_sentiment_shifts(self, df, threshold=0.3):
        """Detect significant sentiment shifts in document"""
        df = self.process_predictions(df)
        
        shifts = []
        for i in range(1, len(df)):
            for sentiment in ['hawkish', 'dovish']:
                col = f'{sentiment}_rolling'
                if col in df.columns and i > 0:
                    change = df.iloc[i][col] - df.iloc[i-1][col]
                    if abs(change) > threshold:
                        shifts.append({
                            'position': i,
                            'type': sentiment,
                            'magnitude': abs(change),
                            'direction': 'increase' if change > 0 else 'decrease',
                            'text': df.iloc[i]['text'][:200] if 'text' in df.columns else ''
                        })
        
        return shifts
    
    def calculate_meeting_tone(self, df):
        """Calculate overall meeting tone score"""
        if df.empty:
            return {'tone_score': 0, 'interpretation': 'Neutral'}
        
        # Weighted by confidence
        hawkish_score = ((df['pred_label'] == 'hawkish') * df['max_prob']).sum()
        dovish_score = ((df['pred_label'] == 'dovish') * df['max_prob']).sum()
        
        total_score = hawkish_score + dovish_score
        if total_score > 0:
            tone_score = (hawkish_score - dovish_score) / total_score
        else:
            tone_score = 0
        
        return {
            'tone_score': tone_score,  # -1 (very dovish) to 1 (very hawkish)
            'interpretation': self._interpret_tone(tone_score),
            'hawkish_weight': hawkish_score,
            'dovish_weight': dovish_score
        }
    
    def _interpret_tone(self, score):
        """Interpret tone score"""
        if score < -0.5:
            return 'Very Dovish'
        elif score < -0.2:
            return 'Dovish'
        elif score < 0.2:
            return 'Neutral'
        elif score < 0.5:
            return 'Hawkish'
        else:
            return 'Very Hawkish'
    
    def extract_key_themes(self, df, top_n=10):
        """Extract key themes from text"""
        if 'text' not in df.columns:
            return []
        
        # Simple word frequency analysis
        all_text = ' '.join(df['text'].values)
        words = re.findall(r'\b[a-z]+\b', all_text.lower())
        
        # Filter out common words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
                     'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
                     'is', 'are', 'was', 'were', 'been', 'be', 'have', 'has', 'had', 'do',
                     'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might'}
        
        filtered_words = [w for w in words if w not in stop_words and len(w) > 3]
        
        # Count frequencies
        word_freq = Counter(filtered_words)
        
        # Get top themes
        themes = []
        for word, count in word_freq.most_common(top_n):
            # Find sentences containing this word
            sentences = df[df['text'].str.lower().str.contains(word, na=False)]
            
            if not sentences.empty:
                # Calculate sentiment association
                sentiment_dist = sentences['pred_label'].value_counts(normalize=True).to_dict()
                
                themes.append({
                    'word': word,
                    'frequency': count,
                    'sentiment_association': sentiment_dist,
                    'avg_confidence': sentences['max_prob'].mean()
                })
        
        return themes
    
    def compare_meetings(self, date1, date2):
        """Compare two FOMC meetings"""
        df1 = self.prediction_model.get_by_date(date1)
        df2 = self.prediction_model.get_by_date(date2)
        
        if df1.empty or df2.empty:
            return None
        
        comparison = {
            'date1': {
                'date': date1,
                'summary': self.get_summary(df1),
                'themes': self.extract_key_themes(df1, top_n=5)
            },
            'date2': {
                'date': date2,
                'summary': self.get_summary(df2),
                'themes': self.extract_key_themes(df2, top_n=5)
            }
        }
        
        # Calculate differences
        comparison['changes'] = {
            'tone_change': comparison['date2']['summary']['tone']['tone_score'] - 
                          comparison['date1']['summary']['tone']['tone_score'],
            'confidence_change': comparison['date2']['summary']['avg_confidence'] - 
                               comparison['date1']['summary']['avg_confidence'],
            'sentiment_shift': {
                'hawkish': (comparison['date2']['summary']['sentiment_distribution'].get('hawkish', 0) - 
                           comparison['date1']['summary']['sentiment_distribution'].get('hawkish', 0)),
                'dovish': (comparison['date2']['summary']['sentiment_distribution'].get('dovish', 0) - 
                          comparison['date1']['summary']['sentiment_distribution'].get('dovish', 0)),
                'neutral': (comparison['date2']['summary']['sentiment_distribution'].get('neutral', 0) - 
                           comparison['date1']['summary']['sentiment_distribution'].get('neutral', 0))
            }
        }
        
        return comparison