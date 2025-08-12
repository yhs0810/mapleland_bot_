import os
import shutil
import getpass
import glob

def find_easyocr_models():
    """전체 컴퓨터에서 EasyOCR 모델 파일들을 찾기"""
    try:
        print("[거탐] EasyOCR 모델 파일 검색 중...")
        
        # 검색할 디렉토리들
        search_dirs = [
            os.path.expanduser("~"),  # 사용자 홈 디렉토리
            os.path.expanduser("~/.EasyOCR"),  # 일반적인 EasyOCR 경로
            os.path.expanduser("~/AppData/Local"),  # Windows AppData
            os.path.expanduser("~/AppData/Roaming"),  # Windows AppData
            "C:/Users",  # Windows 사용자 폴더
            "C:/ProgramData",  # Windows ProgramData
        ]
        
        # 찾을 모델 파일 패턴들
        model_patterns = [
            "**/craft_mlt_25k.pth",
            "**/korean_g2.pth",
            "**/*.pth",  # 모든 .pth 파일
        ]
        
        found_files = []
        
        for search_dir in search_dirs:
            if os.path.exists(search_dir):
                print(f"[거탐] 검색 중: {search_dir}")
                for pattern in model_patterns:
                    try:
                        pattern_path = os.path.join(search_dir, pattern)
                        files = glob.glob(pattern_path, recursive=True)
                        for file in files:
                            if os.path.isfile(file):
                                found_files.append(file)
                                print(f"  발견: {file}")
                    except Exception as e:
                        print(f"  검색 오류: {e}")
        
        # 중복 제거
        found_files = list(set(found_files))
        
        print(f"[거탐] 총 {len(found_files)}개 파일 발견")
        return found_files
        
    except Exception as e:
        print(f"[거탐] 모델 검색 오류: {e}")
        return []

def delete_easyocr_models():
    """EasyOCR 모델 파일들을 삭제"""
    try:
        # 먼저 모델 파일들을 찾기
        found_files = find_easyocr_models()
        
        if not found_files:
            print("[거탐] 삭제할 EasyOCR 모델 파일을 찾을 수 없습니다.")
            return False
        
        print(f"\n[거탐] 삭제할 파일 목록:")
        for i, file_path in enumerate(found_files, 1):
            print(f"  {i}. {file_path}")
        
        # 사용자 확인
        print(f"\n총 {len(found_files)}개 파일을 삭제하시겠습니까?")
        confirm = input("삭제하려면 'DELETE'를 입력하세요: ")
        
        if confirm != "DELETE":
            print("삭제가 취소되었습니다.")
            return False
        
        # 파일 삭제
        deleted_count = 0
        for file_path in found_files:
            try:
                os.remove(file_path)
                print(f"[거탐] 삭제됨: {os.path.basename(file_path)}")
                deleted_count += 1
            except Exception as e:
                print(f"[거탐] 삭제 실패: {os.path.basename(file_path)} - {e}")
        
        # 빈 디렉토리들 정리
        cleaned_dirs = []
        for file_path in found_files:
            dir_path = os.path.dirname(file_path)
            if dir_path not in cleaned_dirs:
                try:
                    if os.path.exists(dir_path) and not os.listdir(dir_path):
                        os.rmdir(dir_path)
                        cleaned_dirs.append(dir_path)
                        print(f"[거탐] 빈 디렉토리 삭제: {dir_path}")
                except:
                    pass
        
        print(f"[거탐] 총 {deleted_count}개 파일 삭제 완료!")
        return True
        
    except Exception as e:
        print(f"[거탐] 모델 삭제 오류: {e}")
        return False

def check_models_exist():
    """모델 파일들이 존재하는지 확인"""
    return find_easyocr_models()

if __name__ == "__main__":
    print("=" * 50)
    print("거탐 모델 삭제 프로그램")
    print("=" * 50)
    
    # 비밀번호 입력 (화면에 표시되지 않음)
    password = getpass.getpass("비밀번호를 입력하세요: ")
    
    if password == "a10233":
        print("인증 성공!")
        
        # 현재 모델 파일 확인
        existing_files = check_models_exist()
        
        if existing_files:
            print(f"\n발견된 모델 파일: {len(existing_files)}개")
            for i, file_path in enumerate(existing_files, 1):
                print(f"  {i}. {file_path}")
            
            print("\n모델 파일들을 삭제하시겠습니까?")
            confirm = input("삭제하려면 'DELETE'를 입력하세요: ")
            
            if confirm == "DELETE":
                print("-" * 50)
                success = delete_easyocr_models()
                if success:
                    print("모델 삭제 완료!")
                else:
                    print("모델 삭제 실패!")
            else:
                print("삭제가 취소되었습니다.")
        else:
            print("삭제할 EasyOCR 모델 파일이 없습니다.")
    else:
        print("비밀번호가 올바르지 않습니다!")
        print("프로그램을 종료합니다.")
    
    input("\n엔터를 누르면 종료됩니다...") 