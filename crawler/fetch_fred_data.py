#!/usr/bin/env python3
"""
Fetches the 2-year US Treasury yield data from the FRED database.
"""

import pandas_datareader.data as web
from datetime import datetime

import os

def fetch_2y_treasury_yield(start_date, end_date):
    """
    Fetches and displays the 2-year Treasury yield from FRED.

    Args:
        start_date (datetime): The start date for the data.
        end_date (datetime): The end date for the data.
    """
    print(f"Fetching 2-Year Treasury Yield (DGS2) from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}...")
    try:
        dgs2 = web.DataReader('DGS2', 'fred', start_date, end_date)
        print("데이터를 성공적으로 불러왔습니다.")
        print("\n최근 5개 데이터:")
        print(dgs2.tail())

        # --- Robust Path Handling ---
        # Get the absolute path of the directory containing this script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Go up one level to the project root
        project_root = os.path.dirname(script_dir)
        # Construct the path to the output directory
        output_dir = os.path.join(project_root, 'output')

        # Ensure the output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Define the output file path and save the CSV
        output_path = os.path.join(output_dir, 'DGS2.csv')
        dgs2.to_csv(output_path)
        print(f"\nData saved to {output_path}")

        return dgs2

    except Exception as e:
        print(f"데이터를 불러오는 중 오류가 발생했습니다: {e}")
        return None

if __name__ == '__main__':
    # 데이터 조회 기간 설정
    start = datetime(1994, 1, 1)
    end = datetime.now()
    
    fetch_2y_treasury_yield(start, end)
