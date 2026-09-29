import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import google.generativeai as genai

# Configurações do Perfil
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

CACHE_FILE = "seen_jobs.json"
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASSWORD")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

def load_seen_jobs():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen_jobs(seen_ids):
    with open(CACHE_FILE, "w") as f:
        json.dump(list(seen_ids), f)

def fetch_jobs():
    """Exemplo consumindo endpoints públicos agregados de ATS (como Remotive / APIs de empresas)."""
    jobs = []
    try:
        # API de vagas remotas públicas
        res = requests.get("https://remotive.com/api/remote-jobs?category=software-dev&limit=25", timeout=10)
        data = res.json()
        for item in data.get("jobs", []):
            jobs.append({
                "id": str(item["id"]),
                "title": item["title"],
                "company": item["company_name"],
                "location": item.get("candidate_required_location", "Anywhere"),
                "url": item["url"],
                "description": item["description"][:1500]  # snippet para validação
            })
    except Exception as e:
        print(f"Erro ao buscar vagas: {e}")
    return jobs

def evaluate_job_with_ai(job):
    prompt = f"""
    És um recrutador técnico sénior. Avalia a compatibilidade desta vaga com o candidato:
    {USER_PROFILE}

    Dados da Vaga:
    - Cargo: {job['title']}
    - Empresa: {job['company']}
    - Local / Restrições: {job['location']}
    - Descrição: {job['description']}

    Critérios de Avaliação:
    1. A vaga é Júnior ou Estágio? (Rejeita Pleno/Sénior).
    2. Se for remota internacional, permite contratação no Brasil/América Latina?
    3. Dá preferência a vagas que peçam Python, TypeScript, React/Next.js ou IA/Dados.

    Responde ESTRITAMENTE em formato JSON:
    {{
        "aprovada": true/false,
        "compatibilidade_score": "0 a 100%",
        "empresa": "{job['company']}",
        "cargo": "{job['title']}",
        "modalidade": "Remoto / Híbrido",
        "pontos_fortes": "Quais requisitos o candidato cumpre com base no currículo",
        "requisitos_em_falta": "Tecnologias pedidas que ele não tem listadas",
        "restricoes_ou_duvidas": "Avisos sobre senioridade, fuso horário ou contratação",
        "link": "{job['url']}"
    }}
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.strip().replace("```json", "").replace("```", "")
        return json.loads(text)
    except Exception:
        return None

def send_email(approved_jobs):
    if not approved_jobs:
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🎯 Novas Vagas Compatíveis ({len(approved_jobs)})"
    msg["From"] = GMAIL_USER
    msg["To"] = GMAIL_USER

    html_content = "<h2>Novas oportunidades encontradas:</h2>"
    for job in approved_jobs:
        html_content += f"""
        <div style="border: 1px solid #ddd; padding: 12px; margin-bottom: 15px; border-radius: 6px;">
            <h3 style="margin: 0 0 8px 0;">{job.get('cargo')} - <strong>{job.get('empresa')}</strong></h3>
            <p><strong>Modalidade:</strong> {job.get('modalidade')}</p>
            <p><strong>Requisitos:</strong> {job.get('requisitos')}</p>
            {f"<p style='color: #c0392b;'><strong>Atenção/Restrições:</strong> {job.get('restricoes_ou_duvidas')}</p>" if job.get('restricoes_ou_duvidas') else ""}
            <p><a href="{job.get('link')}" target="_blank" style="display:inline-block; padding:8px 12px; background:#0066cc; color:#fff; text-decoration:none; border-radius:4px;">Ver Inscrição</a></p>
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
        return

    approved = []
    for job in new_jobs:
        seen_ids.add(job["id"])
        eval_result = evaluate_job_with_ai(job)
        if eval_result and eval_result.get("aprovada"):
            approved.append(eval_result)

    if approved:
        send_email(approved)
        print(f"{len(approved)} vagas enviadas por e-mail.")
    else:
        print("Novas vagas encontradas, mas nenhuma passou no filtro de perfil.")

    save_seen_jobs(seen_ids)

if __name__ == "__main__":
    main()