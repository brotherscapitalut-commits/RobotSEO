"""
Crawler leve: parte da home (ou de uma lista de URLs específicas), segue
links internos até um limite, e baixa o HTML de cada página pra análise.
Respeita robots.txt e limita profundidade/quantidade.
"""
import requests
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup

USER_AGENT = "AutoContentAI-Auditor/1.0"
MAX_PAGES = 25
TIMEOUT = 15


def _soup(html: str) -> BeautifulSoup:
    """Prefere lxml quando instalado, mas nunca deixa a auditoria depender dele."""
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


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
        pass
    return rp


def fetch_page(url: str):
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
            allow_redirects=True,
        )
        content_type = resp.headers.get("content-type", "").lower()
        if resp.status_code >= 400 or (content_type and "text/html" not in content_type and "application/xhtml" not in content_type):
            return None
        return resp.text
    except requests.RequestException:
        return None


def crawl_site(base_url: str, max_pages: int = MAX_PAGES) -> dict:
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

        soup = _soup(html)
        for a in soup.find_all("a", href=True):
            link = urljoin(url, a["href"]).split("#")[0]
            if _same_domain(base_url, link) and link not in visited and link not in to_visit:
                to_visit.append(link)

    return pages


def fetch_specific_urls(urls: list) -> dict:
    pages = {}
    for url in urls:
        html = fetch_page(url)
        if html:
            pages[url] = html
    return pages
