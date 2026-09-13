"""
Crawler leve: parte da home (ou de uma lista de URLs específicas), segue
links internos até um limite, e baixa o HTML de cada página pra análise.
Respeita robots.txt (via urllib.robotparser) e limita profundidade/quantidade
pra não sobrecarregar o site do cliente nem travar a auditoria.
"""
import requests
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup

USER_AGENT = "AutoContentAI-Auditor/1.0 (+https://seudominio.com)"
MAX_PAGES = 25
TIMEOUT = 15


def _same_domain(base_url: str, candidate: str) -> bool:
    return urlparse(base_url).netloc == urlparse(candidate).netloc


def _load_robots(base_url: str) -> RobotFileParser:
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
    except Exception:
        pass  # se não conseguir ler robots.txt, assume permitido (comportamento padrão de crawlers)
    return rp


def fetch_page(url: str):
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        if resp.status_code >= 400:
            return None
        return resp.text
    except requests.RequestException:
        return None


def crawl_site(base_url: str, max_pages: int = MAX_PAGES) -> dict:
    """Retorna {url: html} para até max_pages páginas do mesmo domínio, respeitando robots.txt."""
    robots = _load_robots(base_url)
    to_visit = [base_url]
    visited = set()
    pages = {}

    while to_visit and len(pages) < max_pages:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)

        try:
            if not robots.can_fetch(USER_AGENT, url):
                continue
        except Exception:
            pass

        html = fetch_page(url)
        if not html:
            continue
        pages[url] = html

        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            link = urljoin(url, a["href"]).split("#")[0]
            if _same_domain(base_url, link) and link not in visited and link not in to_visit:
                to_visit.append(link)

    return pages


def fetch_specific_urls(urls: list) -> dict:
    """URLs coladas manualmente pelo cliente: assume consentimento explícito,
    então não filtra por robots.txt (o próprio dono está pedindo a análise)."""
    pages = {}
    for url in urls:
        html = fetch_page(url)
        if html:
            pages[url] = html
    return pages
