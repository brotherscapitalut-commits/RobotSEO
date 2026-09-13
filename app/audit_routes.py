from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, current_app
from flask_login import login_required, current_user
from app.extensions import db
from app.models import Site, SiteAudit, AuditFinding, ContentRecommendation

bp = Blueprint("audit", __name__, url_prefix="/audit")


def _get_site_or_404(site_id):
    return Site.query.filter_by(id=site_id, user_id=current_user.id).first_or_404()


@bp.route("/<site_id>")
@login_required
def home(site_id):
    site = _get_site_or_404(site_id)
    audits = SiteAudit.query.filter_by(site_id=site.id).order_by(SiteAudit.created_at.desc()).all()
    latest = audits[0] if audits else None
    return render_template("audit/home.html", site=site, audits=audits, latest=latest)


@bp.route("/<site_id>/run", methods=["POST"])
@login_required
def run(site_id):
    from app.audit.orchestrator import run_audit_async

    site = _get_site_or_404(site_id)
    scope_crawl = request.form.get("scope_crawl") == "on"
    scope_urls = request.form.get("scope_urls") == "on"
    input_urls = request.form.get("input_urls", "").strip()

    if scope_crawl and scope_urls:
        scope = "both"
    elif scope_urls:
        scope = "urls"
    else:
        scope = "crawl"

    audit = SiteAudit(site_id=site.id, scope=scope, input_urls=input_urls or None, status="running")
    db.session.add(audit)
    db.session.commit()

    run_audit_async(current_app._get_current_object(), audit.id)

    flash("Auditoria iniciada. Isso pode levar alguns minutos — a página atualiza automaticamente.", "success")
    return redirect(url_for("audit.view", site_id=site.id, audit_id=audit.id))


@bp.route("/<site_id>/<audit_id>")
@login_required
def view(site_id, audit_id):
    site = _get_site_or_404(site_id)
    audit = SiteAudit.query.filter_by(id=audit_id, site_id=site.id).first_or_404()
    findings = AuditFinding.query.filter_by(audit_id=audit.id).order_by(
        db.case(
            (AuditFinding.severity == "critical", 0),
            (AuditFinding.severity == "warning", 1),
            (AuditFinding.severity == "info", 2),
            (AuditFinding.severity == "pass", 3),
            else_=4,
        ), AuditFinding.category.asc(), AuditFinding.created_at.asc()
    ).all()
    recommendations = ContentRecommendation.query.filter_by(audit_id=audit.id, status="suggested").all()
    counts = {
        "critical": sum(1 for f in findings if f.severity == "critical"),
        "warning": sum(1 for f in findings if f.severity == "warning"),
        "info": sum(1 for f in findings if f.severity == "info"),
        "pass": sum(1 for f in findings if f.severity == "pass"),
    }
    categories = {}
    for f in findings:
        categories.setdefault(f.category or "outros", {"total": 0, "critical": 0, "warning": 0, "info": 0, "pass": 0})
        categories[f.category or "outros"]["total"] += 1
        if f.severity in categories[f.category or "outros"]:
            categories[f.category or "outros"][f.severity] += 1
    return render_template(
        "audit/view.html",
        site=site,
        audit=audit,
        findings=findings,
        recommendations=recommendations,
        counts=counts,
        categories=categories,
    )


@bp.route("/<site_id>/<audit_id>/status")
@login_required
def status(site_id, audit_id):
    """Endpoint leve pra polling via JS enquanto a auditoria roda em background."""
    site = _get_site_or_404(site_id)
    audit = SiteAudit.query.filter_by(id=audit_id, site_id=site.id).first_or_404()
    return jsonify({"status": audit.status})


@bp.route("/recommendations/<rec_id>/schedule", methods=["POST"])
@login_required
def schedule_recommendation(rec_id):
    from app.models import Article

    rec = ContentRecommendation.query.get_or_404(rec_id)
    _get_site_or_404(rec.site_id)

    article = Article(
        site_id=rec.site_id,
        search_term=rec.search_term or rec.title_suggestion,
        status="scheduled",
        scheduled_for=datetime.utcnow(),
    )
    db.session.add(article)
    db.session.commit()

    rec.status = "scheduled"
    rec.created_article_id = article.id
    db.session.commit()

    return jsonify({"ok": True, "article_id": article.id})


@bp.route("/recommendations/<rec_id>/dismiss", methods=["POST"])
@login_required
def dismiss_recommendation(rec_id):
    rec = ContentRecommendation.query.get_or_404(rec_id)
    _get_site_or_404(rec.site_id)
    rec.status = "dismissed"
    db.session.commit()
    return jsonify({"ok": True})
