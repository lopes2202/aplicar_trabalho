import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import google.generativeai as genai

# Configurações do Perfil
USER_PROFILE = """
- Perfil: Cursando Inteligência Artificial (2º semestre)
- Nível de Experiência: Estágio ou Júnior
- Áreas de interesse: FullStack, Ciência/Engenharia de Dados, IA, Segurança da Informação
- Idioma: Inglês Intermediário
- Localização: Brasília - DF (Brasil)
- Modalidades aceitas:
  * Remoto global (deve permitir contratação de residentes no Brasil)
  * Híbrido ou presencial em Brasília - DF
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
    Você é um assistente de carreira. Avalie se a vaga abaixo é adequada para o seguinte perfil:
    {USER_PROFILE}

    Detalhes da vaga:
    - Cargo: {job['title']}
    - Empresa: {job['company']}
    - Local / Restrição: {job['location']}
    - Descrição: {job['description']}

    Critérios rigorosos:
    1. Vaga de Estágio ou Júnior (descarte Pleno/Sênior).
    2. Se remota, confirme se brasileiros/candidatos da América Latina são elegíveis.
    3. Alinhada com as áreas de interesse (FullStack, Dados, IA, Segurança).

    Responda em JSON:
    {{
        "aprovada": true/false,
        "empresa": "{job['company']}",
        "cargo": "{job['title']}",
        "modalidade": "Remoto / Híbrido",
        "requisitos": "Resumo dos requisitos principais",
        "restricoes_ou_duvidas": "Sinalize pontos dúbios sobre localidade ou senioridade (se houver)",
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