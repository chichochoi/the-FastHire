import os
import PyPDF2
import together
import gradio as gr
import time
import re # re 모듈은 불필요한 태그 제거를 위해 유지합니다.

# --- 사전 설정 ---
# Together.ai API 클라이언트 초기화

try:
    client = together.Together(api_key="e5cba29e90c8626bc5fe5473fad9966c2f026ec1a0eab6a238f53c12f71a4ddd")
except Exception as e:
    print(f"오류: Together.ai 클라이언트 초기화에 실패했습니다. API 키를 확인하세요. 에러: {e}")
    exit()

# --- 백엔드 함수 정의 ---

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

# ★★★★★ 이 함수가 수정되었습니다 ★★★★★
def generate_interview_questions(company_name, job_title, pdf_file, num_interviewers, questions_per_interviewer):
    """Gradio 인터페이스로부터 입력을 받아 면접 질문을 생성하는 메인 함수"""
    
    # --- 0단계: 입력 값 유효성 검사 및 초기화 ---
    if not all([company_name, job_title, pdf_file]):
        yield "회사명, 직무명, PDF 파일을 모두 입력해주세요."
        return

    output_log = ""

    # PDF 텍스트 추출
    pdf_path = pdf_file.name
    resume_text = extract_text_from_pdf(pdf_path)
    if resume_text.startswith("오류"):
        yield f"PDF 처리 실패: {resume_text}"
        return
    
    # --- 1단계: 회사 및 직무 정보 분석 ---
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

    # --- 2단계: 면접관 페르소나 생성 ---
    output_log += "➡️ 2단계: 가상 면접관 생성 중...\n"
    yield output_log
    
    prompt_personas = f"""
    {company_name}의 {job_title} 직무 면접관 {num_interviewers}명의 페르소나를 생성해 주세요. 각 페르소나는 직책, 경력, 성격, 주요 질문 스타일이 드러나도록 구체적으로 묘사해야 합니다.

    [페르소나 생성 예시]
    1. 박준형 이사 (40대 후반): 20년차 개발자 출신으로 현재 기술 총괄. 기술의 깊이와 문제 해결 과정을 집요하게 파고드는 스타일.
    2. 최유진 팀장 (30대 중반): 실무 팀의 리더. 협업 능력과 커뮤니케이션, 컬처핏을 중요하게 생각하며, 경험 기반의 질문을 주로 던짐.

    'thought'는 결과에 포함하지 마세요.
    """
    interviewer_personas = call_llm(prompt_personas)
    if interviewer_personas.startswith("오류"):
        yield output_log + f"❌ 2단계 실패: {interviewer_personas}"
        return
    output_log += "✅ 2단계 완료.\n\n"
    yield output_log
    time.sleep(1)

    # --- 3단계: 최종 면접 질문 생성 ---
    output_log += "➡️ 3단계: 최종 면접 질문 생성 중... 잠시만 기다려주세요.\n"
    yield output_log
    
    prompt_final = f"""
    당신은 지금부터 면접 질문 생성 AI입니다. 아래 주어진 [면접 정보]를 완벽하게 숙지하고, 최고의 면접 질문을 만들어야 합니다.

    [면접 정보]
    1. 면접 상황
    {context_info}

    2. 면접관 구성
    {interviewer_personas}

    3. 지원자 정보 (자기소개서/포트폴리오 원문)
    {resume_text}

    [수행 과제]
    위 [면접 정보]에 기반하여, 각 면접관의 역할과 스타일에 맞는 맞춤형 면접 질문을 면접관별로 {questions_per_interviewer}개씩 생성해 주세요.
    - (지원자 정보)의 활동과 관련된 질문을 반드시 1개 이상 포함해야 합니다.
    - 질문 뒤에는 "(의도: ...)" 형식으로 질문의 핵심 의도를 간략히 덧붙여 주세요.
    - 최종 결과물은 면접관별로 구분하여 깔끔하게 정리된 형태로만 출력해 주세요.
    - 'thought'는 결과에 포함하지 마세요.
    """
    final_questions_raw = call_llm(prompt_final)
    if final_questions_raw.startswith("오류"):
        yield output_log + f"❌ 최종 단계 실패: {final_questions_raw}"
        return
    
    
    # --- ★★★★★ 최종 결과물 구성 방식 변경 ★★★★★ ---
    # 기존: 질문만 출력
    # 변경: 면접관 페르소나 + 구분선 + 면접 질문 순서로 출력
    final_result = f"""### 🧑‍💻 면접관 프로필
    
{interviewer_personas}

---

### 📝 생성된 면접 질문

{final_questions_raw}
"""
    
    output_log += "\n✅ 모든 질문 생성이 완료되었습니다!\n\n---\n\n" + final_result
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

with gr.Blocks(theme=gr.themes.Soft()) as demo:
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
    demo.launch(share=True)
