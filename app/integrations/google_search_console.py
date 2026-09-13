"""
Integração com Google Search Console via OAuth 2.0.
Fluxo: usuário clica 'Conectar Google' -> autoriza -> guardamos refresh_token
-> sincronizamos clicks/impressions/ctr/position diariamente para popular
a tela de Analytics (igual aos prints que você mandou).

Requer, no Google Cloud Console:
1. Projeto com a API "Google Search Console API" ativada
2. Tela de consentimento OAuth configurada
3. Credencial OAuth Client ID (tipo Web application) com redirect URI:
   {BASE_URL}/analytics/google/callback
   -> colar client_id e client_secret em GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET no .env
"""
from datetime import datetime, timedelta
from flask import current_app, url_for
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


def _client_config():
    return {
        "web": {
            "client_id": current_app.config["GOOGLE_OAUTH_CLIENT_ID"],
            "client_secret": current_app.config["GOOGLE_OAUTH_CLIENT_SECRET"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [current_app.config["BASE_URL"] + "/analytics/google/callback"],
        }
    }


def build_auth_url(state: str) -> str:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, state=state)
    flow.redirect_uri = current_app.config["BASE_URL"] + "/analytics/google/callback"
    auth_url, _ = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    return auth_url


def exchange_code(code: str) -> dict:
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES)
    flow.redirect_uri = current_app.config["BASE_URL"] + "/analytics/google/callback"
    flow.fetch_token(code=code)
    creds = flow.credentials
    return {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "expiry": creds.expiry,
    }


def _get_service(connection):
    creds = Credentials(
        token=connection.access_token,
        refresh_token=connection.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=current_app.config["GOOGLE_OAUTH_CLIENT_ID"],
        client_secret=current_app.config["GOOGLE_OAUTH_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    return build("searchconsole", "v1", credentials=creds)


def list_properties(connection) -> list:
    service = _get_service(connection)
    sites = service.sites().list().execute()
    return [s["siteUrl"] for s in sites.get("siteEntry", [])]


def sync_search_metrics(site, connection, days: int = 28):
    """Puxa clicks/impressions/ctr/position dos últimos N dias e salva em SearchMetric."""
    from app.extensions import db
    from app.models import SearchMetric

    if not connection.gsc_property_url:
        raise ValueError("Nenhuma propriedade GSC selecionada para este site")

    service = _get_service(connection)
    end = datetime.utcnow().date()
    start = end - timedelta(days=days)

    request_body = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "dimensions": ["date", "query", "page"],
        "rowLimit": 5000,
    }
    response = service.searchanalytics().query(
        siteUrl=connection.gsc_property_url, body=request_body
    ).execute()

    rows = response.get("rows", [])
    # limpa métricas antigas da janela antes de re-inserir (evita duplicar)
    SearchMetric.query.filter(
        SearchMetric.site_id == site.id, SearchMetric.date >= start
    ).delete()

    for row in rows:
        date_str, query, page = row["keys"]
        db.session.add(SearchMetric(
            site_id=site.id,
            date=datetime.strptime(date_str, "%Y-%m-%d").date(),
            query=query,
            page=page,
            clicks=row.get("clicks", 0),
            impressions=row.get("impressions", 0),
            ctr=row.get("ctr", 0.0),
            position=row.get("position", 0.0),
        ))

    connection.last_synced_at = datetime.utcnow()
    db.session.commit()
    return len(rows)
