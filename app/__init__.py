from flask import Flask
from config import Config
from app.extensions import db, login_manager, bcrypt, migrate, scheduler, csrf, mail, limiter


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(user_id)

    from app.auth import bp as auth_bp
    from app.dashboard import bp as dashboard_bp
    from app.admin import bp as admin_bp
    from app.billing import bp as billing_bp
    from app.analytics import bp as analytics_bp
    from app.audit_routes import bp as audit_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(billing_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(audit_bp)

    from flask import redirect, url_for
    from flask_login import current_user

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("admin.dashboard" if current_user.is_admin else "dashboard.home"))
        return redirect(url_for("auth.login"))

    with app.app_context():
        db.create_all()
        _seed_admin(app)

    from app.scheduler_jobs import start_scheduler
    start_scheduler(app, scheduler)

    return app


def _seed_admin(app):
    from app.models import User, Site

    email = app.config["ADMIN_EMAIL"]
    if not User.query.filter_by(email=email).first():
        admin = User(email=email, name="Administrador", role="admin",
                     subscription_status="active", email_verified=True)
        admin.set_password(app.config["ADMIN_PASSWORD"])
        db.session.add(admin)
        db.session.commit()
        print(f"[seed] Admin criado: {email}")

    # Usuário de teste solicitado, com assinatura ativa e site de exemplo pré-configurado
    test_email = "pedrofilho1@gmail.com"
    test_password = "senha12345"
    test_user = User.query.filter_by(email=test_email).first()
    if not test_user:
        test_user = User(email=test_email, name="Pedro Filho", role="customer",
                          subscription_status="active", email_verified=True)
        test_user.set_password(test_password)
        db.session.add(test_user)
        db.session.commit()

        demo_site = Site(
            user_id=test_user.id,
            url="https://exemplo-demo.com",
            title="Site de Demonstração",
            description="Empresa fictícia de transporte executivo usada para testar o sistema.",
            language="pt", country="BR",
            publish_method="webhook",
            what_you_sell="Fretamento executivo\nTransporte para eventos corporativos",
            what_you_dont_sell="Transporte público urbano\nAluguel de veículos sem motorista",
        )
        db.session.add(demo_site)
        db.session.commit()
        print(f"[seed] Usuário de teste criado: {test_email} / senha: {test_password}")
