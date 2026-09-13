"""
Auditoria técnica de SEO on-page: título, meta description, headings,
canonical, imagens sem alt, schema.org (JSON-LD), Open Graph. Cada check
devolve um dict de "finding" pronto pra virar AuditFinding no banco.

Este módulo cobre a camada "SEO clássico" — a camada GEO/AEO (specificity,
resposta direta, citabilidade por IA) fica no ai_analyst.py, porque isso
exige julgamento de conteúdo, não é regra fixa.
"""
import json
import re
from bs4 import BeautifulSoup


def _finding(url, category, severity, title, description, how_to_fix):
    return {
        "url": url, "category": category, "severity": severity,
        "title": title, "description": description, "how_to_fix": how_to_fix,
    }


def check_page_seo(url: str, html: str) -> list:
    findings = []
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.find("title")
    title_text = title_tag.get_text(strip=True) if title_tag else ""
    if not title_text:
        findings.append(_finding(url, "seo", "critical", "Título ausente",
            "A página não tem tag <title>.", "Adicione um título único de 50-60 caracteres com a palavra-chave principal."))
    elif len(title_text) > 65:
        findings.append(_finding(url, "seo", "warning", "Título muito longo",
            f"Título tem {len(title_text)} caracteres e pode ser cortado no Google.", "Reduza para até 60 caracteres."))

    meta_desc = soup.find("meta", attrs={"name": "description"})
    desc_content = meta_desc.get("content", "").strip() if meta_desc else ""
    if not desc_content:
        findings.append(_finding(url, "seo", "critical", "Meta description ausente",
            "Sem meta description, o Google gera um snippet aleatório da página.",
            "Escreva uma meta description de 140-160 caracteres com call-to-action."))
    elif len(desc_content) > 165:
        findings.append(_finding(url, "seo", "warning", "Meta description longa",
            f"{len(desc_content)} caracteres — será cortada nos resultados de busca.", "Reduza para até 160 caracteres."))

    h1_tags = soup.find_all("h1")
    if len(h1_tags) == 0:
        findings.append(_finding(url, "seo", "critical", "H1 ausente",
            "Nenhum H1 encontrado — prejudica a hierarquia semântica da página.",
            "Adicione exatamente um H1 descrevendo o assunto principal da página."))
    elif len(h1_tags) > 1:
        findings.append(_finding(url, "seo", "warning", "Múltiplos H1",
            f"{len(h1_tags)} tags H1 encontradas. O ideal é apenas 1 por página.",
            "Mantenha só um H1; converta os demais em H2/H3."))

    canonical = soup.find("link", attrs={"rel": "canonical"})
    if not canonical:
        findings.append(_finding(url, "seo", "warning", "Canonical ausente",
            "Sem tag canonical, risco de conteúdo duplicado em variações da URL.",
            "Adicione <link rel='canonical' href='...'> apontando para a URL preferida."))

    imgs = soup.find_all("img")
    imgs_no_alt = [i for i in imgs if not i.get("alt", "").strip()]
    if imgs_no_alt:
        findings.append(_finding(url, "seo", "warning", "Imagens sem texto alternativo",
            f"{len(imgs_no_alt)} de {len(imgs)} imagens sem atributo alt.",
            "Adicione alt descritivo em todas as imagens — ajuda acessibilidade e SEO de imagem."))

    json_ld_scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    for script in json_ld_scripts:
        try:
            json.loads(script.string or "{}")
        except (json.JSONDecodeError, TypeError):
            findings.append(_finding(url, "seo", "critical", "JSON-LD inválido",
                "Há um bloco de schema.org com JSON malformado.",
                "Corrija a sintaxe JSON ou valide em https://validator.schema.org/"))
    if not json_ld_scripts:
        findings.append(_finding(url, "aeo", "warning", "Nenhum schema.org (JSON-LD)",
            "Sem dados estruturados, a página perde elegibilidade para rich snippets e é menos citável por IA.",
            "Adicione JSON-LD relevante: Organization, Service, FAQPage, ou LocalBusiness conforme o conteúdo."))

    og_title = soup.find("meta", attrs={"property": "og:title"})
    if not og_title:
        findings.append(_finding(url, "seo", "info", "Open Graph ausente",
            "Sem meta tags og:title/og:description/og:image, os links compartilhados ficam sem preview.",
            "Adicione as tags og:title, og:description e og:image."))

    return findings


def extract_page_text(html: str) -> str:
    """Extrai texto visível principal da página para análise de conteúdo pela IA."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:8000]
