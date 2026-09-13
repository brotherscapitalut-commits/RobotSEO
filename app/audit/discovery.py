"""Automatic onboarding discovery from the customer's public website."""
import json
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from app.audit.crawler import fetch_page


def _soup(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


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
            data = json.loads(script.string or "{}")
            structured.append(data)
        except (json.JSONDecodeError, TypeError):
            continue

    # Deterministic discovery is always available, even without an AI key.
    business_terms = []
    keywords = [
        "serviço", "serviços", "tratamento", "tratamentos", "produto", "produtos",
        "consulta", "agendamento", "especialidade", "estética", "clínica", "terapia",
        "transporte", "aluguel", "fretamento", "consultoria", "curso", "plano",
    ]
    lower_text = text.lower()
    for term in keywords:
        if term in lower_text and term not in business_terms:
            business_terms.append(term)

    return {
        "url": url,
        "title": title,
        "description": description,
        "headings": headings[:30],
        "business_terms": business_terms,
        "structured_data": structured[:10],
        "text": text[:12000],
    }
