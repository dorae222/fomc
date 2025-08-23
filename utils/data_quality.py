"""
Data Quality Monitoring and Validation System
"""

import sqlite3
import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import config
from database.models import DatabaseManager

logger = logging.getLogger(__name__)

@dataclass
class QualityCheck:
    """Data quality check definition"""
    name: str
    description: str
    query: str
    threshold: Optional[float] = None
    severity: str = 'warning'  # 'info', 'warning', 'error', 'critical'
    enabled: bool = True

@dataclass
class QualityResult:
    """Result of a data quality check"""
    check_name: str
    status: str  # 'pass', 'fail', 'error'
    value: Any
    threshold: Optional[float]
    message: str
    severity: str
    timestamp: datetime
    details: Optional[Dict] = None

class DataQualityMonitor:
    """Monitor and validate data quality across the FOMC database"""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.checks = self._define_quality_checks()
    
    def _define_quality_checks(self) -> List[QualityCheck]:
        """Define all data quality checks"""
        return [
            # Completeness checks
            QualityCheck(
                name="null_prediction_dates",
                description="Check for predictions with null dates",
                query="SELECT COUNT(*) FROM predictions WHERE date IS NULL",
                threshold=0,
                severity="error"
            ),
            QualityCheck(
                name="null_prediction_text",
                description="Check for predictions with null text",
                query="SELECT COUNT(*) FROM predictions WHERE text IS NULL OR text = ''",
                threshold=0,
                severity="error"
            ),
            QualityCheck(
                name="missing_confidence_scores",
                description="Check for predictions with null confidence scores",
                query="SELECT COUNT(*) FROM predictions WHERE max_prob IS NULL",
                threshold=0,
                severity="error"
            ),
            
            # Validity checks
            QualityCheck(
                name="invalid_confidence_scores",
                description="Check for confidence scores outside valid range [0,1]",
                query="SELECT COUNT(*) FROM predictions WHERE max_prob < 0 OR max_prob > 1",
                threshold=0,
                severity="error"
            ),
            QualityCheck(
                name="invalid_dates",
                description="Check for invalid date formats",
                query="""SELECT COUNT(*) FROM predictions 
                        WHERE date IS NOT NULL AND date NOT LIKE '____-__-__'""",
                threshold=0,
                severity="error"
            ),
            QualityCheck(
                name="unknown_sentiment_labels",
                description="Check for unknown sentiment labels",
                query="""SELECT COUNT(*) FROM predictions 
                        WHERE pred_label NOT IN ('hawkish', 'neutral', 'dovish')""",
                threshold=0,
                severity="warning"
            ),
            
            # Consistency checks
            QualityCheck(
                name="orphaned_document_changes",
                description="Check for document changes without corresponding predictions",
                query="""SELECT COUNT(*) FROM document_changes dc 
                        LEFT JOIN predictions p1 ON dc.date_from = p1.date 
                        LEFT JOIN predictions p2 ON dc.date_to = p2.date 
                        WHERE p1.date IS NULL OR p2.date IS NULL""",
                threshold=0,
                severity="warning"
            ),
            QualityCheck(
                name="duplicate_fomc_dates",
                description="Check for duplicate FOMC dates",
                query="""SELECT COUNT(*) FROM (
                            SELECT date FROM fomc_dates GROUP BY date HAVING COUNT(*) > 1
                        )""",
                threshold=0,
                severity="error"
            ),
            
            # Distribution checks
            QualityCheck(
                name="low_confidence_predictions",
                description="Check percentage of low confidence predictions",
                query="SELECT COUNT(*) * 100.0 / (SELECT COUNT(*) FROM predictions) FROM predictions WHERE max_prob < 0.5",
                threshold=30.0,  # More than 30% low confidence is concerning
                severity="warning"
            ),
            QualityCheck(
                name="sentiment_distribution_skew",
                description="Check if sentiment distribution is extremely skewed",
                query="""SELECT MAX(cnt) * 100.0 / SUM(cnt) FROM (
                            SELECT COUNT(*) as cnt FROM predictions GROUP BY pred_label
                        )""",
                threshold=80.0,  # More than 80% of one sentiment is concerning
                severity="info"
            ),
            
            # Recency checks
            QualityCheck(
                name="stale_data",
                description="Check for lack of recent data updates",
                query="""SELECT julianday('now') - julianday(MAX(created_at)) 
                        FROM predictions""",
                threshold=30.0,  # More than 30 days without updates
                severity="warning"
            ),
            
            # Volume checks
            QualityCheck(
                name="prediction_volume",
                description="Check total prediction count",
                query="SELECT COUNT(*) FROM predictions",
                threshold=100,  # Less than 100 predictions total
                severity="info"
            ),
            QualityCheck(
                name="recent_prediction_volume",
                description="Check recent prediction volume (last 90 days)",
                query="""SELECT COUNT(*) FROM predictions 
                        WHERE date > date('now', '-90 days')""",
                threshold=10,  # Less than 10 recent predictions
                severity="warning"
            )
        ]
    
    def run_check(self, check: QualityCheck) -> QualityResult:
        """Run a single quality check"""
        try:
            result = self.db.execute_query(check.query)
            value = result[0][0] if result and result[0] else None
            
            if value is None:
                return QualityResult(
                    check_name=check.name,
                    status='error',
                    value=None,
                    threshold=check.threshold,
                    message="Query returned no results",
                    severity=check.severity,
                    timestamp=datetime.now()
                )
            
            # Determine pass/fail based on threshold
            status = 'pass'
            message = f"Check passed: {check.description}"
            
            if check.threshold is not None:
                if value > check.threshold:
                    status = 'fail'
                    message = f"Check failed: {check.description}. Value: {value}, Threshold: {check.threshold}"
            
            return QualityResult(
                check_name=check.name,
                status=status,
                value=value,
                threshold=check.threshold,
                message=message,
                severity=check.severity,
                timestamp=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Error running quality check '{check.name}': {e}")
            return QualityResult(
                check_name=check.name,
                status='error',
                value=None,
                threshold=check.threshold,
                message=f"Check error: {str(e)}",
                severity='error',
                timestamp=datetime.now()
            )
    
    def run_all_checks(self, enabled_only: bool = True) -> List[QualityResult]:
        """Run all quality checks"""
        logger.info("Running data quality checks...")
        
        checks_to_run = [c for c in self.checks if c.enabled] if enabled_only else self.checks
        results = []
        
        for check in checks_to_run:
            result = self.run_check(check)
            results.append(result)
            
            # Log based on severity and status
            if result.status == 'fail':
                if result.severity == 'critical':
                    logger.critical(result.message)
                elif result.severity == 'error':
                    logger.error(result.message)
                elif result.severity == 'warning':
                    logger.warning(result.message)
                else:
                    logger.info(result.message)
            elif result.status == 'error':
                logger.error(result.message)
        
        logger.info(f"Completed {len(results)} quality checks")
        return results
    
    def generate_report(self, results: List[QualityResult]) -> Dict[str, Any]:
        """Generate a comprehensive quality report"""
        total_checks = len(results)
        passed_checks = len([r for r in results if r.status == 'pass'])
        failed_checks = len([r for r in results if r.status == 'fail'])
        error_checks = len([r for r in results if r.status == 'error'])
        
        # Group by severity
        severity_summary = {}
        for severity in ['info', 'warning', 'error', 'critical']:
            severity_results = [r for r in results if r.severity == severity]
            severity_summary[severity] = {
                'total': len(severity_results),
                'passed': len([r for r in severity_results if r.status == 'pass']),
                'failed': len([r for r in severity_results if r.status == 'fail']),
                'errors': len([r for r in severity_results if r.status == 'error'])
            }
        
        # Failed checks details
        failed_details = [
            {
                'name': r.check_name,
                'value': r.value,
                'threshold': r.threshold,
                'message': r.message,
                'severity': r.severity
            }
            for r in results if r.status == 'fail'
        ]
        
        # Error checks details
        error_details = [
            {
                'name': r.check_name,
                'message': r.message,
                'severity': r.severity
            }
            for r in results if r.status == 'error'
        ]
        
        return {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_checks': total_checks,
                'passed': passed_checks,
                'failed': failed_checks,
                'errors': error_checks,
                'pass_rate': (passed_checks / total_checks * 100) if total_checks > 0 else 0
            },
            'severity_breakdown': severity_summary,
            'failed_checks': failed_details,
            'error_checks': error_details,
            'recommendations': self._generate_recommendations(results)
        }
    
    def _generate_recommendations(self, results: List[QualityResult]) -> List[str]:
        """Generate recommendations based on quality check results"""
        recommendations = []
        
        failed_results = [r for r in results if r.status == 'fail']
        
        for result in failed_results:
            if result.check_name == "null_prediction_dates":
                recommendations.append("Clean up predictions with missing dates - consider removing or imputing")
            elif result.check_name == "invalid_confidence_scores":
                recommendations.append("Investigate and fix predictions with invalid confidence scores")
            elif result.check_name == "low_confidence_predictions":
                recommendations.append("Review model performance - high percentage of low confidence predictions")
            elif result.check_name == "sentiment_distribution_skew":
                recommendations.append("Check if sentiment distribution reflects actual data or indicates bias")
            elif result.check_name == "stale_data":
                recommendations.append("Update data pipeline - no recent data updates detected")
            elif result.check_name == "orphaned_document_changes":
                recommendations.append("Clean up orphaned document changes or fix data consistency issues")
        
        if not recommendations:
            recommendations.append("Data quality looks good - no major issues detected")
        
        return recommendations
    
    def get_data_profile(self) -> Dict[str, Any]:
        """Generate a comprehensive data profile"""
        try:
            profile = {}
            
            with self.db.get_connection() as conn:
                # Basic statistics
                cursor = conn.cursor()
                
                # Predictions table profile
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_predictions,
                        COUNT(DISTINCT date) as unique_dates,
                        COUNT(DISTINCT document_type) as document_types,
                        MIN(date) as earliest_date,
                        MAX(date) as latest_date,
                        AVG(max_prob) as avg_confidence,
                        MIN(max_prob) as min_confidence,
                        MAX(max_prob) as max_confidence
                    FROM predictions
                """)
                pred_stats = dict(zip([desc[0] for desc in cursor.description], cursor.fetchone()))
                profile['predictions'] = pred_stats
                
                # Sentiment distribution
                cursor.execute("""
                    SELECT pred_label, COUNT(*) as count 
                    FROM predictions 
                    GROUP BY pred_label 
                    ORDER BY count DESC
                """)
                sentiment_dist = {row[0]: row[1] for row in cursor.fetchall()}
                profile['sentiment_distribution'] = sentiment_dist
                
                # Document type distribution
                cursor.execute("""
                    SELECT document_type, COUNT(*) as count 
                    FROM predictions 
                    WHERE document_type IS NOT NULL
                    GROUP BY document_type 
                    ORDER BY count DESC
                """)
                doc_type_dist = {row[0]: row[1] for row in cursor.fetchall()}
                profile['document_type_distribution'] = doc_type_dist
                
                # FOMC dates profile
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_meetings,
                        COUNT(CASE WHEN has_statement = 1 THEN 1 END) as with_statements,
                        COUNT(CASE WHEN has_press_conf = 1 THEN 1 END) as with_press_conf,
                        COUNT(CASE WHEN has_minutes = 1 THEN 1 END) as with_minutes,
                        MIN(date) as earliest_meeting,
                        MAX(date) as latest_meeting
                    FROM fomc_dates
                """)
                fomc_stats = dict(zip([desc[0] for desc in cursor.description], cursor.fetchone()))
                profile['fomc_meetings'] = fomc_stats
                
                # Document changes profile
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_changes,
                        COUNT(DISTINCT date_from) as unique_from_dates,
                        COUNT(DISTINCT date_to) as unique_to_dates,
                        AVG(similarity_score) as avg_similarity,
                        MIN(similarity_score) as min_similarity,
                        MAX(similarity_score) as max_similarity
                    FROM document_changes
                """)
                changes_stats = dict(zip([desc[0] for desc in cursor.description], cursor.fetchone()))
                profile['document_changes'] = changes_stats
                
            profile['generated_at'] = datetime.now().isoformat()
            return profile
            
        except Exception as e:
            logger.error(f"Error generating data profile: {e}")
            return {'error': str(e), 'generated_at': datetime.now().isoformat()}

def main():
    """Run data quality monitoring"""
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description='FOMC Data Quality Monitor')
    parser.add_argument('--output', '-o', help='Output file for report (JSON)')
    parser.add_argument('--profile', action='store_true', help='Generate data profile')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], 
                       default='INFO', help='Set logging level')
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    monitor = DataQualityMonitor()
    
    if args.profile:
        logger.info("Generating data profile...")
        profile = monitor.get_data_profile()
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(profile, f, indent=2, default=str)
            logger.info(f"Data profile saved to {args.output}")
        else:
            print(json.dumps(profile, indent=2, default=str))
    else:
        # Run quality checks
        results = monitor.run_all_checks()
        report = monitor.generate_report(results)
        
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"Quality report saved to {args.output}")
        else:
            print(json.dumps(report, indent=2, default=str))
        
        # Print summary
        summary = report['summary']
        print(f"\nData Quality Summary:")
        print(f"  Total checks: {summary['total_checks']}")
        print(f"  Passed: {summary['passed']} ({summary['pass_rate']:.1f}%)")
        print(f"  Failed: {summary['failed']}")
        print(f"  Errors: {summary['errors']}")
        
        if report['failed_checks']:
            print(f"\nFailed checks:")
            for check in report['failed_checks']:
                print(f"  - {check['name']}: {check['message']}")
        
        if report['recommendations']:
            print(f"\nRecommendations:")
            for rec in report['recommendations']:
                print(f"  - {rec}")

if __name__ == '__main__':
    main()
