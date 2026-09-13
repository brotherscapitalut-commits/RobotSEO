import secrets
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, session
from flask_login import login_required, current_user
from sqlalchemy import func
from app.extensions import db
from app.models import Site, GoogleConnection, SearchMetric, TrendTopic, ContentAlert

bp = Blueprint("analytics", __name__, url_prefix="/analytics")


def _get_site_or_404(site_id):
    return Site.query.filter_by(id=site_id, user_id=current_user.id).first_or_404()


@bp.route("/<site_id>")
@login_required
def home(site_id):
    site = _get_site_or_404(site_id)
    connection = GoogleConnection.query.filter_by(site_id=site.id).first()

    daily = []
    top_queries = []
    top_pages = []
    totals = {"clicks": 0, "impressions": 0, "ctr": 0.0, "position": 0.0}

    if connection and connection.last_synced_at:
        since = datetime.utcnow().date() - timedelta(days=28)

        daily_rows = (
            db.session.query(
                SearchMetric.date,
                func.sum(SearchMetric.clicks).label("clicks"),
                func.sum(SearchMetric.impressions).label("impressions"),
            )
            .filter(SearchMetric.site_id == site.id, SearchMetric.date >= since)
            .group_by(SearchMetric.date)
            .order_by(SearchMetric.date.asc())
            .all()
        )
        daily = [{"date": r.date.isoformat(), "clicks": r.clicks, "impressions": r.impressions} for r in daily_rows]

        top_queries = (
            db.session.query(
                SearchMetric.query,
                func.sum(SearchMetric.clicks).label("clicks"),
                func.avg(SearchMetric.position).label("position"),
            )
            .filter(SearchMetric.site_id == site.id, SearchMetric.date >= since)
            .group_by(SearchMetric.query)
            .order_by(func.sum(SearchMetric.clicks).desc())
            .limit(10)
            .all()
        )

        top_pages = (
            db.session.query(
                SearchMetric.page,
                func.sum(SearchMetric.impressions).label("impressions"),
                func.avg(SearchMetric.position).label("position"),
            )
            .filter(SearchMetric.site_id == site.id, SearchMetric.date >= since)
            .group_by(SearchMetric.page)
            .order_by(func.sum(SearchMetric.impressions).desc())
            .limit(10)
            .all()
        )

        agg = (
            db.session.query(
                func.sum(SearchMetric.clicks).label("clicks"),
                func.sum(SearchMetric.impressions).label("impressions"),
                func.avg(SearchMetric.ctr).label("ctr"),
                func.avg(SearchMetric.position).label("position"),
            )
            .filter(SearchMetric.site_id == site.id, SearchMetric.date >= since)
            .first()
        )
        if agg and agg.clicks is not None:
            totals = {
                "clicks": agg.clicks or 0,
                "impressions": agg.impressions or 0,
                "ctr": round((agg.ctr or 0) * 100, 2),
                "position": round(agg.position or 0, 1),
            }

    trend_topics = TrendTopic.query.filter_by(site_id=site.id).order_by(TrendTopic.created_at.desc()).all()
    alerts = ContentAlert.query.filter_by(site_id=site.id, status="new").order_by(ContentAlert.created_at.desc()).all()

    return render_template(
        "analytics/home.html",
        site=site, connection=connection, daily=daily,
        top_queries=top_queries, top_pages=top_pages, totals=totals,
        trend_topics=trend_topics, alerts=alerts,
    )


# ---------------- Google Search Console OAuth ----------------

@bp.route("/<site_id>/google/connect")
@login_required
def google_connect(site_id):
    from app.integrations.google_search_console import build_auth_url

    site = _get_site_or_404(site_id)
    state = secrets.token_urlsafe(16)
    session["gsc_oauth_state"] = state
    session["gsc_oauth_site_id"] = site.id
    return redirect(build_auth_url(state))


@bp.route("/google/callback")
@login_required
def google_callback():
    from app.integrations.google_search_console import exchange_code

    if request.args.get("state") != session.get("gsc_oauth_state"):
        flash("Estado OAuth inválido, tente novamente.", "error")
        return redirect(url_for("dashboard.home"))

    site_id = session.get("gsc_oauth_site_id")
    site = _get_site_or_404(site_id)
    code = request.args.get("code")

    tokens = exchange_code(code)
    connection = GoogleConnection.query.filter_by(site_id=site.id).first()
    if not connection:
        connection = GoogleConnection(site_id=site.id)
        db.session.add(connection)

    connection.access_token = tokens["access_token"]
    connection.refresh_token = tokens["refresh_token"] or connection.refresh_token
    connection.token_expiry = tokens["expiry"]
    db.session.commit()

    flash("Google conectado! Agora selecione a propriedade do Search Console.", "success")
    return redirect(url_for("analytics.select_property", site_id=site.id))


@bp.route("/<site_id>/google/select-property", methods=["GET", "POST"])
@login_required
def select_property(site_id):
    from app.integrations.google_search_console import list_properties

    site = _get_site_or_404(site_id)
    connection = GoogleConnection.query.filter_by(site_id=site.id).first_or_404()

    if request.method == "POST":
        connection.gsc_property_url = request.form.get("property_url")
        db.session.commit()
        flash("Propriedade selecionada. Sincronizando dados...", "success")
        return redirect(url_for("analytics.sync_now", site_id=site.id))

    properties = list_properties(connection)
    return render_template("analytics/select_property.html", site=site, properties=properties)


@bp.route("/<site_id>/google/sync", methods=["GET", "POST"])
@login_required
def sync_now(site_id):
    from app.integrations.google_search_console import sync_search_metrics

    site = _get_site_or_404(site_id)
    connection = GoogleConnection.query.filter_by(site_id=site.id).first_or_404()

    try:
        count = sync_search_metrics(site, connection)
        flash(f"{count} linhas de métricas sincronizadas.", "success")
    except Exception as e:
        flash(f"Falha ao sincronizar: {e}", "error")

    return redirect(url_for("analytics.home", site_id=site.id))


# ---------------- Google Trends / Alertas de conteúdo ----------------

@bp.route("/<site_id>/trends/add", methods=["POST"])
@login_required
def add_trend_topic(site_id):
    site = _get_site_or_404(site_id)
    keyword = request.form.get("keyword", "").strip()
    if keyword:
        db.session.add(TrendTopic(site_id=site.id, keyword=keyword))
        db.session.commit()
        flash(f"Termo '{keyword}' agora está sendo monitorado no Google Trends.", "success")
    return redirect(url_for("analytics.home", site_id=site.id))


@bp.route("/<site_id>/trends/<topic_id>/remove", methods=["POST"])
@login_required
def remove_trend_topic(site_id, topic_id):
    site = _get_site_or_404(site_id)
    topic = TrendTopic.query.filter_by(id=topic_id, site_id=site.id).first_or_404()
    db.session.delete(topic)
    db.session.commit()
    return redirect(url_for("analytics.home", site_id=site.id))


@bp.route("/alerts/<alert_id>/create-article", methods=["POST"])
@login_required
def act_on_alert(alert_id):
    from app.integrations.google_trends import create_article_from_alert

    alert = ContentAlert.query.get_or_404(alert_id)
    site = _get_site_or_404(alert.site_id)
    article_id = create_article_from_alert(alert_id)
    return jsonify({"ok": True, "article_id": article_id})


@bp.route("/alerts/<alert_id>/dismiss", methods=["POST"])
@login_required
def dismiss_alert(alert_id):
    alert = ContentAlert.query.get_or_404(alert_id)
    _get_site_or_404(alert.site_id)
    alert.status = "dismissed"
    db.session.commit()
    return jsonify({"ok": True})
