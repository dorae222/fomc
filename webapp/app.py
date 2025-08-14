from flask import Flask, render_template, jsonify, request
import pandas as pd
import json
import os
from datetime import datetime, timedelta, timezone

app = Flask(__name__)

# 데이터 로딩 함수들
def load_celebrity_data():
    """연예인 기본 통계 데이터 로드"""
    try:
        df = pd.read_csv('data/celebrity_stats.csv')
        return df.to_dict('records')
    except FileNotFoundError:
        # 샘플 데이터
        return [
            {'name': 'IU', 'total_comments': 45230, 'positive_ratio': 78.5, 'negative_ratio': 21.5},
            {'name': 'BTS', 'total_comments': 89456, 'positive_ratio': 82.3, 'negative_ratio': 17.7},
            {'name': '아이브', 'total_comments': 32190, 'positive_ratio': 75.2, 'negative_ratio': 24.8},
            {'name': '뉴진스', 'total_comments': 28456, 'positive_ratio': 79.8, 'negative_ratio': 20.2}
        ]

def load_sentiment_data(celebrity_name=None):
    """감성 분석 데이터 로드"""
    try:
        df = pd.read_csv('data/sentiment_analysis.csv')
        if celebrity_name:
            df = df[df['celebrity'] == celebrity_name]
        return df.to_dict('records')
    except FileNotFoundError:
        # 샘플 데이터
        return [
            {'celebrity': 'IU', 'date': '2023-10-01', 'positive': 456, 'negative': 123, 'neutral': 234},
            {'celebrity': 'IU', 'date': '2023-10-02', 'positive': 523, 'negative': 145, 'neutral': 267},
            {'celebrity': 'BTS', 'date': '2023-10-01', 'positive': 1234, 'negative': 234, 'neutral': 456}
        ]

def load_keyword_data(celebrity_name=None):
    """키워드 분석 데이터 로드"""
    try:
        df = pd.read_csv('data/keyword_analysis.csv')
        if celebrity_name:
            df = df[df['celebrity'] == celebrity_name]
        return df.to_dict('records')
    except FileNotFoundError:
        # 샘플 데이터
        return [
            {'celebrity': 'IU', 'keyword': '노래', 'count': 1234, 'sentiment': 'positive'},
            {'celebrity': 'IU', 'keyword': '예쁘다', 'count': 987, 'sentiment': 'positive'},
            {'celebrity': 'IU', 'keyword': '목소리', 'count': 756, 'sentiment': 'positive'},
            {'celebrity': 'BTS', 'keyword': '월드투어', 'count': 2345, 'sentiment': 'positive'}
        ]

def load_comment_data(celebrity_name=None, limit=1000):
    """댓글 원문 데이터 로드 (연관어/워드클라우드 용)"""
    try:
        df = pd.read_csv('data/comment_data.csv')
        if celebrity_name:
            df = df[df['celebrity'] == celebrity_name]
        if limit:
            df = df.head(int(limit))
        return df[['celebrity', 'text', 'date']].to_dict('records')
    except FileNotFoundError:
        # 간단 샘플
        sample = [
            {'celebrity': 'IU', 'text': 'IU 노래 너무 좋아요 목소리 예쁘다 최고야', 'date': '2025-08-01'},
            {'celebrity': 'IU', 'text': '콘서트 정보 알려주세요 음악 감동이에요', 'date': '2025-08-02'},
            {'celebrity': 'BTS', 'text': 'BTS 월드투어 대박 사랑해 최고야', 'date': '2025-08-03'},
        ]
        if celebrity_name:
            sample = [r for r in sample if r['celebrity'] == celebrity_name]
        return sample[:limit] if limit else sample

def load_timeline_data(celebrity_name=None):
    """타임라인 데이터 로드"""
    try:
        df = pd.read_csv('data/timeline_data.csv')
        if celebrity_name:
            df = df[df['celebrity'] == celebrity_name]
        return df.to_dict('records')
    except FileNotFoundError:
        # 샘플 데이터
        dates = [(datetime.now() - timedelta(days=x)).strftime('%Y-%m-%d') for x in range(30, 0, -1)]
        return [
            {'celebrity': 'IU', 'date': date, 'comment_count': 100 + (i * 10), 'positive_ratio': 75 + (i % 10)}
            for i, date in enumerate(dates)
        ]

@app.route('/')
def index():
    """메인 페이지"""
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    """대시보드 페이지"""
    celebrity_data = load_celebrity_data()
    return render_template('dashboard.html', celebrities=celebrity_data)

from flask import redirect, url_for

@app.route('/celebrity')
def celebrity():
    """기존 연예인별 페이지는 대시보드로 리다이렉트"""
    name = request.args.get('name')
    compare = request.args.get('compare')
    period = request.args.get('period')
    qs = []
    if name: qs.append(f"name={name}")
    if compare: qs.append(f"compare={compare}")
    if period: qs.append(f"period={period}")
    return redirect(url_for('dashboard') + (('?' + '&'.join(qs)) if qs else ''))

@app.route('/sentiment')
def sentiment():
    """기존 감성 페이지는 대시보드로 리다이렉트"""
    name = request.args.get('name')
    compare = request.args.get('compare')
    period = request.args.get('period')
    qs = []
    if name: qs.append(f"name={name}")
    if compare: qs.append(f"compare={compare}")
    if period: qs.append(f"period={period}")
    return redirect(url_for('dashboard') + (('?' + '&'.join(qs)) if qs else ''))

@app.route('/keywords')
def keywords():
    """기존 키워드 페이지는 대시보드로 리다이렉트"""
    name = request.args.get('name')
    compare = request.args.get('compare')
    period = request.args.get('period')
    qs = []
    if name: qs.append(f"name={name}")
    if compare: qs.append(f"compare={compare}")
    if period: qs.append(f"period={period}")
    return redirect(url_for('dashboard') + (('?' + '&'.join(qs)) if qs else ''))

@app.route('/team')
def team():
    """팀 소개 페이지"""
    return render_template('team.html')

# API 엔드포인트들
@app.route('/api/celebrity/<name>/sentiment')
def api_celebrity_sentiment(name):
    """특정 연예인의 감성 분석 데이터 API"""
    data = load_sentiment_data(name)
    return jsonify(data)

@app.route('/api/celebrity/<name>/keywords')
def api_celebrity_keywords(name):
    """특정 연예인의 키워드 데이터 API"""
    data = load_keyword_data(name)
    return jsonify(data)

@app.route('/api/celebrity/<name>/comments')
def api_celebrity_comments(name):
    """특정 연예인의 댓글 원문 데이터 API (텍스트만 필요)"""
    try:
        limit = int(request.args.get('limit') or 1000)
    except Exception:
        limit = 1000
    data = load_comment_data(name, limit=limit)
    return jsonify(data)

@app.route('/api/celebrity/<name>/timeline')
def api_celebrity_timeline(name):
    """특정 연예인의 타임라인 데이터 API"""
    data = load_timeline_data(name)
    return jsonify(data)

@app.route('/api/celebrities')
def api_celebrities():
    """전체 연예인 리스트 API"""
    data = load_celebrity_data()
    return jsonify(data)

if __name__ == '__main__':
    # 데이터 폴더가 없으면 생성
    os.makedirs('data', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)