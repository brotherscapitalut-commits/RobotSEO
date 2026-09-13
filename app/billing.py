import stripe
from flask import Blueprint, render_template, redirect, url_for, current_app, request, jsonify
from flask_login import login_required, current_user
from app.extensions import db, csrf

bp = Blueprint("billing", __name__)


@bp.route("/billing/checkout")
@login_required
def checkout():
    if current_user.has_active_subscription:
        return redirect(url_for("dashboard.home"))
    return render_template("billing/checkout.html", price="$100/mês")


@bp.route("/billing/create-checkout-session", methods=["POST"])
@login_required
def create_checkout_session():
    stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]

    if not current_user.stripe_customer_id:
        customer = stripe.Customer.create(
            email=current_user.email, name=current_user.name
        )
        current_user.stripe_customer_id = customer.id
        db.session.commit()

    session = stripe.checkout.Session.create(
        customer=current_user.stripe_customer_id,
        mode="subscription",
        line_items=[{
            "price": current_app.config["STRIPE_PRICE_ID_MONTHLY"],
            "quantity": 1,
        }],
        success_url=current_app.config["BASE_URL"] + "/billing/success",
        cancel_url=current_app.config["BASE_URL"] + "/billing/checkout",
    )
    return jsonify({"url": session.url})


@bp.route("/billing/success")
@login_required
def success():
    return render_template("billing/success.html")


@bp.route("/billing/portal", methods=["POST"])
@login_required
def customer_portal():
    stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]
    session = stripe.billing_portal.Session.create(
        customer=current_user.stripe_customer_id,
        return_url=current_app.config["BASE_URL"] + "/dashboard",
    )
    return jsonify({"url": session.url})


@bp.route("/billing/webhook", methods=["POST"])
@csrf.exempt
def webhook():
    """Recebe eventos do Stripe: ativa/cancela assinatura automaticamente."""
    stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, current_app.config["STRIPE_WEBHOOK_SECRET"]
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return "Assinatura inválida", 400

    from app.models import User

    data = event["data"]["object"]
    etype = event["type"]

    if etype in (
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    ):
        customer_id = data.get("customer")
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
        if user:
            status = data.get("status", "inactive")
            user.subscription_status = "canceled" if etype.endswith("deleted") else status
            user.stripe_subscription_id = data.get("id")
            db.session.commit()

    return jsonify({"received": True})
