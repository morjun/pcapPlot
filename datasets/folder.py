import os
import re
import shutil

# 정규 표현식으로 l#d#d# 형식을 추출
pattern = re.compile(r'l(\d+(\.\d+)?)b(\d+)d(\d+)')

# 현재 작업 디렉토리
current_directory = os.getcwd()

# 파일을 탐색하고 이동하는 함수
def move_files():
    for file_name in os.listdir(current_directory):
        match = pattern.match(file_name)
        if match and os.path.isfile(file_name):
            # 그룹화된 숫자를 가져와 폴더 이름 생성 (예: l1b2d3)
            folder_name = f"l{match.group(1)}b{match.group(3)}d{match.group(4)}"

            # 1,2,3일 때에는 l정수 소수 포함, b(l의 소수부분), d(b의 정수부분)로 폴더가 생성되었고
            # 옮겨지는 파일은 l이랑 b가 일치하면 d 값이 달라도 똑같은 폴더로 옮겨졌었다
            # 폴더 이름이 겹치기 때문에 같은 폴더로 옮겨졌던 것일 뿐이고, 정규 표현식 자체에는 문제 X

            destination_folder = os.path.join(current_directory, folder_name)
            
            # 폴더가 없으면 생성
            if not os.path.exists(destination_folder):
                os.makedirs(destination_folder)
            
            # 파일 이동
            source_path = os.path.join(current_directory, file_name)
            destination_path = os.path.join(destination_folder, file_name)
            shutil.move(source_path, destination_path)
            print(f"Moved {file_name} to {destination_folder}")

if __name__ == "__main__":
    move_files()
