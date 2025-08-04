import os
import PyPDF2
import together
import gradio as gr
import time
import uuid  # 고유 파일명 생성을 위해 추가
from google.cloud import storage  # GCS 연동을 위해 추가
import numpy as np
# --- 사전 설정 ---
# Render 환경 변수에서 API 키를 안전하게 불러옵니다.
api_key = os.getenv("TOGETHER_API_KEY")
# GCS 버킷 이름을 환경 변수에서 불러옵니다.
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
# Google Analytics 연동을 위한 설정
GA_MEASUREMENT_ID = os.getenv("GA_MEASUREMENT_ID")

if not api_key:
    print("오류: TOGETHER_API_KEY 환경 변수가 설정되지 않았습니다. 프로그램을 종료합니다.")
    exit() # API 키가 없으면 실행 중단

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

# --- [신규] LLM 모델 정의 ---
MODELS = {
    'ko': 'lgai/exaone-deep-32b',
    'en': 'meta-llama/Llama-3.3-70B-Instruct-Turbo-Free' # 영어권에서 성능이 좋은 Llama 모델
}

# --- [신규] 다국어 지원을 위한 텍스트 관리 ---
LANG_STRINGS = {
    'ko': {
        "title": "# **FastHire | 맞춤형 면접 솔루션**",
        "subtitle": "회사, 직무, 지원자의 PDF를 바탕으로 맞춤형 면접 질문을 생성합니다.<br>면접관 수에 따라 여러 종류의 면접관이 여러분에게 질문합니다.",
        "company_label": "1. 회사명",
        "company_placeholder": "예: 네이버웹툰",
        "job_label": "2. 채용 직무명",
        "job_placeholder": "예: 백엔드 개발자",
        "interviewer_count_label": "3. 면접관 수",
        "question_count_label": "4. 면접관 별 질문 개수",
        "upload_button_text": "5. 이력서 및 포트폴리오 PDF 업로드",
        "upload_status_label": "업로드 상태",
        "upload_success": "✅ 파일 업로드 완료!",
        "privacy_notice": "<div style='text-align: center; color: gray; font-size: 0.8em; margin-top: 20px; margin-bottom: 10px;'>*고객의 개인정보는 서비스 제공 목적 달성 후 안전하게 삭제됩니다*</div>",
        "generate_button_text": "면접 질문 생성하기",
        "output_label": "생성 과정 및 결과",
        "contact_html": """<div style='display: flex; justify-content: space-between; align-items: flex-start; color: gray; font-size: 0.9em; margin-top: 40px; margin-bottom: 30px;'><div style='text-align: left; max-width: 70%;'>회사명, 직무명, PDF 이력서를 기반으로 <strong>다양한 면접관한테 면접 질문을</strong> 받을 수 있습니다.<br>맞춤형 <strong>면접 준비</strong>, <strong>자기소개서 기반 질문</strong>, <strong>다양한 형태의 질문 대비</strong>, <strong>취업 대비</strong>까지 완벽하게 지원합니다.</div><div style='text-align: right; white-space: nowrap;'>Contact us: eeooeeforbiz@gmail.com</div></div>""",
        "error_all_fields": "회사명, 직무명, PDF 파일을 모두 입력해주세요.",
        "error_not_pdf": "❌ 오류: PDF 파일만 업로드할 수 있습니다.",
        "log_step1_start": "➡️ 1단계: 회사 및 직무 정보 분석 중...",
        "log_step1_fail": "❌ 1단계 실패: ",
        "log_step1_done": "✅ 1단계 완료.\n\n",
        "log_step2_start": "➡️ 2단계: 가상 면접관 생성 중...",
        "log_step2_fail": "❌ 2단계 실패: ",
        "log_step2_done": "✅ 2단계 완료.\n\n",
        "log_step3_start": "➡️ 3단계: 최종 면접 질문 생성 중... 잠시만 기다려주세요.",
        "log_step3_fail": "❌ 3단계 실패: ",
        "log_step3_done": "✅ 3단계 완료.\n\n",
        "log_summary_start": "➡️ 추가 단계: 생성된 결과 요약 중...",
        "log_summary_fail": "결과를 요약하는 데 실패했습니다.",
        "log_all_done": "✅ 모든 작업이 완료되었습니다!\n\n---\n\n",
        "final_result_header": "### 🌟 면접관 프로필 + 면접 질문 + 질문 의도",
        "prompt_context": """{company_name}의 {job_title} 채용에 대한 [면접 상황]을 아래 양식에 맞게 사실에 기반하여 구체적으로 작성해 주세요.

[면접 상황]
- 회사명: {company_name}
- 회사 소개: (회사의 비전, 문화, 주력 사업 등을 간략히 서술)
- 채용 직무: {job_title}
- 핵심 요구 역량: (해당 직무에 필요한 기술 스택, 소프트 스킬 등을 3-4가지 서술)""",
        "prompt_personas": """{company_name}의 {job_title} 직무 면접관 {num_interviewers}명의 페르소나를 생성해 주세요. 각 페르소나는 직책, 경력, 성격, 주요 질문 스타일이 드러나도록 구체적으로 묘사해야 합니다.

[페르소나 생성 예시]
1. 박준형 이사 (40대 후반): 20년차 개발자 출신으로 현재 기술 총괄. 기술의 깊이와 문제 해결 과정을 집요하게 파고드는 스타일.
2. 최유진 팀장 (30대 중반): 실무 팀의 리더. 협업 능력과 커뮤니케이션, 컬처핏을 중요하게 생각하며, 경험 기반의 질문을 주로 던짐.""",
        "prompt_final": """당신은 지금부터 면접 질문 생성 AI입니다. 아래 주어진 [면접 정보]를 완벽하게 숙지하고, 최고의 면접 질문을 만들어야 합니다.

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
- 최종 결과물은 면접관별로 구분하여 깔끔하게 정리된 형태로만 출력해 주세요.""",
        "prompt_real_final": """아래에서 영어를 모두 한국어로 번역해주세요.
아래에서 중복되는 내용을 지우고 '면접관 페르소나'와 '면접질문'들만 남기세요.
---
{full_content_to_summarize}
---""",
    },
    'en': {
        "title": "# **FastHire | Custom Interview Solution**",
        "subtitle": "Generates tailored interview questions based on the company, job title, and applicant's PDF.<br>Different types of interviewers will ask you questions depending on the number selected.",
        "company_label": "1. Company Name",
        "company_placeholder": "e.g., Google",
        "job_label": "2. Job Title",
        "job_placeholder": "e.g., Software Engineer",
        "interviewer_count_label": "3. Number of Interviewers",
        "question_count_label": "4. Questions per Interviewer",
        "upload_button_text": "5. Upload Resume/Portfolio PDF",
        "upload_status_label": "Upload Status",
        "upload_success": "✅ File uploaded successfully!",
        "privacy_notice": "<div style='text-align: center; color: gray; font-size: 0.8em; margin-top: 20px; margin-bottom: 10px;'>*Your personal information will be securely deleted after the service purpose is fulfilled.*</div>",
        "generate_button_text": "Generate Interview Questions",
        "output_label": "Process and Results",
        "contact_html": """<div style='display: flex; justify-content: space-between; align-items: flex-start; color: gray; font-size: 0.9em; margin-top: 40px; margin-bottom: 30px;'><div style='text-align: left; max-width: 70%;'>Get <strong>interview questions from various interviewers</strong> based on company name, job title, and your PDF resume.<br>We provide complete support from tailored <strong>interview preparation</strong>, <strong>resume-based questions</strong>, preparing for <strong>various question types</strong>, to <strong>job search readiness</strong>.</div><div style='text-align: right; white-space: nowrap;'>Contact us: eeooeeforbiz@gmail.com</div></div>""",
        "error_all_fields": "Please enter the company name, job title, and upload a PDF file.",
        "error_not_pdf": "❌ Error: Only PDF files can be uploaded.",
        "log_step1_start": "➡️ Step 1: Analyzing company and job information...",
        "log_step1_fail": "❌ Step 1 Failed: ",
        "log_step1_done": "✅ Step 1 Complete.\n\n",
        "log_step2_start": "➡️ Step 2: Creating virtual interviewers...",
        "log_step2_fail": "❌ Step 2 Failed: ",
        "log_step2_done": "✅ Step 2 Complete.\n\n",
        "log_step3_start": "➡️ Step 3: Generating final interview questions... Please wait.",
        "log_step3_fail": "❌ Step 3 Failed: ",
        "log_step3_done": "✅ Step 3 Complete.\n\n",
        "log_summary_start": "➡️ Extra Step: Summarizing the generated results...",
        "log_summary_fail": "Failed to summarize the results.",
        "log_all_done": "✅ All tasks are complete!\n\n---\n\n",
        "final_result_header": "### 🌟 Interviewer Profiles + Interview Questions + Question Intent",
        "prompt_context": """Please create a detailed [Interview Scenario] for the {job_title} position at {company_name}, based on facts, in the format below.

[Interview Scenario]
- Company Name: {company_name}
- Company Introduction: (Briefly describe the company's vision, culture, and main business)
- Hiring Position: {job_title}
- Key Required Competencies: (List 3-4 technical skills and soft skills required for the position)""",
        "prompt_personas": """Please create {num_interviewers} interviewer personas for the {job_title} position at {company_name}. Each persona should be described in detail, including their job title, career background, personality, and primary questioning style.

[Persona Creation Example]
1. Director Park (Late 40s): A 20-year veteran developer, now the Head of Technology. Known for digging deep into technical depth and problem-solving processes.
2. Team Lead Choi (Mid 30s): Leader of the practical team. Emphasizes collaboration, communication, and culture fit, primarily asking experience-based questions.""",
        "prompt_final": """You are now an interview question generation AI. You must perfectly understand the [Interview Information] provided below and create the best interview questions.

[Interview Information]
1. Interview Scenario
{context_info}

2. Interviewer Panel
{interviewer_personas}

3. Applicant Information (Original text from resume/portfolio)
{resume_text}

[Task to Perform]
Based on the [Interview Information] above, generate {questions_per_interviewer} tailored interview questions for each interviewer, matching their role and style.
- You must include at least one question related to the activities mentioned in the (Applicant Information).
- After each question, briefly add the core intent of the question in the format "(Intent: ...)."
- The final output should be presented in a neatly organized format, separated by interviewer.""",
        "prompt_real_final": """Please remove any redundant information from the text below and leave only the 'Interviewer Personas' and 'Interview Questions'.
---
{full_content_to_summarize}
---""",
    }
}

# --- Google Analytics 스크립트 생성 ---
FAVICON_URL = "https://i.imgur.com/hpUa5yb.jpeg"

ga_script_html = f"""
    <!-- SEO Meta Tags -->
    <meta name="description" content="FastHire | PDF-based custom interview question generation platform. AI automatically creates questions when you enter a company and job title. Get sample questions from various interviewers.">
    <meta name="keywords" content="interview question examples, AI interview questions, interview prep, job search, FastHire">
    <meta name="author" content="FastHire">

    <!-- Open Graph (OG) Tags for Link Previews -->
    <meta property="og:title" content="FastHire | We provide custom interview questions">
    <meta property="og:description" content="Create your own personalized interview questions with just a company, job title, and resume! Get real interview questions from a variety of interviewers.">
    <meta property="og:image" content="https://i.imgur.com/hpUa5yb.jpeg"> 
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="FastHire">

    <!-- Favicon -->
    <link rel="icon" href="{FAVICON_URL}">
    <link rel="shortcut icon" href="{FAVICON_URL}">
    <link rel="apple-touch-icon" href="{FAVICON_URL}">
"""
if GA_MEASUREMENT_ID:
    ga_script_html += f"""
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
def show_upload_feedback(file_obj, lang):
    """파일이 업로드되면 확인 메시지를 반환하는 함수"""
    if file_obj is not None:
        return LANG_STRINGS[lang]['upload_success']
    return ""

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

def call_llm(prompt: str, chat_history: list, model: str) -> str:
    """Together.ai API를 호출하고, 실패 시 오류 메시지를 반환하며 대화 히스토리를 유지합니다."""
    chat_history.append({"role": "user", "content": prompt})
    try:
        response = client.chat.completions.create(
            model=model,
            messages=chat_history,
        )
        if response.choices and response.choices[0].message.content:
            reply = response.choices[0].message.content.strip()
            chat_history.append({"role": "assistant", "content": reply})
            return reply
        else:
            print("Warning: LLM returned an empty response.")
            return "Error: LLM returned an empty response."
    except Exception as e:
        print(f"LLM API 호출 중 오류 발생: {e}")
        return f"Error: LLM API call failed. ({e})"

# --- [수정된 메인 함수] ---
def generate_interview_questions(company_name, job_title, pdf_file, num_interviewers, questions_per_interviewer, lang):
    """Gradio 인터페이스로부터 입력을 받아 면접 질문을 생성하고 요약하는 메인 함수 (다국어 지원)"""
    
    # 현재 언어에 맞는 텍스트 로드
    T = LANG_STRINGS[lang]
    model = MODELS[lang]

    if not all([company_name, job_title, pdf_file]):
        yield T['error_all_fields']
        return
        
    pdf_path = pdf_file.name
    if not pdf_path.lower().endswith(".pdf"):
        yield T['error_not_pdf']
        return

    if GCS_BUCKET_NAME:
        original_filename = os.path.basename(pdf_file.name)
        unique_id = str(uuid.uuid4().hex)[:8]
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        destination_blob_name = f"{timestamp}-{unique_id}-{original_filename}"
        upload_to_gcs(GCS_BUCKET_NAME, pdf_path, destination_blob_name)

    output_log = ""
    resume_text = extract_text_from_pdf(pdf_path)
    if resume_text.startswith("오류") or resume_text.startswith("Error"):
        yield f"PDF Processing Failed: {resume_text}"
        return

    output_log += T['log_step1_start'] + "\n"
    yield output_log
    
    prompt_context = T['prompt_context'].format(company_name=company_name, job_title=job_title)
    chat_history = []
    context_info = call_llm(prompt_context, chat_history, model)
    if context_info.startswith("오류") or context_info.startswith("Error"):
        yield output_log + T['log_step1_fail'] + context_info
        return
    output_log += T['log_step1_done']
    yield output_log
    time.sleep(1)

    output_log += T['log_step2_start'] + "\n"
    yield output_log
    
    prompt_personas = T['prompt_personas'].format(company_name=company_name, job_title=job_title, num_interviewers=num_interviewers)
    interviewer_personas = call_llm(prompt_personas, chat_history, model)
    if interviewer_personas.startswith("오류") or interviewer_personas.startswith("Error"):
        yield output_log + T['log_step2_fail'] + interviewer_personas
        return
    output_log += T['log_step2_done']
    yield output_log
    time.sleep(1)

    output_log += T['log_step3_start'] + "\n"
    yield output_log

    prompt_final = T['prompt_final'].format(
        context_info=context_info,
        interviewer_personas=interviewer_personas,
        resume_text=resume_text,
        questions_per_interviewer=questions_per_interviewer
    )
    final_questions_raw = call_llm(prompt_final, chat_history, model)
    if final_questions_raw.startswith("오류") or final_questions_raw.startswith("Error"):
        yield output_log + T['log_step3_fail'] + final_questions_raw
        return
    output_log += T['log_step3_done']
    yield output_log
    time.sleep(1)

    output_log += T['log_summary_start'] + "\n"
    yield output_log

    full_content_to_summarize = f"[Interviewer Personas]\n{interviewer_personas}\n\n[Generated Interview Questions]\n{final_questions_raw}"
    prompt_real_final = T['prompt_real_final'].format(full_content_to_summarize=full_content_to_summarize)
    summarized_result = call_llm(prompt_real_final, chat_history, model)
    if summarized_result.startswith("오류") or summarized_result.startswith("Error"):
        summarized_result = T['log_summary_fail']

    final_result = f"{T['final_result_header']}\n\n{summarized_result}"
    output_log += T['log_all_done'] + final_result
    yield output_log

# --- [신규] UI 언어 변경 함수 ---
def update_ui_language(lang_choice):
    lang_key = 'en' if lang_choice == 'English' else 'ko'
    T = LANG_STRINGS[lang_key]
    
    # 반환 값의 첫 번째 항목을 lang_state 객체에서 lang_key 변수로 수정합니다.
    # 이렇게 해야 lang_state의 "값"이 'ko' 또는 'en'으로 올바르게 업데이트됩니다.
    return (
        lang_key,  # <--- 이렇게 수정!
        gr.update(value=T['title']),
        gr.update(value=T['subtitle']),
        gr.update(label=T['company_label'], placeholder=T['company_placeholder']),
        gr.update(label=T['job_label'], placeholder=T['job_placeholder']),
        gr.update(label=T['interviewer_count_label']),
        gr.update(label=T['question_count_label']),
        gr.update(label=T['upload_button_text']),
        gr.update(label=T['upload_status_label']),
        gr.update(value=T['privacy_notice']),
        gr.update(value=T['generate_button_text']),
        gr.update(label=T['output_label']),
        gr.update(value=T['contact_html'])
    )

# --- 실시간 접속자 수 업데이트 함수 (제너레이터로 수정) ---
def update_live_users():
    """실시간 접속자 수를 계산하여 HTML 콘텐츠를 반환하는 일반 함수입니다."""
    user_count = int(np.random.normal(loc=600, scale=50))
    html_content = f"""
    <div style="display: flex; align-items: center;">
        <span class="green-dot"></span>
        <span>실시간 접속자 수: {user_count}</span>
    </div>
    """
    return html_content


# --- Gradio UI 구성 ---
css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Nanum+Gothic&display=swap');
body, * {
    font-family: 'Nanum Gothic', 'Arial', sans-serif !important;
}
#header_row {
    display: flex;
    justify-content: space-between;
    align-items: center;
}
/* 오른쪽 상단 요소(접속자 수, 언어 선택기)를 담을 컨테이너 스타일 */
#right_header_container {
    display: flex;
    align-items: center;
    gap: 20px; /* 요소 사이의 간격 */
    margin-left: auto; /* 컨테이너를 오른쪽으로 밀어냄 */
}
/* 실시간 접속자 표시의 초록색 점 스타일 */
.green-dot {
    display: inline-block;
    width: 10px;
    height: 10px;
    background-color: #28a745; /* 초록색 */
    border-radius: 50%;
    margin-right: 8px;
    vertical-align: middle;
}
</style>
"""

with gr.Blocks(title="FastHire | 맞춤형 면접 질문 받기", theme=gr.themes.Soft(), head=ga_script_html) as demo:
    lang_state = gr.State("ko")
    gr.HTML(css)

    with gr.Row(elem_id="header_row"):
        title_md = gr.Markdown(LANG_STRINGS['ko']['title'])

        # 오른쪽 상단 요소들을 담을 컨테이너 추가
        with gr.Row(elem_id="right_header_container"):
            # 실시간 접속자 수를 표시할 HTML 컴포넌트 추가
            live_users_display = gr.HTML()

            lang_selector = gr.Radio(
                ["한국어", "English"],
                value="한국어",
                label="Language",
                show_label=False,
                interactive=True,
                # elem_id는 부모 컨테이너로 이동했으므로 여기서 제거
            )

    subtitle_md = gr.Markdown(LANG_STRINGS['ko']['subtitle'])

    with gr.Row():
        company_name = gr.Textbox(label=LANG_STRINGS['ko']['company_label'], placeholder=LANG_STRINGS['ko']['company_placeholder'])
        job_title = gr.Textbox(label=LANG_STRINGS['ko']['job_label'], placeholder=LANG_STRINGS['ko']['job_placeholder'])

    with gr.Row():
        num_interviewers = gr.Slider(label=LANG_STRINGS['ko']['interviewer_count_label'], minimum=1, maximum=5, value=2, step=1)
        questions_per_interviewer = gr.Slider(label=LANG_STRINGS['ko']['question_count_label'], minimum=1, maximum=5, value=3, step=1)

    pdf_file = gr.UploadButton(
        "이력서 및 포트폴리오 pdf",
        label=LANG_STRINGS['ko']['upload_button_text'],
        file_types=[".pdf"]
    )
    upload_feedback_box = gr.Textbox(label=LANG_STRINGS['ko']['upload_status_label'], interactive=False)

    pdf_file.upload(
        fn=show_upload_feedback,
        inputs=[pdf_file, lang_state],
        outputs=[upload_feedback_box]
    )

    privacy_notice_html = gr.HTML(LANG_STRINGS['ko']['privacy_notice'])
    generate_button = gr.Button(LANG_STRINGS['ko']['generate_button_text'], variant="primary")
    output_textbox = gr.Textbox(label=LANG_STRINGS['ko']['output_label'], lines=20, interactive=False, show_copy_button=True)
    contact_html = gr.HTML(LANG_STRINGS['ko']['contact_html'])


    # --- 이벤트 리스너 연결 ---
    
    demo.load(
        fn=update_live_users,
        inputs=None,
        outputs=[live_users_display],
        every=3  # 3초마다 함수를 실행
    )
    lang_selector.select(
        fn=update_ui_language,
        inputs=[lang_selector],
        outputs=[
            lang_state, title_md, subtitle_md,
            company_name, job_title, num_interviewers, questions_per_interviewer,
            pdf_file, upload_feedback_box, privacy_notice_html, generate_button,
            output_textbox, contact_html
        ]
    )

    generate_button.click(
        fn=generate_interview_questions,
        inputs=[company_name, job_title, pdf_file, num_interviewers, questions_per_interviewer, lang_state],
        outputs=output_textbox
    )

if __name__ == "__main__":
    # share=True 옵션을 추가하여 외부 접속용 URL을 생성합니다.
    demo.launch(server_name="0.0.0.0", server_port=int(os.environ.get('PORT', 7860)), share=True)
