from functools import wraps
from flask import Blueprint, render_template, abort, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, Site, Article

bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@bp.route("/")
@login_required
@admin_required
def dashboard():
    total_users = User.query.filter_by(role="customer").count()
    active_subs = User.query.filter(User.subscription_status == "active").count()
    total_sites = Site.query.count()
    total_articles = Article.query.count()
    published = Article.query.filter_by(status="published").count()
    failed = Article.query.filter_by(status="failed").count()

    recent_failed = (
        Article.query.filter_by(status="failed")
        .order_by(Article.created_at.desc())
        .limit(10)
        .all()
    )

    mrr = active_subs * 100  # $100/mês por assinatura ativa

    return render_template(
        "admin/dashboard.html",
        total_users=total_users,
        active_subs=active_subs,
        total_sites=total_sites,
        total_articles=total_articles,
        published=published,
        failed=failed,
        mrr=mrr,
        recent_failed=recent_failed,
    )


@bp.route("/users")
@login_required
@admin_required
def users():
    all_users = User.query.filter_by(role="customer").order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=all_users)


@bp.route("/users/<user_id>/toggle-admin", methods=["POST"])
@login_required
@admin_required
def toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    user.role = "admin" if user.role != "admin" else "customer"
    db.session.commit()
    flash(f"Permissões de {user.email} atualizadas.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/sites")
@login_required
@admin_required
def sites():
    all_sites = Site.query.order_by(Site.created_at.desc()).all()
    return render_template("admin/sites.html", sites=all_sites)
