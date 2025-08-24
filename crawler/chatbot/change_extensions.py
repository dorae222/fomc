# change_extensions.py
import os

# fomc_files 디렉토리의 절대 경로를 지정합니다.
# 사용자님의 경로: C:\Users\user\Desktop\github\fomc\crawler\fomc_files
directory_path = "C:/Users/user/Desktop/github/fomc/crawler/fomc_files"

for root, dirs, files in os.walk(directory_path):
    for filename in files:
        if filename.endswith(".markdown"):
            old_path = os.path.join(root, filename)
            new_filename = filename.replace(".markdown", ".md")
            new_path = os.path.join(root, new_filename)
            os.rename(old_path, new_path)
            print(f"'{old_path}' -> '{new_path}'로 변경 완료-")