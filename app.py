import os
import PyPDF2
import together
import gradio as gr
import time
import uuid
from google.cloud import storage

# --- 사전 설정 ---
# Render 환경 변수에서 API 키를 안전하게 불러옵니다.
api_key = os.getenv("TOGETHER_API_KEY")
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")

# --- [수정] Google Analytics 연동을 위한 설정 ---
GA_MEASUREMENT_ID = os.getenv("GA_MEASUREMENT_ID")

if not api_key:
    print("오류: TOGETHER_API_KEY 환경 변수가 설정되지 않았습니다.")
    api_key = "e5cba29e90c8626bc5fe5473fad9966c2f026ec1a0eab6a238f53c12f71a4ddd"

storage_client = None
if GCS_BUCKET_NAME:
    try:
        storage_client = storage.Client()
    except Exception as e:
        print(f"경고: Google Cloud Storage 클라이언트 초기화 실패. 파일이 저장되지 않습니다. 오류: {e}")
else:
    print("경고: GCS_BUCKET_NAME 환경 변수가 설정되지 않았습니다. 파일이 저장되지 않습니다.")

try:
    client = together.Together(api_key=api_key)
except Exception as e:
    print(f"오류: Together.ai 클라이언트 초기화에 실패했습니다. 에러: {e}")
    exit()

# --- [수정] Google Analytics 스크립트 생성 ---
ga_script_html = ""
if GA_MEASUREMENT_ID:
    ga_script_html = f"""
    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());
      gtag('config', '{GA_MEASUREMENT_ID}');
    </script>
    """
    print("Google Analytics 스크립트가 활성화되었습니다.")
else:
    print("경고: GA_MEASUREMENT_ID 환경 변수가 설정되지 않아 Google Analytics가 비활성화되었습니다.")


# (백엔드 함수 정의 부분은 기존과 동일하므로 생략)
def upload_to_gcs(...): ...
def extract_text_from_pdf(...): ...
def call_llm(...): ...
def generate_interview_questions(...): ...


# --- Gradio UI 구성 ---
css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Nanum+Gothic&display=swap');
* { font-family: 'Nanum Gothic', sans-serif !important; }
</style>
"""

# --- [수정] gr.Blocks에 head 파라미터 추가 ---
with gr.Blocks(theme=gr.themes.Soft(), head=ga_script_html) as demo:
    gr.HTML(css)
    gr.Markdown("## FastHire | 맞춤형 면접 솔루션")
    gr.Markdown("회사, 직무, 지원자의 PDF를 바탕으로 맞춤형 면접 질문을 생성합니다. 모든 정보를 입력하고 '생성하기' 버튼을 눌러주세요.")
    
    with gr.Row():
        company_name = gr.Textbox(label="1. 회사명", placeholder="예: 네이버웹툰")
        job_title = gr.Textbox(label="2. 채용 직무명", placeholder="예: 백엔드 개발자")
    
    with gr.Row():
        num_interviewers = gr.Slider(label="3. 면접관 수", minimum=1, maximum=5, value=2, step=1)
        questions_per_interviewer = gr.Slider(label="4. 면접관 별 질문 개수", minimum=1, maximum=5, value=3, step=1)
    
    pdf_file = gr.File(label="5. 자기소개서 및 포트폴리오 PDF 업로드", file_types=[".pdf"])
    generate_button = gr.Button("면접 질문 생성하기", variant="primary")
    output_textbox = gr.Textbox(label="생성 과정 및 결과", lines=20, interactive=False)
    
    generate_button.click(
        fn=generate_interview_questions,
        inputs=[company_name, job_title, pdf_file, num_interviewers, questions_per_interviewer],
        outputs=output_textbox
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get('PORT', 7860)))
