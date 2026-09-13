"""
Publica via webhook genérico: enviamos um POST JSON assinado (HMAC) para a URL
que o cliente configurou no site dele (endpoint próprio, Zapier, Make, Supabase
Edge Function, etc). Isso cobre qualquer plataforma que não tenha conector nativo.
"""
import hmac
import hashlib
import json
import requests


class WebhookPublishError(Exception):
    pass


def _sign(payload_bytes: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


def publish_to_webhook(site, article) -> str:
    if not site.webhook_url:
        raise WebhookPublishError("Nenhuma webhook_url configurada para este site")

    payload = {
        "id": article.id,
        "title": article.title,
        "content_html": article.content_html,
        "meta_description": article.meta_description,
        "hero_image_url": article.hero_image_url,
        "slug": None,  # o receptor pode gerar o slug a partir do título
    }
    body = json.dumps(payload).encode("utf-8")
    signature = _sign(body, site.webhook_secret or "")

    resp = requests.post(
        site.webhook_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-AutoSEO-Signature": signature,
        },
        timeout=30,
    )

    if resp.status_code >= 300:
        raise WebhookPublishError(
            f"Webhook retornou {resp.status_code}: {resp.text[:500]}"
        )

    try:
        data = resp.json()
        return data.get("url", site.webhook_url)
    except ValueError:
        return site.webhook_url


def publish_article(site, article) -> str:
    """Roteador: escolhe o método de publicação configurado no site."""
    if site.publish_method == "wordpress":
        from app.publishers.wordpress import publish_to_wordpress
        return publish_to_wordpress(site, article)
    elif site.publish_method == "webhook":
        return publish_to_webhook(site, article)
    else:
        raise ValueError(f"Método de publicação desconhecido: {site.publish_method}")
