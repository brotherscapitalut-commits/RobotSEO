from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Site, Article, SearchTerm, Competitor, SiteAudit, ContentRecommendation, AuditFinding

bp = Blueprint("dashboard", __name__)


def require_subscription():
    return current_user.has_full_access


@bp.route("/dashboard")
@login_required
def home():
    if not require_subscription():
        return redirect(url_for("billing.checkout"))
    sites = Site.query.filter_by(user_id=current_user.id).all()
    site_id = request.args.get("site_id") or (sites[0].id if sites else None)
    active_site = next((s for s in sites if s.id == site_id), None)
    calendar_articles = []
    latest_audit = None
    if active_site:
        start = datetime.utcnow() - timedelta(days=1)
        end = datetime.utcnow() + timedelta(days=35)
        calendar_articles = Article.query.filter(
            Article.site_id == active_site.id,
            Article.scheduled_for >= start,
            Article.scheduled_for <= end,
        ).order_by(Article.scheduled_for.asc()).all()
        latest_audit = SiteAudit.query.filter_by(site_id=active_site.id).order_by(SiteAudit.created_at.desc()).first()
    return render_template("dashboard/home.html", sites=sites, active_site=active_site, calendar_articles=calendar_articles, latest_audit=latest_audit)


@bp.route("/dashboard/sites/new", methods=["GET", "POST"])
@login_required
def new_site():
    if not require_subscription():
        return redirect(url_for("billing.checkout"))
    if request.method == "POST":
        site = Site(
            user_id=current_user.id,
            url=request.form.get("url", "").strip(),
            title=request.form.get("title", "").strip(),
            description=request.form.get("description", "").strip(),
            language=request.form.get("language", "pt"),
            country=request.form.get("country", "BR"),
            publish_method=request.form.get("publish_method", "webhook"),
        )
        db.session.add(site)
        db.session.commit()
        flash("Site criado com sucesso.", "success")
        return redirect(url_for("dashboard.site_settings", site_id=site.id))
    return render_template("dashboard/new_site.html")


@bp.route("/dashboard/sites/<site_id>/discover", methods=["POST"])
@login_required
def discover_site(site_id):
    site = Site.query.filter_by(id=site_id, user_id=current_user.id).first_or_404()
    from app.audit.discovery import discover_site as run_discovery
    try:
        data = run_discovery(site.url)
        # Never overwrite information the customer has already supplied.
        if not site.title and data.get("title"):
            site.title = data["title"]
        if not site.description and data.get("description"):
            site.description = data["description"]
        if not site.what_you_sell and data.get("business_terms"):
            site.what_you_sell = "\n".join(data["business_terms"])
        db.session.commit()
        return jsonify({
            "ok": True,
            "data": {
                "title": data.get("title", ""),
                "description": data.get("description", ""),
                "business_terms": data.get("business_terms", []),
                "headings": data.get("headings", []),
            },
            "message": "Dados públicos detectados. Os campos vazios foram preenchidos; revise e complemente o restante.",
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 400


@bp.route("/dashboard/sites/<site_id>/settings", methods=["GET", "POST"])
@login_required
def site_settings(site_id):
    site = Site.query.filter_by(id=site_id, user_id=current_user.id).first_or_404()
    if request.method == "POST":
        form = request.form
        site.title = form.get("title", site.title)
        site.description = form.get("description", site.description)
        site.publish_method = form.get("publish_method", site.publish_method)
        site.wp_base_url = form.get("wp_base_url", "").strip() or None
        site.wp_username = form.get("wp_username", "").strip() or None
        site.wp_app_password = form.get("wp_app_password", "").strip() or None
        site.webhook_url = form.get("webhook_url", "").strip() or None
        site.writing_instructions = form.get("writing_instructions", "")
        site.article_length_words = int(form.get("article_length_words") or 1500)
        site.publish_frequency_per_week = int(form.get("publish_frequency_per_week") or 3)
        site.auto_publish = form.get("auto_publish") == "on"
        site.what_you_sell = form.get("what_you_sell", "")
        site.what_you_dont_sell = form.get("what_you_dont_sell", "")
        db.session.commit()
        flash("Configurações salvas.", "success")
        return redirect(url_for("dashboard.site_settings", site_id=site.id))
    return render_template("dashboard/site_settings.html", site=site)


@bp.route("/dashboard/sites/<site_id>/search-terms", methods=["POST"])
@login_required
def add_search_terms(site_id):
    site = Site.query.filter_by(id=site_id, user_id=current_user.id).first_or_404()
    raw_terms = request.form.get("terms", "")
    terms = [t.strip() for t in raw_terms.split("\n") if t.strip()]
    days_between = 7 / max(site.publish_frequency_per_week, 1)
    last = Article.query.filter_by(site_id=site.id).order_by(Article.scheduled_for.desc()).first()
    next_slot = last.scheduled_for if last and last.scheduled_for else datetime.utcnow()
    for term in terms:
        next_slot = next_slot + timedelta(days=days_between)
        db.session.add(SearchTerm(site_id=site.id, term=term))
        db.session.add(Article(site_id=site.id, search_term=term, status="scheduled", scheduled_for=next_slot))
    db.session.commit()
    flash(f"{len(terms)} artigos agendados.", "success")
    return redirect(url_for("dashboard.home", site_id=site.id))


@bp.route("/dashboard/articles/<article_id>/generate-now", methods=["POST"])
@login_required
def generate_now(article_id):
    from app.ai.engine import generate_article_content, AIGenerationError
    article = Article.query.get_or_404(article_id)
    Site.query.filter_by(id=article.site_id, user_id=current_user.id).first_or_404()
    try:
        result = generate_article_content(Site.query.get(article.site_id), article.search_term, article_id=article.id)
        article.title = result["title"]
        article.content_html = result["content_html"]
        article.ai_provider_used = result["provider"]
        article.hero_image_url = result.get("hero_image_url")
        article.status = "ready"
        article.error_message = None
        db.session.commit()
        return jsonify({"ok": True, "provider": result["provider"]})
    except AIGenerationError as e:
        article.status = "failed"
        article.error_message = str(e)
        db.session.commit()
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/dashboard/articles/<article_id>")
@login_required
def view_article(article_id):
    article = Article.query.get_or_404(article_id)
    site = Site.query.filter_by(id=article.site_id, user_id=current_user.id).first_or_404()
    return render_template("dashboard/article.html", article=article, site=site)


@bp.route("/dashboard/articles/<article_id>/edit", methods=["POST"])
@login_required
def edit_article(article_id):
    article = Article.query.get_or_404(article_id)
    Site.query.filter_by(id=article.site_id, user_id=current_user.id).first_or_404()
    article.title = request.form.get("title", article.title)
    article.content_html = request.form.get("content_html", article.content_html)
    article.meta_description = request.form.get("meta_description", article.meta_description)
    db.session.commit()
    flash("Artigo atualizado.", "success")
    return redirect(url_for("dashboard.view_article", article_id=article.id))


@bp.route("/dashboard/articles/<article_id>/publish-now", methods=["POST"])
@login_required
def publish_now(article_id):
    from app.publishers.webhook import publish_article
    article = Article.query.get_or_404(article_id)
    site = Site.query.filter_by(id=article.site_id, user_id=current_user.id).first_or_404()
    if article.status != "ready":
        return jsonify({"ok": False, "error": "Artigo ainda não está pronto"}), 400
    try:
        url = publish_article(site, article)
        article.status = "published"
        article.published_at = datetime.utcnow()
        article.published_url = url
        article.error_message = None
        db.session.commit()
        return jsonify({"ok": True, "url": url})
    except Exception as e:
        article.error_message = str(e)
        db.session.commit()
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.route("/dashboard/sites/<site_id>/competitors/add", methods=["POST"])
@login_required
def add_competitor(site_id):
    site = Site.query.filter_by(id=site_id, user_id=current_user.id).first_or_404()
    domain = request.form.get("domain", "").strip()
    if domain:
        db.session.add(Competitor(site_id=site.id, domain=domain))
        db.session.commit()
    return redirect(url_for("dashboard.site_settings", site_id=site.id))


@bp.route("/dashboard/sites/<site_id>/competitors/<competitor_id>/remove", methods=["POST"])
@login_required
def remove_competitor(site_id, competitor_id):
    site = Site.query.filter_by(id=site_id, user_id=current_user.id).first_or_404()
    c = Competitor.query.filter_by(id=competitor_id, site_id=site.id).first_or_404()
    db.session.delete(c)
    db.session.commit()
    return redirect(url_for("dashboard.site_settings", site_id=site.id))


@bp.route("/dashboard/sites/<site_id>/suggest-terms", methods=["POST"])
@login_required
def suggest_terms(site_id):
    from app.audit.ai_analyst import suggest_search_terms
    site = Site.query.filter_by(id=site_id, user_id=current_user.id).first_or_404()
    business_context = f"{site.title or site.url} — {site.description or ''}. Vende: {site.what_you_sell or ''}. Não vende: {site.what_you_dont_sell or ''}."
    competitors = [c.domain for c in site.competitors]
    existing_topics = [a.search_term for a in Article.query.filter_by(site_id=site.id).all() if a.search_term]
    terms = suggest_search_terms(business_context, competitors, existing_topics)
    return jsonify({"ok": True, "terms": terms})
