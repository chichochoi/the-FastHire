import os
import PyPDF2
import together
import gradio as gr
import time
import uuid # 고유 파일명 생성을 위해 추가
from google.cloud import storage # GCS 연동을 위해 추가

# --- 사전 설정 ---
# Render 환경 변수에서 API 키를 안전하게 불러옵니다.
api_key = os.getenv("TOGETHER_API_KEY")
# GCS 버킷 이름을 환경 변수에서 불러옵니다.
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
# --- [수정] Google Analytics 연동을 위한 설정 ---
GA_MEASUREMENT_ID = os.getenv("GA_MEASUREMENT_ID")

if not api_key:
    print("오류: TOGETHER_API_KEY 환경 변수가 설정되지 않았습니다.")
    # 로컬 테스트용
    api_key = "e5cba29e90c8626bc5fe5473fad9966c2f026ec1a0eab6a238f53c12f71a4ddd"

# GCS 클라이언트는 한번만 초기화하는 것이 효율적입니다.
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

# --- 백엔드 함수 정의 ---

def upload_to_gcs(bucket_name: str, source_file_path: str, destination_blob_name: str):
    """로컬 파일을 Google Cloud Storage 버킷에 업로드합니다."""
    if not storage_client:
        print("GCS 클라이언트가 초기화되지 않아 업로드를 건너뜁니다.")
        return

    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination_blob_name)
        blob.upload_from_filename(source_file_path)
        print(f"파일 '{source_file_path}'를(을) 버킷 '{bucket_name}'에 '{destination_blob_name}'(으)로 업로드했습니다.")
    except Exception as e:
        print(f"GCS 업로드 중 오류 발생: {e}")


def extract_text_from_pdf(pdf_path: str) -> str:
    """PDF 파일에서 텍스트를 추출합니다."""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = "".join(page.extract_text() or "" for page in reader.pages)
            return text
    except FileNotFoundError:
        return f"오류: PDF 파일을 찾을 수 없습니다. 경로: {pdf_path}"
    except Exception as e:
        return f"PDF 처리 중 오류 발생: {e}"

def call_llm(prompt: str, model: str = "lgai/exaone-deep-32b") -> str:
    """Together.ai API를 호출하고, 실패 시 빈 문자열 대신 오류 메시지를 반환합니다."""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        if response.choices and response.choices[0].message.content:
            return response.choices[0].message.content.strip()
        else:
            print("Warning: LLM returned an empty response.")
            return "오류: LLM으로부터 비어 있는 응답을 받았습니다."

    except Exception as e:
        print(f"LLM API 호출 중 오류 발생: {e}")
        return f"오류: LLM API 호출에 실패했습니다. ({e})"

# --- [수정된 함수] ---
def generate_interview_questions(company_name, job_title, pdf_file, num_interviewers, questions_per_interviewer):
    """Gradio 인터페이스로부터 입력을 받아 면접 질문을 생성하고 요약하는 메인 함수"""

    if not all([company_name, job_title, pdf_file]):
        yield "회사명, 직무명, PDF 파일을 모두 입력해주세요."
        return

    # --- GCS 업로드 로직 추가 ---
    pdf_path = pdf_file.name # Gradio가 임시 저장한 파일 경로

    if GCS_BUCKET_NAME:
        # 파일명이 겹치지 않도록 고유한 이름 생성 (예: 20250731-140000-uuid-원본파일이름.pdf)
        original_filename = os.path.basename(pdf_file.name)
        unique_id = str(uuid.uuid4().hex)[:8]
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        destination_blob_name = f"{timestamp}-{unique_id}-{original_filename}"

        upload_to_gcs(GCS_BUCKET_NAME, pdf_path, destination_blob_name)
    # --- GCS 업로드 로직 끝 ---

    output_log = ""
    resume_text = extract_text_from_pdf(pdf_path)
    if resume_text.startswith("오류"):
        yield f"PDF 처리 실패: {resume_text}"
        return

    output_log += "➡️ 1단계: 회사 및 직무 정보 분석 중...\n"
    yield output_log

    prompt_context = f"""
    {company_name}의 {job_title} 채용에 대한 [면접 상황]을 아래 양식에 맞게 사실에 기반하여 구체적으로 작성해 주세요.

    [면접 상황]
    - 회사명: {company_name}
    - 회사 소개: (회사의 비전, 문화, 주력 사업 등을 간략히 서술)
    - 채용 직무: {job_title}
    - 핵심 요구 역량: (해당 직무에 필요한 기술 스택, 소프트 스킬 등을 3-4가지 서술)
    """
    context_info = call_llm(prompt_context)
    if context_info.startswith("오류"):
        yield output_log + f"❌ 1단계 실패: {context_info}"
        return
    output_log += "✅ 1단계 완료.\n\n"
    yield output_log
    time.sleep(1)

    output_log += "➡️ 2단계: 다양한 면접관과 접촉 중...\n"
    yield output_log

    prompt_personas = f"""
    {company_name}의 {job_title} 직무 면접관 {num_interviewers}명의 페르소나를 생성해 주세요. 각 페르소나는 직책, 경력, 성격, 주요 질문 스타일이 드러나도록 구체적으로 묘사해야 합니다.

    [페르소나 생성 예시]
    1. 박준형 이사 (40대 후반): 20년차 개발자 출신으로 현재 기술 총괄. 기술의 깊이와 문제 해결 과정을 집요하게 파고드는 스타일.
    2. 최유진 팀장 (30대 중반): 실무 팀의 리더. 협업 능력과 커뮤니케이션, 컬처핏을 중요하게 생각하며, 경험 기반의 질문을 주로 던짐.
    """
    interviewer_personas = call_llm(prompt_personas)
    if interviewer_personas.startswith("오류"):
        yield output_log + f"❌ 2단계 실패: {interviewer_personas}"
        return
    output_log += "✅ 2단계 완료.\n\n"
    yield output_log
    time.sleep(1)

    output_log += "➡️ 3단계: 최종 면접 질문 생성 중... 잠시만 기다려주세요.\n"
    yield output_log

도

{summarized_result}
"""

    output_log += "✅ 모든 작업이 완료되었습니다!\n\n---\n\n" + final_result
    yield output_log


# --- Gradio UI 구성 ---
css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Nanum+Gothic&display=swap');

* {
    font-family: 'Nanum Gothic', sans-serif !important;
}
</style>
"""

# 아이콘 파일 경로 (예: 'fav.png', 'icon.ico')
# 다운로드한 아이콘 파일을 코드와 같은 디렉토리에 두거나 정확한 경로를 입력하세요.
favicon_path = "logo2.jpg" 

# --- [수정] gr.Blocks에 head 파라미터 추가 ---
with gr.Blocks(title="FastHire", theme=gr.themes.Soft(), head=ga_script_html) as demo:
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
    # --- [사용자 요청] 개인정보 보호 문구 추가 ---
    gr.Markdown(
        "<div style='text-align: center; color: gray; font-size: 0.8em; margin-top: 10px; margin-bottom: 10px;'>"
        "*고객의 개인정보는 서비스 제공 목적 달성 후 안전하게 삭제됩니다*"
        "</div>"
    )

    generate_button = gr.Button("면접 질문 생성하기", variant="primary")
    output_textbox = gr.Textbox(label="생성 과정 및 결과", lines=20, interactive=False, show_copy_button=True)
    
    generate_button.click(
        fn=generate_interview_questions,
        inputs=[company_name, job_title, pdf_file, num_interviewers, questions_per_interviewer],
        outputs=output_textbox
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", favicon_path=favicon_path,server_port=int(os.environ.get('PORT', 7860)))
