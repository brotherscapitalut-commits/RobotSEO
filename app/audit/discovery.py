"""Automatic onboarding discovery from the customer's public website."""
import json
import re
from flask import current_app
from bs4 import BeautifulSoup
from app.audit.crawler import fetch_page


def _soup(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def _ai_enrich(url: str, title: str, description: str, text: str) -> dict:
    if not current_app.config.get("ANTHROPIC_API_KEY") and not current_app.config.get("GOOGLE_API_KEY"):
        return {}
    from app.ai.engine import generate_with_fallback
    prompt = f"""Identifique o negócio descrito no site abaixo. Não invente dados.
URL: {url}
Título: {title}
Descrição: {description}
Conteúdo público:
{text[:9000]}

Retorne SOMENTE JSON válido:
{{
  "business_name": "nome identificado ou vazio",
  "business_description": "descrição objetiva ou vazio",
  "what_you_sell": ["serviço/produto explicitamente oferecido"],
  "what_you_dont_sell": ["somente itens explicitamente indicados como não oferecidos"],
  "language": "pt|en|es|outro",
  "country": "BR|US|outro"
}}"""
    system = "Você é um analista de onboarding para SEO. Extraia apenas fatos presentes no conteúdo fornecido. Nunca invente serviços, preços, localização ou políticas."
    try:
        raw, _, _ = generate_with_fallback(prompt, system=system)
        raw = re.sub(r"^```json\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE).strip()
        return json.loads(raw)
    except Exception:
        return {}


def discover_site(url: str) -> dict:
    html = fetch_page(url)
    if not html:
        raise ValueError("Não foi possível acessar o site. Verifique a URL e tente novamente.")

    soup = _soup(html)
    title = (soup.title.get_text(" ", strip=True) if soup.title else "").strip()
    meta = soup.find("meta", attrs={"name": "description"})
    description = (meta.get("content", "") if meta else "").strip()
    headings = [h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2", "h3"]) if h.get_text(strip=True)]
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p") if p.get_text(strip=True)]
    nav_links = [a.get_text(" ", strip=True) for a in soup.find_all("a") if a.get_text(strip=True)]
    text = "\n".join(headings[:30] + paragraphs[:40] + nav_links[:40])

    structured = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            structured.append(json.loads(script.string or "{}"))
        except (json.JSONDecodeError, TypeError):
            continue

    business_terms = []
    keywords = ["serviço", "serviços", "tratamento", "tratamentos", "produto", "produtos", "consulta", "agendamento", "especialidade", "estética", "clínica", "terapia", "transporte", "aluguel", "fretamento", "consultoria", "curso", "plano"]
    lower_text = text.lower()
    for term in keywords:
        if term in lower_text and term not in business_terms:
            business_terms.append(term)

    ai = _ai_enrich(url, title, description, text)
    return {
        "url": url,
        "title": ai.get("business_name") or title,
        "description": ai.get("business_description") or description,
        "what_you_sell": ai.get("what_you_sell") or business_terms,
        "what_you_dont_sell": ai.get("what_you_dont_sell") or [],
        "language": ai.get("language"),
        "country": ai.get("country"),
        "headings": headings[:30],
        "business_terms": business_terms,
        "structured_data": structured[:10],
        "text": text[:12000],
    }
