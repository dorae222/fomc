import difflib
from typing import List, Tuple, Dict

class TextComparator:
    def __init__(self, similarity_threshold=0.7):
        self.similarity_threshold = similarity_threshold
    
    def find_changes(self, texts1, texts2):
        """Find changes between two sets of texts"""
        changes = {
            'added': [],
            'removed': [],
            'modified': [],
            'sentiment_changed': []
        }
        
        # Create mapping of similar sentences
        matches = []
        for i, (text1, label1, prob1) in enumerate(texts1):
            best_match = None
            best_score = 0
            
            for j, (text2, label2, prob2) in enumerate(texts2):
                score = self.calculate_similarity(text1, text2)
                if score > best_score and score > self.similarity_threshold:
                    best_score = score
                    best_match = (j, text2, label2, prob2)
            
            if best_match:
                matches.append({
                    'index1': i,
                    'index2': best_match[0],
                    'text1': text1,
                    'text2': best_match[1],
                    'label1': label1,
                    'label2': best_match[2],
                    'prob1': prob1,
                    'prob2': best_match[3],
                    'similarity': best_score
                })
                
                # Check for sentiment changes
                if label1 != best_match[2]:
                    changes['sentiment_changed'].append({
                        'text': text1[:200],
                        'from_sentiment': label1,
                        'to_sentiment': best_match[2],
                        'confidence_change': best_match[3] - prob1
                    })
                
                # Check for text modifications
                if best_score < 0.95:  # Not identical
                    changes['modified'].append({
                        'original': text1[:200],
                        'modified': best_match[1][:200],
                        'similarity': best_score
                    })
            else:
                changes['removed'].append({
                    'text': text1[:200],
                    'sentiment': label1,
                    'confidence': prob1
                })
        
        # Find added sentences
        matched_indices2 = {m['index2'] for m in matches}
        for j, (text2, label2, prob2) in enumerate(texts2):
            if j not in matched_indices2:
                changes['added'].append({
                    'text': text2[:200],
                    'sentiment': label2,
                    'confidence': prob2
                })
        
        return changes
    
    def calculate_similarity(self, text1, text2):
        """Calculate similarity between two texts"""
        return difflib.SequenceMatcher(None, text1, text2).ratio()
    
    def generate_diff_html(self, text1, text2):
        """Generate HTML diff visualization"""
        d = difflib.HtmlDiff()
        return d.make_file(
            text1.splitlines(),
            text2.splitlines(),
            fromdesc='Previous Meeting',
            todesc='Current Meeting'
        )