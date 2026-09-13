"""
Publica artigos direto no WordPress do cliente via REST API + Application Password.
O cliente cria uma "Application Password" em Usuários > Perfil > Senhas de Aplicativo
no painel WP dele, e cola aqui (nunca a senha principal da conta).
"""
import requests


class WordPressPublishError(Exception):
    pass


def publish_to_wordpress(site, article) -> str:
    base = (site.wp_base_url or "").rstrip("/")
    if not base or not site.wp_username or not site.wp_app_password:
        raise WordPressPublishError("Credenciais do WordPress incompletas para este site")

    endpoint = f"{base}/wp-json/wp/v2/posts"

    payload = {
        "title": article.title,
        "content": article.content_html,
        "status": "publish" if site.auto_publish else "draft",
        "excerpt": article.meta_description or "",
    }

    resp = requests.post(
        endpoint,
        json=payload,
        auth=(site.wp_username, site.wp_app_password),
        timeout=30,
    )

    if resp.status_code not in (200, 201):
        raise WordPressPublishError(
            f"WordPress retornou {resp.status_code}: {resp.text[:500]}"
        )

    data = resp.json()
    return data.get("link", base)
