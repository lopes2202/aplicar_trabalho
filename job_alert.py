import os
import json
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from bs4 import BeautifulSoup
from google import genai
from jobspy import scrape_jobs

# Carrega .env caso esteja testando localmente
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

GEMINI_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASSWORD") or os.getenv("GMAIL_APP_PASS")
CACHE_FILE = "seen_jobs.json"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
if GEMINI_MODEL == "gemini-2.0-flash":
    GEMINI_MODEL = "gemini-3.8-flash"
MAX_JOBS_PER_RUN = int(os.getenv("MAX_JOBS_PER_RUN", "1"))
USE_GEMINI = os.getenv("USE_GEMINI", "1").strip().lower() in {"1", "true", "yes", "on"}

# Inicialização oficial do novo SDK google-genai
ai_client = None
if GEMINI_KEY:
    try:
        ai_client = genai.Client(api_key=GEMINI_KEY)
    except Exception as e:
        print(f"Erro ao inicializar o cliente Gemini: {e}")
else:
    print("Aviso: Chave GEMINI_API_KEY não foi encontrada nas variáveis de ambiente.")

USER_PROFILE = """
Perfil do Candidato: Gabriel Lopes de Brito
Formação:
- Tecnologia em Análise e Desenvolvimento de Sistemas (Concluído - jul/2025)
- Graduação em Inteligência Artificial (Gran Faculdade - Previsão: jul/2028)

Experiência Atual:
- Estagiário de Desenvolvimento de Software (Atacadão Dia a Dia, desde abr/2026)
- Atuação com Next.js, React Native (Expo), TypeScript e Python
- Criação de APIs, autenticação MFA, painéis de KPI, otimização de queries/lotes e Prisma ORM

Competências Técnicas:
- Linguagens: Python, JavaScript, TypeScript, SQL, Java
- Frameworks/Libs: Next.js, React, React Native, Expo, FastAPI, Django, Node.js, Angular, Prisma ORM
- Bases de Dados: PostgreSQL, SQL Server
- DevOps & Práticas: Git, GitHub, Docker, APIs REST, Automações, Integração com Google Gemini

Preferências de Vagas:
- Nível: Estágio avançado ou Desenvolvedor Júnior (Full Stack, Backend, Frontend, IA/Dados)
- Idioma: Inglês Intermediário
- Localização: Remoto global (elegível para residentes no Brasil) ou Híbrido/Presencial em Brasília-DF
"""


def load_seen_jobs():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_seen_jobs(seen_ids):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen_ids), f, indent=2, ensure_ascii=False)


def fetch_jobspy():
    jobs = []
    try:
        jobs_df = scrape_jobs(
            site_name=["indeed"],
            search_term="desenvolvedor junior",
            location="Brasilia, Brazil",
            results_wanted=10,
            hours_old=48,
            country_indeed="brazil",
        )
        for _, row in jobs_df.iterrows():
            job_url = str(row.get("job_url", "")).strip()
            job_id = str(row.get("id", job_url))
            if job_url:
                jobs.append({
                    "id": f"indeed_{job_id}",
                    "title": str(row.get("title", "")).strip(),
                    "company": str(row.get("company", "Confidencial")).strip(),
                    "location": str(row.get("location", "Brasília / Remoto")).strip(),
                    "url": job_url,
                    "description": str(row.get("description", ""))[:1500].strip(),
                })
    except Exception as e:
        print(f"Erro ao buscar no JobSpy (Indeed): {e}")
    return jobs


def fetch_remotive():
    jobs = []
    try:
        res = requests.get(
            "https://remotive.com/api/remote-jobs?category=software-dev&limit=20",
            timeout=10,
        )
        for item in res.json().get("jobs", []):
            jobs.append({
                "id": f"remotive_{item['id']}",
                "title": item["title"],
                "company": item["company_name"],
                "location": item.get("candidate_required_location", "Anywhere"),
                "url": item["url"],
                "description": item["description"][:1500],
            })
    except Exception as e:
        print(f"Erro ao buscar no Remotive: {e}")
    return jobs


def fetch_linkedin():
    jobs = []
    url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=desenvolvedor%20junior&location=Brasil&f_TPR=r86400"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        postings = soup.find_all("li")
        for post in postings:
            title_tag = post.find("h3", class_="base-search-card__title")
            company_tag = post.find("h4", class_="base-search-card__subtitle")
            link_tag = post.find("a", class_="base-card__full-link")
            loc_tag = post.find("span", class_="job-search-card__location")

            if title_tag and link_tag:
                link = link_tag["href"].split("?")[0]
                job_id = link.rstrip("/").split("-")[-1]
                jobs.append({
                    "id": f"linkedin_{job_id}",
                    "title": title_tag.text.strip(),
                    "company": company_tag.text.strip() if company_tag else "Confidencial",
                    "location": loc_tag.text.strip() if loc_tag else "Brasil",
                    "url": link,
                    "description": f"Vaga no LinkedIn: {title_tag.text.strip()}",
                })
    except Exception as e:
        print(f"Erro ao buscar no LinkedIn: {e}")
    return jobs


def fetch_nerdin():
    jobs = []
    url = "https://nerdin.com.br/vagas?termo=junior"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        for card in soup.find_all("div", class_="vaga-item"):
            a_tag = card.find("a")
            if a_tag and a_tag.get("href"):
                jobs.append({
                    "id": f"nerdin_{a_tag['href'].split('/')[-1]}",
                    "title": a_tag.text.strip(),
                    "company": "Nerdin",
                    "location": "Remoto / Brasil",
                    "url": f"https://nerdin.com.br{a_tag['href']}",
                    "description": card.text.strip()[:1000],
                })
    except Exception as e:
        print(f"Erro ao buscar no Nerdin: {e}")
    return jobs


def fetch_jobs():
    all_jobs = []
    all_jobs.extend(fetch_jobspy())
    all_jobs.extend(fetch_remotive())
    all_jobs.extend(fetch_linkedin())
    all_jobs.extend(fetch_nerdin())
    return all_jobs


def local_profile_match(job):
    text = " ".join([
        job.get("title", ""),
        job.get("company", ""),
        job.get("location", ""),
        job.get("description", ""),
    ]).lower()

    junior_keywords = [
        "junior", "jr", "estagiario", "estágio", "intern", "trainee",
        "associate software engineer", "software engineer", "developer",
        "full stack", "frontend", "frontend developer", "backend", "web developer",
    ]
    senior_keywords = [
        "senior", "staff", "lead", "principal", "tech lead", "manager", "arquitect",
        "architect", "specialist"
    ]
    tech_keywords = [
        "python", "javascript", "typescript", "react", "next", "node", "sql",
        "java", "django", "fastapi", "api", "frontend", "backend", "full stack",
        "fullstack", "ia", "data", "dados", "graphql"
    ]

    title = job.get("title", "").lower()
    if any(term in title for term in senior_keywords):
        return False

    if not any(term in title for term in junior_keywords):
        if not any(term in text for term in tech_keywords):
            return False

    if not any(term in text for term in tech_keywords):
        return False

    if "remote" in text or "remoto" in text or "hybrid" in text or "hibrido" in text or "presencial" in text:
        return True

    return "brasil" in text or "brazil" in text or "df" in text or "brasilia" in text


def build_local_approval(job):
    title = job.get("title", "").strip()
    company = job.get("company", "").strip()
    location = job.get("location", "").strip()
    return {
        "aprovada": True,
        "compatibilidade_score": "82%",
        "empresa": company,
        "cargo": title,
        "modalidade": location or "Remoto / Híbrido",
        "pontos_fortes": "Alinhamento com o perfil júnior/full-stack e stack principal do candidato.",
        "requisitos_em_falta": "Nenhum",
        "restricoes_ou_duvidas": "Nenhuma",
        "link": job.get("url", ""),
    }


def evaluate_job_with_ai(job):
    if not USE_GEMINI or not ai_client:
        print(f"[{job['title']}] Sem uso de Gemini: avaliando localmente por regras do perfil.")
        if local_profile_match(job):
            return build_local_approval(job)
        return None

    prompt = f"""
    És um recrutador técnico sénior. Avalia a compatibilidade desta vaga com o candidato:
    {USER_PROFILE}

    Dados da Vaga:
    - Cargo: {job['title']}
    - Empresa: {job['company']}
    - Local / Restrições: {job['location']}
    - Descrição: {job['description']}

    Critérios de Avaliação:
    1. A vaga é Júnior ou Estágio? (Rejeita Pleno/Sênior).
    2. Se for remota internacional, permite contratação no Brasil/América Latina?
    3. Dá preferência a vagas que peçam Python, TypeScript, React/Next.js ou IA/Dados.

    Responde ESTRITAMENTE em formato JSON puro, sem blocos de código ou crases de markdown:
    {{
        "aprovada": true,
        "compatibilidade_score": "85%",
        "empresa": "{job['company']}",
        "cargo": "{job['title']}",
        "modalidade": "Remoto / Híbrido",
        "pontos_fortes": "Alinhamento com a stack",
        "requisitos_em_falta": "Nenhum",
        "restricoes_ou_duvidas": "Nenhuma",
        "link": "{job['url']}"
    }}
    """

    max_tentativas = 3
    raw_text = None

    for tentativa in range(max_tentativas):
        try:
            chat_session = ai_client.chats.create(model=GEMINI_MODEL)
            response = chat_session.send_message(prompt)
            raw_text = response.text.strip()
            break

        except Exception as e:
            erro = str(e)
            if any(token in erro.lower() for token in ["429", "503", "quota", "rate limit", "too many requests"]):
                print(f"[{job['title']}] Cota/Sobrecarga da Google. Tentativa {tentativa + 1}/{max_tentativas}. Aguardando 20s...")
                if tentativa < max_tentativas - 1:
                    time.sleep(20)
                else:
                    print(f"Falha definitiva para [{job['title']}] após {max_tentativas} tentativas.")
                    return None
            else:
                print(f"Falha na IA para [{job['title']}]. Detalhe: {erro}")
                return None

    if not raw_text:
        return None

    try:
        clean = raw_text
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[-1]
        if clean.endswith("```"):
            clean = clean.rsplit("```", 1)[0]
        return json.loads(clean.strip())
    except Exception as e:
        print(f"Erro ao converter JSON para [{job['title']}]: {e}")
        return None


def send_email(approved_jobs):
    if not approved_jobs:
        return

    if not GMAIL_USER or not GMAIL_APP_PASS:
        print("Credenciais de Gmail ausentes. E-mail não enviado.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🎯 Novas Vagas Compatíveis ({len(approved_jobs)})"
    msg["From"] = GMAIL_USER
    msg["To"] = GMAIL_USER

    html_content = "<h2>Novas oportunidades encontradas para o seu perfil:</h2>"
    for job in approved_jobs:
        score = job.get("compatibilidade_score", "N/A")
        html_content += f"""
        <div style="border: 1px solid #e1e4e8; padding: 16px; margin-bottom: 20px; border-radius: 8px; font-family: sans-serif;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <h3 style="margin: 0; color: #1a73e8;">{job.get('cargo')} — <strong>{job.get('empresa')}</strong></h3>
                <span style="background: #e8f0fe; color: #1a73e8; padding: 4px 8px; border-radius: 4px; font-weight: bold;">Score: {score}</span>
            </div>
            <p style="margin: 4px 0;"><strong>Modalidade/Local:</strong> {job.get('modalidade')}</p>
            <p style="margin: 4px 0; color: #137333;"><strong>Pontos Fortes:</strong> {job.get('pontos_fortes', 'Compatível com a stack principal')}</p>
            {f"<p style='margin: 4px 0; color: #b06000;'><strong>Requisitos em Falta:</strong> {job.get('requisitos_em_falta')}</p>" if job.get('requisitos_em_falta') else ""}
            {f"<p style='margin: 4px 0; color: #d93025;'><strong>Avisos / Restrições:</strong> {job.get('restricoes_ou_duvidas')}</p>" if job.get('restricoes_ou_duvidas') and job.get('restricoes_ou_duvidas') != 'Nenhuma' else ""}
            <div style="margin-top: 12px;">
                <a href="{job.get('link')}" target="_blank" style="display: inline-block; padding: 8px 14px; background: #1a73e8; color: #ffffff; text-decoration: none; border-radius: 4px; font-weight: 500;">Acessar Vaga</a>
            </div>
        </div>
        """
    msg.attach(MIMEText(html_content, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASS)
        server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())


def main():
    seen_ids = load_seen_jobs()
    current_jobs = fetch_jobs()

    new_jobs = [j for j in current_jobs if j["id"] not in seen_ids][:MAX_JOBS_PER_RUN]
    if not new_jobs:
        print("Nenhuma nova vaga encontrada nesta execução.")
        save_seen_jobs(seen_ids)
        return

    approved = []
    for job in new_jobs:
        eval_result = evaluate_job_with_ai(job)
        if eval_result is not None:
            seen_ids.add(job["id"])
            if eval_result.get("aprovada"):
                approved.append(eval_result)

    if approved:
        send_email(approved)
        print(f"{len(approved)} vagas enviadas por e-mail com sucesso.")
    elif new_jobs:
        print("Novas vagas encontradas, mas nenhuma foi aprovada pelos critérios.")

    save_seen_jobs(seen_ids)


if __name__ == "__main__":
    main()