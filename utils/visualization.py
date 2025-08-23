import plotly.graph_objs as go
import plotly.express as px
import pandas as pd
import numpy as np
from plotly.subplots import make_subplots
import config

class ChartGenerator:
    def __init__(self):
        self.colors = config.SENTIMENT_COLORS
        self.template = 'plotly_white'
        
    def create_sentiment_flow(self, df):
        """Create interactive sentiment flow chart with confidence visualization"""
        fig = make_subplots(
            rows=2, cols=1,
            row_heights=[0.7, 0.3],
            subplot_titles=('Sentiment Flow with Confidence', 'Sentiment Momentum'),
            vertical_spacing=0.1
        )
        
        # Main sentiment flow
        for sentiment in ['hawkish', 'neutral', 'dovish']:
            mask = df['pred_label'] == sentiment
            
            # Add scatter plot with variable size based on confidence
            fig.add_trace(go.Scatter(
                x=df[mask].index if df[mask].index.name else df[mask]['sentence_id'],
                y=df[mask]['max_prob'],
                mode='markers',
                name=sentiment.capitalize(),
                marker=dict(
                    color=self.colors[sentiment],
                    size=df[mask]['max_prob'] * 25,
                    opacity=0.6,
                    line=dict(width=1, color='white')
                ),
                text=df[mask]['text'].str[:150] + '...' if 'text' in df.columns else None,
                hovertemplate='<b>%{text}</b><br>' +
                             'Confidence: %{y:.2%}<br>' +
                             'Position: %{x}<extra></extra>',
                showlegend=True
            ), row=1, col=1)
        
        # Add rolling average lines
        window = 10
        for sentiment in ['hawkish', 'dovish']:
            rolling = (df['pred_label'] == sentiment).rolling(window, min_periods=1).mean()
            
            fig.add_trace(go.Scatter(
                x=df.index if df.index.name else df['sentence_id'] if 'sentence_id' in df.columns else range(len(df)),
                y=rolling,
                mode='lines',
                name=f'{sentiment.capitalize()} Trend',
                line=dict(
                    color=self.colors[sentiment],
                    width=2,
                    dash='dash'
                ),
                opacity=0.5,
                showlegend=False
            ), row=1, col=1)
        
        # Add momentum indicator
        momentum = []
        for i in range(len(df)):
            if i < 5:
                momentum.append(0)
            else:
                recent = df.iloc[i-5:i]
                h = (recent['pred_label'] == 'hawkish').mean()
                d = (recent['pred_label'] == 'dovish').mean()
                momentum.append(h - d)
        
        fig.add_trace(go.Scatter(
            x=df.index if df.index.name else range(len(df)),
            y=momentum,
            mode='lines',
            name='Momentum',
            fill='tozeroy',
            line=dict(color='#2C3E50', width=1),
            fillcolor='rgba(44, 62, 80, 0.2)'
        ), row=2, col=1)
        
        # Add zero line for momentum
        fig.add_hline(y=0, line_dash="dot", line_color="gray", row=2, col=1)
        
        fig.update_xaxes(title_text="Sentence Position", row=2, col=1)
        fig.update_yaxes(title_text="Confidence", tickformat='.0%', row=1, col=1)
        fig.update_yaxes(title_text="Momentum", row=2, col=1)
        
        fig.update_layout(
            height=600,
            hovermode='x unified',
            showlegend=True,
            template=self.template
        )
        
        return fig.to_dict()
    
    def create_confidence_heatmap(self, df):
        """Create confidence heatmap with enhanced visualization"""
        # Prepare data for heatmap
        if 'date' not in df.columns or 'pred_label' not in df.columns:
            return {}
        
        pivot = df.pivot_table(
            index='date',
            columns='pred_label',
            values='avg_confidence',
            fill_value=0
        )
        
        # Create annotated heatmap
        fig = go.Figure(data=go.Heatmap(
            z=pivot.values,
            x=pivot.columns,
            y=pivot.index,
            colorscale=[
                [0, '#E8F4F3'],
                [0.5, '#FFFFFF'],
                [1, '#FFE8E8']
            ],
            zmid=0.5,
            text=np.round(pivot.values * 100, 1),
            texttemplate='%{text}%',
            textfont={"size": 10},
            colorbar=dict(
                title='Avg Confidence (%)',
                tickmode='linear',
                tick0=0,
                dtick=0.1,
                tickformat='.0%'
            ),
            hovertemplate='Date: %{y}<br>' +
                         'Sentiment: %{x}<br>' +
                         'Confidence: %{z:.1%}<extra></extra>'
        ))
        
        fig.update_layout(
            title='Sentiment Confidence Heatmap by Meeting',
            xaxis_title='Sentiment',
            yaxis_title='Meeting Date',
            height=max(400, len(pivot.index) * 20),
            template=self.template
        )
        
        return fig.to_dict()
    
    def create_3d_sentiment_surface(self, df):
        """Create 3D surface plot of sentiment evolution"""
        if df.empty:
            return {}
        
        # Prepare data
        dates = df['date'].unique() if 'date' in df.columns else range(len(df))
        sentiments = ['hawkish', 'neutral', 'dovish']
        
        # Create grid
        Z = []
        for date in dates:
            date_data = df[df['date'] == date] if 'date' in df.columns else df.iloc[date:date+1]
            row = []
            for sentiment in sentiments:
                count = (date_data['pred_label'] == sentiment).sum()
                row.append(count / len(date_data) if len(date_data) > 0 else 0)
            Z.append(row)
        
        fig = go.Figure(data=[go.Surface(
            z=Z,
            x=sentiments,
            y=dates,
            colorscale='RdBu_r',
            showscale=True,
            colorbar=dict(title='Proportion')
        )])
        
        fig.update_layout(
            title='3D Sentiment Surface',
            scene=dict(
                xaxis_title='Sentiment',
                yaxis_title='Date',
                zaxis_title='Proportion',
                camera=dict(
                    eye=dict(x=1.5, y=1.5, z=1.3)
                )
            ),
            height=600,
            template=self.template
        )
        
        return fig.to_dict()
    
    def create_sunburst_chart(self, df):
        """Create sunburst chart for hierarchical sentiment analysis"""
        if df.empty:
            return {}
        
        # Prepare hierarchical data
        data = []
        
        # Root
        data.append(dict(
            labels=['Total'],
            parents=[''],
            values=[len(df)],
            marker_colors=['#FFFFFF']
        ))
        
        # By sentiment
        for sentiment in ['hawkish', 'neutral', 'dovish']:
            sentiment_df = df[df['pred_label'] == sentiment]
            if not sentiment_df.empty:
                # Add sentiment level
                data.append(dict(
                    labels=[sentiment.capitalize()],
                    parents=['Total'],
                    values=[len(sentiment_df)],
                    marker_colors=[self.colors[sentiment]]
                ))
                
                # Add confidence levels
                for level in ['high', 'medium', 'low']:
                    if level == 'high':
                        level_df = sentiment_df[sentiment_df['max_prob'] > 0.8]
                    elif level == 'medium':
                        level_df = sentiment_df[(sentiment_df['max_prob'] > 0.6) & 
                                              (sentiment_df['max_prob'] <= 0.8)]
                    else:
                        level_df = sentiment_df[sentiment_df['max_prob'] <= 0.6]
                    
                    if not level_df.empty:
                        data.append(dict(
                            labels=[f'{level.capitalize()} Conf'],
                            parents=[sentiment.capitalize()],
                            values=[len(level_df)],
                            marker_colors=[self.colors[sentiment]]
                        ))
        
        # Flatten data structure
        all_labels = []
        all_parents = []
        all_values = []
        all_colors = []
        
        for d in data:
            all_labels.extend(d['labels'])
            all_parents.extend(d['parents'])
            all_values.extend(d['values'])
            all_colors.extend(d['marker_colors'])
        
        fig = go.Figure(go.Sunburst(
            labels=all_labels,
            parents=all_parents,
            values=all_values,
            marker=dict(colors=all_colors),
            branchvalues="total",
            hovertemplate='<b>%{label}</b><br>' +
                         'Count: %{value}<br>' +
                         'Percentage: %{percentParent}<extra></extra>'
        ))
        
        fig.update_layout(
            title='Sentiment Distribution Hierarchy',
            height=500,
            template=self.template
        )
        
        return fig.to_dict()
    
    def create_network_graph(self, df, similarity_threshold=0.7):
        """Create network graph showing relationships between similar statements"""
        import networkx as nx
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        
        if 'text' not in df.columns or len(df) > 100:  # Limit for performance
            return {}
        
        # Calculate similarity matrix
        vectorizer = TfidfVectorizer(max_features=100)
        tfidf_matrix = vectorizer.fit_transform(df['text'])
        similarity_matrix = cosine_similarity(tfidf_matrix)
        
        # Create graph
        G = nx.Graph()
        
        # Add nodes
        for i, row in df.iterrows():
            G.add_node(i, 
                      sentiment=row['pred_label'],
                      confidence=row['max_prob'],
                      text=row['text'][:100])
        
        # Add edges for similar statements
        for i in range(len(similarity_matrix)):
            for j in range(i+1, len(similarity_matrix)):
                if similarity_matrix[i][j] > similarity_threshold:
                    G.add_edge(i, j, weight=similarity_matrix[i][j])
        
        # Get layout
        pos = nx.spring_layout(G, k=1, iterations=50)
        
        # Create traces
        edge_trace = []
        for edge in G.edges(data=True):
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            edge_trace.append(go.Scatter(
                x=[x0, x1, None],
                y=[y0, y1, None],
                mode='lines',
                line=dict(width=edge[2]['weight']*2, color='#888'),
                hoverinfo='none',
                showlegend=False
            ))
        
        node_trace = go.Scatter(
            x=[pos[node][0] for node in G.nodes()],
            y=[pos[node][1] for node in G.nodes()],
            mode='markers+text',
            hoverinfo='text',
            marker=dict(
                color=[self.colors[G.nodes[node]['sentiment']] for node in G.nodes()],
                size=[G.nodes[node]['confidence']*30 for node in G.nodes()],
                line=dict(width=2, color='white')
            ),
            text=[G.nodes[node]['sentiment'][0].upper() for node in G.nodes()],
            hovertext=[G.nodes[node]['text'] for node in G.nodes()],
            textposition="middle center",
            showlegend=False
        )
        
        fig = go.Figure(data=edge_trace + [node_trace])
        
        fig.update_layout(
            title='Statement Similarity Network',
            showlegend=False,
            hovermode='closest',
            height=600,
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            template=self.template
        )
        
        return fig.to_dict()