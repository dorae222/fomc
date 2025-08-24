from flask import Flask, render_template, jsonify, request
import pandas as pd
import sqlite3
import json
from datetime import datetime, timedelta
import os
import threading
import plotly.graph_objs as go
import plotly.utils
from utils.data_processor import DataProcessor
from utils.visualization import ChartGenerator
from utils.text_diff import TextComparator
from utils.precompute import ensure_sentiment_daily, precompute_recent_pairs, get_compare_payload
from utils.data_loader import DataLoader
from utils.rag_index import build_or_load_index, FAISS_DB_PATH_DEFAULT
import config
from typing import List
import hashlib
import threading as _threading

# Optional: RAG Chatbot state (lazy init)
_CHATBOT_STATE = {
    'initialized': False,
    'retriever': None,
    'prompt': None,
    'llm': None
}
_CHATBOT_LOCK = _threading.Lock()

app = Flask(__name__)
app.config.from_object(config)

processor = DataProcessor()
chart_gen = ChartGenerator()
text_comp = TextComparator()
data_loader = DataLoader()
_PRECOMPUTE_STARTED = False
_RAG_PREWARM_STARTED = False

def _ensure_sentiment_daily():
    # Delegate to utils.precompute implementation
    ensure_sentiment_daily(force=False, show_progress=False)
    
def _get_compare_payload(conn, date1: str, date2: str, types: List[str]):
    # Delegate to utils.precompute implementation
    return get_compare_payload(conn, date1, date2, types, use_cache=True)

def _precompute_recent_pairs(limit_pairs: int = 8):
    # Delegate to utils.precompute implementation
    precompute_recent_pairs(limit_pairs=limit_pairs, show_progress=False)

def _ensure_chatbot_chain():
    """Lazy-initialize the RAG chain from chatbot.py once per process."""
    if _CHATBOT_STATE['initialized']:
        return
    with _CHATBOT_LOCK:
        if _CHATBOT_STATE['initialized']:
            return
        try:
            # Import locally to avoid hard dependency if not used
            import chatbot as rag_bot
            retriever, prompt, llm = rag_bot.create_rag_chain()
            _CHATBOT_STATE.update({
                'initialized': True,
                'retriever': retriever,
                'prompt': prompt,
                'llm': llm
            })
        except Exception as e:
            app.logger.error(f"Failed to init chatbot chain: {e}")
            raise

@app.before_request
def _maybe_init_aggregates():
    """One-time init before the first handled request in this process."""
    global _PRECOMPUTE_STARTED, _RAG_PREWARM_STARTED
    if not _PRECOMPUTE_STARTED:
        try:
            _ensure_sentiment_daily()
        except Exception as e:
            app.logger.warning(f"Failed to ensure sentiment_daily: {e}")
        try:
            threading.Thread(target=_precompute_recent_pairs, kwargs={'limit_pairs': 8}, daemon=True).start()
        except Exception as e:
            app.logger.warning(f"Failed to start precompute thread: {e}")
        _PRECOMPUTE_STARTED = True
    if not _RAG_PREWARM_STARTED:
        def _prewarm():
            try:
                path = os.environ.get('FAISS_DB_PATH', FAISS_DB_PATH_DEFAULT)
                max_docs = int(os.environ.get('FOMC_RAG_MAX_DOCS', '200'))
            except Exception:
                path, max_docs = FAISS_DB_PATH_DEFAULT, 200
            try:
                build_or_load_index(path, None, max_docs)
                app.logger.info("RAG index prewarmed")
            except Exception as e:
                app.logger.warning(f"RAG prewarm failed: {e}")
        try:
            threading.Thread(target=_prewarm, daemon=True).start()
            _RAG_PREWARM_STARTED = True
        except Exception as e:
            app.logger.warning(f"Failed to start RAG prewarm thread: {e}")

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')

@app.route('/api/summary')
def get_summary():
    """Get dashboard summary statistics"""
    conn = sqlite3.connect(config.DATABASE_PATH)
    
    try:
        # Total predictions
        total_query = "SELECT COUNT(*) as total FROM predictions"
        total_result = pd.read_sql_query(total_query, conn)
        total_predictions = total_result['total'].iloc[0]
        
        # Sentiment distribution
        sentiment_query = '''
            SELECT pred_label, COUNT(*) as count
            FROM predictions
            GROUP BY pred_label
        '''
        sentiment_df = pd.read_sql_query(sentiment_query, conn)
        
        # Convert to percentages
        total = sentiment_df['count'].sum()
        sentiment_distribution = {}
        for _, row in sentiment_df.iterrows():
            sentiment_distribution[row['pred_label']] = row['count'] / total
        
        # Average confidence
        confidence_query = "SELECT AVG(max_prob) as avg_confidence FROM predictions"
        confidence_result = pd.read_sql_query(confidence_query, conn)
        avg_confidence = confidence_result['avg_confidence'].iloc[0]
        
        # Recent activity (last 30 days if date available)
        recent_query = '''
            SELECT COUNT(*) as recent_count 
            FROM predictions 
            WHERE date >= date('now', '-30 days')
        '''
        recent_result = pd.read_sql_query(recent_query, conn)
        recent_predictions = recent_result['recent_count'].iloc[0]
        
    except Exception as e:
        app.logger.error(f"Error in summary API: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()
    
    return jsonify({
        'total_predictions': int(total_predictions),
        'sentiment_distribution': sentiment_distribution,
        'avg_confidence': float(avg_confidence) if avg_confidence else 0,
        'recent_predictions': int(recent_predictions)
    })

@app.route('/api/overview')
def get_overview():
    """Get overview statistics"""
    # Ensure precomputed aggregates exist for fast queries
    try:
        _ensure_sentiment_daily()
    except Exception:
        pass
    
    conn = sqlite3.connect(config.DATABASE_PATH)
    
    try:
        doc_types = request.args.get('doc_types', '')
        types: List[str] = [t.strip() for t in doc_types.split(',') if t.strip()]
        
        # Overall sentiment distribution (precomputed)
        where = ''
        params: List[str] = []
        if types:
            placeholders = ','.join(['?'] * len(types))
            where = f"WHERE document_type IN ({placeholders})"
            params = types
        
        try:
            sentiment_dist = pd.read_sql_query(
                f"""
                SELECT pred_label, SUM(count) as count, 
                       SUM(avg_confidence * count) / NULLIF(SUM(count),0) as avg_confidence
                FROM sentiment_daily
                {where}
                GROUP BY pred_label
                """,
                conn, params=params
            )
        except Exception:
            # Fallback to computing from predictions
            where_pred = ''
            params_pred: List[str] = []
            if types:
                placeholders = ','.join(['?'] * len(types))
                where_pred = f"WHERE document_type IN ({placeholders})"
                params_pred = types
            sentiment_dist = pd.read_sql_query(
                f"""
                SELECT pred_label, COUNT(*) as count, AVG(max_prob) as avg_confidence
                FROM predictions
                {where_pred}
                GROUP BY pred_label
                """,
                conn, params=params_pred
            )
        
        # Recent meetings sentiment trend
        and_doc = ''
        params2: List[str] = []
        if types:
            placeholders = ','.join(['?'] * len(types))
            and_doc = f" AND document_type IN ({placeholders})"
            params2 = types
        try:
            trend_data = pd.read_sql_query(
                f"""
                SELECT date, pred_label, SUM(count) as count
                FROM sentiment_daily
                WHERE 1=1{and_doc}
                GROUP BY date, pred_label
                ORDER BY date DESC
                LIMIT 300
                """,
                conn, params=params2
            )
        except Exception:
            trend_data = pd.read_sql_query(
                f"""
                SELECT date, pred_label, COUNT(*) as count
                FROM predictions
                WHERE date IS NOT NULL{and_doc}
                GROUP BY date, pred_label
                ORDER BY date DESC
                LIMIT 300
                """,
                conn, params=params2
            )
        
        # Document type distribution
        try:
            doc_dist = pd.read_sql_query(
                """
                SELECT document_type, pred_label, SUM(count) as count
                FROM sentiment_daily
                GROUP BY document_type, pred_label
                """,
                conn
            )
        except Exception:
            doc_dist = pd.read_sql_query(
                """
                SELECT document_type, pred_label, COUNT(*) as count
                FROM predictions
                WHERE date IS NOT NULL
                GROUP BY document_type, pred_label
                """,
                conn
            )
        
        return jsonify({
            'sentiment_distribution': sentiment_dist.to_dict('records'),
            'trend_data': trend_data.to_dict('records'),
            'document_distribution': doc_dist.to_dict('records')
        })
    
    finally:
        conn.close()

@app.route('/api/meeting/<date>')
def get_meeting_details(date):
    """Get detailed analysis for specific FOMC meeting"""
    conn = sqlite3.connect(config.DATABASE_PATH)
    doc_types = request.args.get('doc_types', '')
    types: List[str] = [t.strip() for t in doc_types.split(',') if t.strip()]
    
    and_doc = ''
    params: List[str] = [date]
    if types:
        placeholders = ','.join(['?'] * len(types))
        and_doc = f" AND document_type IN ({placeholders})"
        params += types
    query = f'''
        SELECT * FROM predictions
        WHERE date = ?{and_doc}
        ORDER BY id
    '''
    df = pd.read_sql_query(query, conn, params=params)
    
    # Calculate sentiment progression
    df['cumulative_hawkish'] = (df['pred_label'] == 'hawkish').cumsum()
    df['cumulative_dovish'] = (df['pred_label'] == 'dovish').cumsum()
    df['cumulative_neutral'] = (df['pred_label'] == 'neutral').cumsum()
    
    # High confidence sentences
    high_conf = df[df['max_prob'] > config.CONFIDENCE_THRESHOLDS['high']]
    
    conn.close()
    
    return jsonify({
        'sentences': df.to_dict('records'),
        'high_confidence': high_conf.to_dict('records'),
        'statistics': {
            'total_sentences': len(df),
            'hawkish_pct': (df['pred_label'] == 'hawkish').mean() * 100,
            'dovish_pct': (df['pred_label'] == 'dovish').mean() * 100,
            'neutral_pct': (df['pred_label'] == 'neutral').mean() * 100,
            'avg_confidence': df['max_prob'].mean()
        }
    })

@app.route('/api/compare')
def compare_meetings():
    """Compare two FOMC meetings"""
    date1 = request.args.get('date1')
    date2 = request.args.get('date2')
    doc_types = request.args.get('doc_types', '')
    types: List[str] = [t.strip() for t in doc_types.split(',') if t.strip()]
    
    if not date1 or not date2:
        return jsonify({'error': 'Both dates required'}), 400
    
    conn = sqlite3.connect(config.DATABASE_PATH)
    payload = _get_compare_payload(conn, date1, date2, types)
    conn.close()
    return jsonify(payload)

@app.route('/compare', methods=['POST'])
def compare_meetings_post():
    """Compare two FOMC meetings (POST endpoint for UI)"""
    date1 = request.form.get('meeting1')
    date2 = request.form.get('meeting2')
    
    if not date1 or not date2:
        return '<div class="alert alert-danger">Both meeting dates are required</div>', 400
    
    if date1 == date2:
        return '<div class="alert alert-warning">Please select two different meetings</div>', 400
    
    conn = sqlite3.connect(config.DATABASE_PATH)
    try:
        payload = _get_compare_payload(conn, date1, date2, [])
        
        # Render comparison results as HTML
        results_html = f"""
        <div class="row">
            <div class="col-12">
                <h3 class="text-center mb-4">
                    <i class="bi bi-graph-up me-2"></i>Comparison Results
                </h3>
                <div class="text-center mb-4">
                    <span class="badge bg-primary fs-6">{format_date_display(date1)}</span>
                    <span class="mx-3 fs-4">VS</span>
                    <span class="badge bg-success fs-6">{format_date_display(date2)}</span>
                </div>
            </div>
        </div>
        
        <div class="row">
            <div class="col-md-6">
                <div class="card h-100">
                    <div class="card-header bg-primary text-white">
                        <h5 class="mb-0">{format_date_display(date1)}</h5>
                    </div>
                    <div class="card-body">
                        <div class="row text-center">
                            <div class="col-4">
                                <h4 class="text-danger">{payload.get('meeting1_stats', {}).get('hawkish', 0)}</h4>
                                <small class="text-muted">Hawkish</small>
                            </div>
                            <div class="col-4">
                                <h4 class="text-secondary">{payload.get('meeting1_stats', {}).get('neutral', 0)}</h4>
                                <small class="text-muted">Neutral</small>
                            </div>
                            <div class="col-4">
                                <h4 class="text-success">{payload.get('meeting1_stats', {}).get('dovish', 0)}</h4>
                                <small class="text-muted">Dovish</small>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="col-md-6">
                <div class="card h-100">
                    <div class="card-header bg-success text-white">
                        <h5 class="mb-0">{format_date_display(date2)}</h5>
                    </div>
                    <div class="card-body">
                        <div class="row text-center">
                            <div class="col-4">
                                <h4 class="text-danger">{payload.get('meeting2_stats', {}).get('hawkish', 0)}</h4>
                                <small class="text-muted">Hawkish</small>
                            </div>
                            <div class="col-4">
                                <h4 class="text-secondary">{payload.get('meeting2_stats', {}).get('neutral', 0)}</h4>
                                <small class="text-muted">Neutral</small>
                            </div>
                            <div class="col-4">
                                <h4 class="text-success">{payload.get('meeting2_stats', {}).get('dovish', 0)}</h4>
                                <small class="text-muted">Dovish</small>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="row mt-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0"><i class="bi bi-bar-chart me-2"></i>Sentiment Changes</h5>
                    </div>
                    <div class="card-body">
                        <p class="text-muted">Detailed comparison analysis would go here...</p>
                    </div>
                </div>
            </div>
        </div>
        """
        
        return results_html
        
    except Exception as e:
        app.logger.error(f"Comparison error: {e}")
        return f'<div class="alert alert-danger">Error comparing meetings: {str(e)}</div>', 500
    finally:
        conn.close()

def format_date_display(date_str):
    """Format date string for display"""
    try:
        from datetime import datetime
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.strftime('%B %d, %Y')
    except:
        return date_str

@app.route('/api/timeline')
def get_timeline():
    """Get timeline view of sentiment evolution"""
    # Ensure precomputed aggregates exist
    try:
        _ensure_sentiment_daily()
    except Exception:
        pass
    conn = sqlite3.connect(config.DATABASE_PATH)
    doc_types = request.args.get('doc_types', '')
    types: List[str] = [t.strip() for t in doc_types.split(',') if t.strip()]
    
    and_doc = ''
    params: List[str] = []
    if types:
        placeholders = ','.join(['?'] * len(types))
        and_doc = f" AND document_type IN ({placeholders})"
        params = types
    # Aggregate from precomputed daily table
    query = f'''
        SELECT 
            date,
            pred_label,
            SUM(count) as count
        FROM sentiment_daily
        WHERE date IS NOT NULL{and_doc}
        GROUP BY date, pred_label
        ORDER BY date
    '''
    try:
        df = pd.read_sql_query(query, conn, params=params)
    except Exception:
        # Fallback to predictions aggregation if precomputed table missing
        query2 = f'''
            SELECT 
                date,
                pred_label,
                COUNT(*) as count
            FROM predictions
            WHERE date IS NOT NULL{and_doc}
            GROUP BY date, pred_label
            ORDER BY date
        '''
        df = pd.read_sql_query(query2, conn, params=params)

    # Pivot for easier visualization
    if df.empty:
        conn.close()
        return jsonify({'dates': [], 'hawkish': [], 'dovish': [], 'neutral': []})

    pivot_df = df.pivot_table(
        index='date',
        columns='pred_label',
        values='count',
        fill_value=0
    )
    # Calculate percentages
    pivot_df = pivot_df.div(pivot_df.sum(axis=1), axis=0) * 100

    payload = {
        'dates': pivot_df.index.tolist(),
        'hawkish': pivot_df.get('hawkish', pd.Series(dtype=float)).tolist(),
        'dovish': pivot_df.get('dovish', pd.Series(dtype=float)).tolist(),
        'neutral': pivot_df.get('neutral', pd.Series(dtype=float)).tolist()
    }
    conn.close()
    return jsonify(payload)

@app.route('/api/document-types')
def get_document_types():
    conn = sqlite3.connect(config.DATABASE_PATH)
    try:
        df = pd.read_sql_query("SELECT DISTINCT document_type FROM predictions WHERE document_type IS NOT NULL ORDER BY document_type", conn)
        types = df['document_type'].dropna().tolist()
    except Exception:
        types = []
    finally:
        conn.close()
    return jsonify({'document_types': types})

@app.route('/api/recent-changes')
def get_recent_changes():
    """Compute recent sentiment/text changes between the last two meetings for optional doc types."""
    doc_types = request.args.get('doc_types', '')
    types: List[str] = [t.strip() for t in doc_types.split(',') if t.strip()]
    conn = sqlite3.connect(config.DATABASE_PATH)
    try:
        dates_df = pd.read_sql_query(
            f"SELECT DISTINCT date FROM predictions WHERE date IS NOT NULL{' AND document_type IN (' + ','.join(['?'] * len(types)) + ')' if types else ''} ORDER BY date DESC LIMIT 2",
            conn, params=types if types else []
        )
        if len(dates_df) < 2:
            return jsonify({'dates': [], 'changes': {}})
        d1, d2 = dates_df['date'].iloc[1], dates_df['date'].iloc[0]
        if len(types) <= 1:
            # Use direct cache for 'all' or single type
            payload = _get_compare_payload(conn, d1, d2, types)
            changes = payload.get('changes', {})
        else:
            # Merge per-doc_type cached results to avoid heavy recomputation
            merged = { 'added': [], 'removed': [], 'modified': [], 'sentiment_changed': [] }
            for t in types:
                p = _get_compare_payload(conn, d1, d2, [t])
                ch = p.get('changes', {}) if isinstance(p, dict) else {}
                for k in merged.keys():
                    items = ch.get(k, [])
                    # annotate items with their doc_type
                    for it in items:
                        if isinstance(it, dict):
                            it = dict(it)
                            it['doc_type'] = t
                        merged[k].append(it)
            # Rank and trim top-K per category
            def topk(lst, key, reverse=True, k=10):
                try:
                    return sorted(lst, key=lambda x: x.get(key, 0) if isinstance(x, dict) else 0, reverse=reverse)[:k]
                except Exception:
                    return lst[:10]
            changes = {
                'sentiment_changed': topk(merged['sentiment_changed'], key='confidence_change', reverse=True),
                'added': topk(merged['added'], key='confidence', reverse=True),
                'removed': topk(merged['removed'], key='confidence', reverse=True),
                'modified': topk(merged['modified'], key='similarity', reverse=True)
            }
    finally:
        conn.close()
    # Ensure max 10 per category for dashboard brevity
    for k in list(changes.keys()):
        changes[k] = changes.get(k, [])[:10]
    return jsonify({'dates': [d1, d2], 'changes': changes})

@app.route('/api/finance')
def get_finance_metrics():
    """Return finance metrics for given date range and series.
    Query params: start, end, series (comma-separated)
    """
    start = request.args.get('start')
    end = request.args.get('end')
    series_param = request.args.get('series', '')
    series: List[str] = [s.strip() for s in series_param.split(',') if s.strip()]

    conn = sqlite3.connect(config.DATABASE_PATH)
    try:
        base = "SELECT date, series, value FROM metrics"
        conditions = []
        params: List[str] = []
        if start:
            conditions.append("date >= ?")
            params.append(start)
        if end:
            conditions.append("date <= ?")
            params.append(end)
        if series:
            placeholders = ','.join(['?'] * len(series))
            conditions.append(f"series IN ({placeholders})")
            params.extend(series)
        if conditions:
            base += " WHERE " + " AND ".join(conditions)
        base += " ORDER BY date, series"
        df = pd.read_sql_query(base, conn, params=params)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

    return jsonify(df.to_dict('records'))

@app.route('/api/meetings')
def get_meetings():
    """Return meeting dates with document counts, optionally filtered by document types.
    Query param: doc_types=comma,separated
    Response: { meetings: [{date: str, count: int}], dates: [...] }
    """
    doc_types = request.args.get('doc_types', '')
    types: List[str] = [t.strip() for t in doc_types.split(',') if t.strip()]
    conn = sqlite3.connect(config.DATABASE_PATH)
    try:
        if types:
            placeholders = ','.join(['?'] * len(types))
            df = pd.read_sql_query(
                f"""SELECT date, COUNT(*) as count 
                   FROM predictions 
                   WHERE date IS NOT NULL AND document_type IN ({placeholders}) 
                   GROUP BY date 
                   ORDER BY date""",
                conn, params=types
            )
        else:
            # Get all meetings with document counts
            df = pd.read_sql_query(
                """SELECT date, COUNT(*) as count 
                   FROM predictions 
                   WHERE date IS NOT NULL 
                   GROUP BY date 
                   ORDER BY date""",
                conn
            )
    except Exception as e:
        app.logger.error(f"Error in meetings API: {e}")
        df = pd.DataFrame(columns=['date', 'count'])
    finally:
        conn.close()

    if df.empty:
        return jsonify({'meetings': [], 'dates': []})

    # Ensure ISO date strings
    df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.strftime('%Y-%m-%d')
    df = df.dropna(subset=['date'])
    
    meetings = [{'date': row['date'], 'count': int(row['count'])} for _, row in df.iterrows()]
    
    return jsonify({
        'meetings': meetings,
        'dates': df['date'].tolist()  # Keep for backward compatibility
    })

@app.route('/api/correlation')
def get_correlation():
    """Compute correlation between sentiment and selected finance series.
    Query params: series, window (optional)
    """
    series = request.args.get('series', '')
    window = int(request.args.get('window', 0))
    if not series:
        return jsonify({'error': 'series required'}), 400

    conn = sqlite3.connect(config.DATABASE_PATH)
    try:
        # Sentiment by date (hawkish share)
        sent_query = '''
            SELECT date, AVG(CASE WHEN pred_label='hawkish' THEN 1.0 ELSE 0 END) AS hawkish_share,
                   AVG(max_prob) AS avg_conf
            FROM predictions
            WHERE date IS NOT NULL
            GROUP BY date
        '''
        sent_df = pd.read_sql_query(sent_query, conn)

        # Finance series
        fin_df = pd.read_sql_query(
            "SELECT date, series, value FROM metrics WHERE series = ? ORDER BY date",
            conn, params=[series]
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()

    if sent_df.empty or fin_df.empty:
        return jsonify({'error': 'insufficient data'}), 400

    # Merge by date
    merged = pd.merge(sent_df, fin_df.pivot(index='date', columns='series', values='value').reset_index(), on='date', how='inner')
    merged = merged.sort_values('date')

    # Optional rolling window
    if window and window > 1:
        merged['hawkish_share_roll'] = merged['hawkish_share'].rolling(window).mean()
        merged[f'{series}_roll'] = merged[series].rolling(window).mean()
        x = merged['hawkish_share_roll']
        y = merged[f'{series}_roll']
    else:
        x = merged['hawkish_share']
        y = merged[series]

    corr = float(x.corr(y)) if len(merged) >= 2 else 0.0

    return jsonify({
        'series': series,
        'window': window,
        'correlation': corr,
        'points': merged[['date', 'hawkish_share', series]].to_dict('records')
    })

@app.route('/api/charts/sentiment-flow/<date>')
def get_sentiment_flow(date):
    """Generate sentiment flow chart for a meeting"""
    conn = sqlite3.connect(config.DATABASE_PATH)
    
    query = '''
        SELECT id, pred_label, max_prob, text
        FROM predictions
        WHERE date = ?
        ORDER BY id
    '''
    
    df = pd.read_sql_query(query, conn, params=[date])
    conn.close()
    
    if df.empty:
        return jsonify({'error': 'No data found'}), 404
    
    chart = chart_gen.create_sentiment_flow(df)
    
    return jsonify(chart)

@app.route('/api/charts/confidence-heatmap')
def get_confidence_heatmap():
    """Generate confidence heatmap"""
    conn = sqlite3.connect(config.DATABASE_PATH)
    
    query = '''
        SELECT date, document_type, pred_label, AVG(max_prob) as avg_confidence
        FROM predictions
        WHERE date IS NOT NULL
        GROUP BY date, document_type, pred_label
        ORDER BY date DESC
        LIMIT 500
    '''
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    chart = chart_gen.create_confidence_heatmap(df)
    
    return jsonify(chart)

@app.route('/api/fulltext/<date>')
def get_full_text(date):
    """Return the full document text tokenized to sentences with sentiment labels for a given date.
    Optional: doc_types=comma,separated to filter.
    """
    conn = sqlite3.connect(config.DATABASE_PATH)
    doc_types = request.args.get('doc_types', '')
    types: List[str] = [t.strip() for t in doc_types.split(',') if t.strip()]
    and_doc = ''
    params: List[str] = [date]
    if types:
        placeholders = ','.join(['?'] * len(types))
        and_doc = f" AND document_type IN ({placeholders})"
        params += types
    df = pd.read_sql_query(
        f"SELECT text, pred_label, max_prob FROM predictions WHERE date = ?{and_doc} ORDER BY id",
        conn, params=params
    )
    conn.close()
    return jsonify(df.to_dict('records'))

@app.route('/analysis')
def analysis_page():
    """Detailed analysis page"""
    return render_template('analysis.html')

@app.route('/comparison')
def comparison_page():
    """Document comparison page"""
    return render_template('comparison.html')

@app.route('/timeline')
def timeline_page():
    """Timeline visualization page"""
    return render_template('timeline.html')

@app.route('/load-data')
def load_data_page():
    """Data loading page"""
    return render_template('load_data.html')

@app.route('/chatbot')
def chatbot_page():
    """Chatbot UI page"""
    return render_template('chatbot.html')

@app.route('/chatbot/ask', methods=['POST'])
def chatbot_ask():
    """RAG chatbot endpoint. Body: {question: str}"""
    data = request.get_json()
    if not data or 'question' not in data:
        return jsonify({'error': 'Question not provided'}), 400

    question = data['question']
    
    try:
        # Import and use the answer_question function
        from chatbot import answer_question
        result = answer_question(question)
        return jsonify(result)
    except Exception as e:
        app.logger.error(f"Error in chatbot endpoint: {e}")
        return jsonify({'error': 'Failed to get an answer.'}), 500


@app.route('/api/load-data', methods=['POST'])
def load_data():
    """Load predictions from CSV file"""
    try:
        request_data = request.get_json() or {}
        limit = request_data.get('limit')
        
        # Clear existing data if requested
        if request_data.get('clear_existing'):
            data_loader.clear_predictions()
        
        # Load data
        count = data_loader.load_predictions_from_csv(limit=limit)
        
        # Get statistics
        stats = data_loader.get_loading_stats()
        
        return jsonify({
            'success': True,
            'message': f'Successfully loaded {count:,} predictions',
            'count': count,
            'stats': stats
        })
        
    except Exception as e:
        app.logger.error(f"Error loading data: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/data-stats')
def get_data_stats():
    """Get current data loading statistics"""
    try:
        stats = data_loader.get_loading_stats()
        return jsonify(stats)
    except Exception as e:
        app.logger.error(f"Error getting data stats: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Start background precompute on main process only
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        _ensure_sentiment_daily()
        threading.Thread(target=_precompute_recent_pairs, kwargs={'limit_pairs': 8}, daemon=True).start()
        # Also prewarm RAG index once
        def _prewarm():
            try:
                path = os.environ.get('FAISS_DB_PATH', FAISS_DB_PATH_DEFAULT)
                max_docs = int(os.environ.get('FOMC_RAG_MAX_DOCS', '200'))
            except Exception:
                path, max_docs = FAISS_DB_PATH_DEFAULT, 200
            try:
                build_or_load_index(path, None, max_docs)
            except Exception as e:
                app.logger.warning(f"RAG prewarm failed: {e}")
        threading.Thread(target=_prewarm, daemon=True).start()
    app.run(debug=True, port=5000)