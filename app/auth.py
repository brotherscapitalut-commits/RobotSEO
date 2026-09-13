from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db, limiter
from app.models import User
from app.services.tokens import generate_token, verify_token
from app.services.email_service import send_welcome_email, send_verification_email, send_password_reset_email

bp = Blueprint("auth", __name__)

EMAIL_VERIFY_SALT = "email-verify"
PASSWORD_RESET_SALT = "password-reset"
PASSWORD_RESET_MAX_AGE = 3600  # 1 hora
EMAIL_VERIFY_MAX_AGE = 86400 * 3  # 3 dias


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.dashboard" if current_user.is_admin else "dashboard.home"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user, remember=True)
            next_url = request.args.get("next")
            if user.is_admin:
                return redirect(next_url or url_for("admin.dashboard"))
            return redirect(next_url or url_for("dashboard.home"))

        flash("E-mail ou senha inválidos.", "error")

    return render_template("auth/login.html")


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        name = request.form.get("name", "").strip()

        if not email or not password or len(password) < 8:
            flash("Preencha e-mail e uma senha com no mínimo 8 caracteres.", "error")
            return render_template("auth/register.html")

        if User.query.filter_by(email=email).first():
            flash("Este e-mail já está cadastrado.", "error")
            return render_template("auth/register.html")

        user = User(email=email, name=name, role="customer")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        send_welcome_email(user)
        token = generate_token(user.id, EMAIL_VERIFY_SALT)
        verify_url = url_for("auth.verify_email", token=token, _external=True)
        send_verification_email(user, verify_url)

        login_user(user)
        return redirect(url_for("billing.checkout"))

    return render_template("auth/register.html")


@bp.route("/verify-email/<token>")
def verify_email(token):
    user_id = verify_token(token, EMAIL_VERIFY_SALT, EMAIL_VERIFY_MAX_AGE)
    if not user_id:
        flash("Link de verificação inválido ou expirado.", "error")
        return redirect(url_for("auth.login"))

    user = User.query.get(user_id)
    if user:
        user.email_verified = True
        db.session.commit()
        flash("E-mail verificado com sucesso!", "success")
    return redirect(url_for("auth.login"))


@bp.route("/resend-verification", methods=["POST"])
@login_required
def resend_verification():
    if current_user.email_verified:
        return redirect(url_for("dashboard.home"))
    token = generate_token(current_user.id, EMAIL_VERIFY_SALT)
    verify_url = url_for("auth.verify_email", token=token, _external=True)
    send_verification_email(current_user, verify_url)
    flash("E-mail de verificação reenviado.", "success")
    return redirect(request.referrer or url_for("dashboard.home"))


@bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = User.query.filter_by(email=email).first()
        if user:
            token = generate_token(user.id, PASSWORD_RESET_SALT)
            reset_url = url_for("auth.reset_password", token=token, _external=True)
            send_password_reset_email(user, reset_url)
        flash("Se este e-mail existir na nossa base, você receberá um link de redefinição.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html")


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user_id = verify_token(token, PASSWORD_RESET_SALT, PASSWORD_RESET_MAX_AGE)
    if not user_id:
        flash("Link de redefinição inválido ou expirado. Solicite um novo.", "error")
        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        if len(password) < 8:
            flash("A senha deve ter no mínimo 8 caracteres.", "error")
            return render_template("auth/reset_password.html", token=token)

        user = User.query.get(user_id)
        user.set_password(password)
        db.session.commit()
        flash("Senha redefinida! Faça login com a nova senha.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", token=token)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
