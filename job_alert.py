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


def evaluate_job_with_ai(job):
    if not ai_client:
        print("Erro: Cliente da IA não está disponível.")
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

    time.sleep(1)

    try:
        # Usa o chat para contornar a restrição de AFC do SDK
        chat_session = ai_client.chats.create(model="gemini-3.8-flash")
        response = chat_session.send_message(prompt)
        raw_text = response.text.strip()
    except Exception as e:
        print(f"Falha na IA para [{job['title']}]. Detalhe: {e}")
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

    new_jobs = [j for j in current_jobs if j["id"] not in seen_ids]
    if not new_jobs:
        print("Nenhuma nova vaga encontrada nesta execução.")
        save_seen_jobs(seen_ids)
        return

    approved = []
    for job in new_jobs:
        seen_ids.add(job["id"])
        eval_result = evaluate_job_with_ai(job)
        if eval_result and eval_result.get("aprovada"):
            approved.append(eval_result)

    if approved:
        send_email(approved)
        print(f"{len(approved)} vagas enviadas por e-mail com sucesso.")
    else:
        print("Novas vagas encontradas, mas nenhuma foi aprovada pelos critérios.")

    save_seen_jobs(seen_ids)


if __name__ == "__main__":
    main()