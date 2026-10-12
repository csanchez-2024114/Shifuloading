import logging
import os
from typing import Annotated, Optional
import stripe
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr, Field, model_validator
from app.database import get_current_user, get_db
from app.services.stripe_service import StripeService
from config import Config

router = APIRouter(tags=["Billing"])
templates = Jinja2Templates(directory="templates")
logger = logging.getLogger(__name__)


def _has_active_subscription(current_user: dict) -> bool:
    return bool(current_user.get("subscription", {}).get("active", False))


class CheckoutRequest(BaseModel):
    user_id: str
    plan: str = Field(..., pattern="^(standard|pro|premium|enterprise)$")
    email: EmailStr

    @model_validator(mode="before")
    def accept_spanish_email_alias(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        if "correo" in values and (not values.get("email")):
            values["email"] = values.get("correo")
        if "userEmail" in values and (not values.get("email")):
            values["email"] = values.get("userEmail")
        if "user_email" in values and (not values.get("email")):
            values["email"] = values.get("user_email")
        return values


class CancelSubscriptionRequest(BaseModel):
    user_id: str
    at_period_end: bool = True


class ChangeSubscriptionRequest(BaseModel):
    user_id: str
    plan: str = Field(..., min_length=1)
    email: EmailStr

    @model_validator(mode="before")
    def accept_spanish_email_alias(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        if "correo" in values and (not values.get("email")):
            values["email"] = values.get("correo")
        if "userEmail" in values and (not values.get("email")):
            values["email"] = values.get("userEmail")
        if "user_email" in values and (not values.get("email")):
            values["email"] = values.get("user_email")
        return values


class ReactivateSubscriptionRequest(BaseModel):
    user_id: str
    product_slug: Optional[str] = None


class ProductUpsertRequest(BaseModel):
    slug: str = Field(..., min_length=2, max_length=80)
    name: str = Field(..., min_length=2, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    plan_code: Optional[str] = Field(default=None, max_length=80)
    stripe_product_id: Optional[str] = None
    stripe_price_id: Optional[str] = None
    unit_amount: Optional[int] = Field(default=None, ge=0)
    currency: str = Field(default="usd", pattern="^[a-zA-Z]{3}$")
    interval: str = Field(default="month", pattern="^(day|week|month|year)$")
    active: bool = True


class ProductCheckoutRequest(BaseModel):
    user_id: str
    email: EmailStr

    @model_validator(mode="before")
    def accept_spanish_email_alias(cls, values: dict) -> dict:
        if not isinstance(values, dict):
            return values
        if "correo" in values and (not values.get("email")):
            values["email"] = values.get("correo")
        if "userEmail" in values and (not values.get("email")):
            values["email"] = values.get("userEmail")
        if "user_email" in values and (not values.get("email")):
            values["email"] = values.get("user_email")
        return values


class UpdateFeatureByIndex(BaseModel):
    index: int
    value: str


class AddFeature(BaseModel):
    value: str


@router.post("/checkout-sessions")
async def create_checkout_session(body: CheckoutRequest, mongo=Depends(get_db)):
    """Initiates checkout and returns a Stripe Checkout Session URL."""
    service = StripeService(mongo)
    try:
        logger.info(
            f"🛒 NEW CHECKOUT INITIATED | User: {body.user_id} | Email: {body.email} | Plan: {body.plan}"
        )
        success_url = "http://localhost:5000/api/v1/billing/payment/success?session_id={CHECKOUT_SESSION_ID}"
        cancel_url = "http://localhost:5000/api/v1/billing/payment/cancel"
        checkout_url = await service.create_checkout(
            user_id=body.user_id,
            email=body.email,
            plan=body.plan,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        logger.info(
            f"✅ CHECKOUT CREATED | User: {body.user_id} | Plan: {body.plan} | URL: {checkout_url}"
        )
        return {"success": True, "url": checkout_url}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal error processing payment")


@router.get("/products")
async def list_products(
    active_only: bool = Query(
        True, description="If true, returns only active products"
    ),
    mongo=Depends(get_db),
):
    """Lists dynamic products managed from Mongo + Stripe."""
    service = StripeService(mongo)
    products = await service.list_products(active_only=active_only)
    return {"success": True, "products": products}


@router.get("/products/{slug}")
async def get_product(slug: str, mongo=Depends(get_db)):
    """Gets a dynamic product by slug."""
    service = StripeService(mongo)
    product = await service.get_product_by_slug(slug)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"success": True, "product": product}


@router.post("/products/{slug}/checkout-sessions")
async def create_checkout_session_for_product(
    slug: str, body: ProductCheckoutRequest, mongo=Depends(get_db)
):
    """Initiates dynamic checkout using a product configured in Mongo + Stripe."""
    service = StripeService(mongo)
    try:
        logger.info(
            f"🛒 NEW CHECKOUT INITIATED | User: {body.user_id} | Email: {body.email} | Product: {slug}"
        )
        success_url = "http://localhost:5000/api/v1/billing/payment/success?session_id={CHECKOUT_SESSION_ID}"
        cancel_url = "http://localhost:5000/api/v1/billing/payment/cancel"
        checkout_url = await service.create_checkout_for_product_slug(
            user_id=body.user_id,
            email=body.email,
            product_slug=slug,
            success_url=success_url,
            cancel_url=cancel_url,
        )
        logger.info(
            f"✅ CHECKOUT CREATED | User: {body.user_id} | Product: {slug} | URL: {checkout_url}"
        )
        return {"success": True, "url": checkout_url}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception:
        raise HTTPException(status_code=500, detail="Could not start checkout")


@router.post("/products/{id}/features")
async def add_feature(id: str, body: AddFeature, mongo=Depends(get_db)):
    service = StripeService(mongo)
    new_feature = await service.add_characteristics_products(id, body.value)
    return new_feature


@router.get("/products/{id}/features")
async def get_features(id: str, mongo=Depends(get_db)):
    """Gets features of a product by its ID."""
    service = StripeService(mongo)
    product_features = await service.get_characteristics_products(id)
    return product_features


@router.patch("/products/{id}/features")
async def update_feature(
    id: str, body: UpdateFeatureByIndex, mongo=Depends(get_db)
):
    """Updates a feature of a product by its index."""
    service = StripeService(mongo)
    product_update = await service.update_characteristics_products(
        id, body.index, body.value
    )
    return product_update


@router.delete("/products/{id}/features/{feature_id}")
async def delete_feature(
    id: Annotated[str, Path(title="Product collection ID")],
    feature_id: Annotated[int, Path(title="Feature index")],
    mongo=Depends(get_db),
):
    """Deletes a feature of a product by its index."""
    service = StripeService(mongo)
    product_update = await service.delete_characteristics_products(id, feature_id)
    return product_update


@router.post("/products")
async def upsert_product(body: ProductUpsertRequest, mongo=Depends(get_db)):
    """Creates/updates a dynamic product (Stripe Product/Price/PaymentLink + Mongo)."""
    service = StripeService(mongo)
    try:
        product = await service.upsert_product(
            slug=body.slug,
            name=body.name,
            description=body.description,
            plan_code=body.plan_code,
            stripe_product_id=body.stripe_product_id,
            stripe_price_id=body.stripe_price_id,
            unit_amount=body.unit_amount,
            currency=body.currency,
            interval=body.interval,
            active=body.active,
        )
        return {"success": True, "product": product}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception:
        raise HTTPException(status_code=500, detail="Could not save product")


@router.delete("/products/{slug}")
async def delete_product(slug: str, mongo=Depends(get_db)):
    """Deletes a dynamic product from the local catalog."""
    service = StripeService(mongo)
    deleted = await service.delete_product(slug)
    if not deleted:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"success": True, "deleted": True}


@router.get("/products/{slug}/payment-link")
async def get_payment_link(slug: str, mongo=Depends(get_db)):
    """Returns a reusable payment URL for a product."""
    service = StripeService(mongo)
    try:
        url = await service.get_or_create_payment_link(slug)
        return {"success": True, "url": url}
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception:
        raise HTTPException(status_code=500, detail="Could not generate payment URL")


@router.delete("/subscription")
async def cancel_subscription(body: CancelSubscriptionRequest, mongo=Depends(get_db)):
    """Cancels a user's subscription."""
    service = StripeService(mongo)
    try:
        result = await service.cancel_subscription(
            user_id=body.user_id, at_period_end=body.at_period_end
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception:
        raise HTTPException(status_code=500, detail="Error canceling subscription")


@router.post("/subscription/change")
async def change_subscription(body: ChangeSubscriptionRequest, mongo=Depends(get_db)):
    """Changes a user's subscription plan."""
    service = StripeService(mongo)
    try:
        logger.info(
            f"🔄 SUBSCRIPTION CHANGE | User: {body.user_id} | New Plan: {body.plan}"
        )
        result = await service.change_subscription(
            user_id=body.user_id, new_plan=body.plan, email=body.email
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception:
        raise HTTPException(status_code=500, detail="Error changing subscription")


@router.post("/subscription/reactivate")
async def reactivate_subscription(body: ReactivateSubscriptionRequest, mongo=Depends(get_db)):
    """Reactivates a cancelled subscription."""
    service = StripeService(mongo)
    try:
        logger.info(f"🔄 SUBSCRIPTION REACTIVATE | User: {body.user_id}")
        result = await service.reactivate_subscription(
            user_id=body.user_id, product_slug=body.product_slug
        )
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception:
        raise HTTPException(status_code=500, detail="Error reactivating subscription")


@router.post("/webhook")
async def webhook(request: Request, mongo=Depends(get_db)):
    """Entry point for asynchronous Stripe events."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    service = StripeService(mongo)
    if not Config.WEBHOOK_SECRET:
        logger.error("WEBHOOK_SECRET not configured in .env")
        raise HTTPException(status_code=500, detail="Webhook not configured")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, Config.WEBHOOK_SECRET
        )
        logger.info(f"✅ Valid webhook: {event['type']} (ID: {event['id']})")
    except ValueError as e:
        logger.error(f"❌ Invalid payload: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid payload: {str(e)}")
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"❌ Invalid signature (incorrect WEBHOOK_SECRET): {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid webhook signature. Check WEBHOOK_SECRET in .env",
        )
    try:
        await service.handle_webhook_event(event)
        logger.info(f"✅ Webhook processed successfully: {event['type']}")
    except Exception as e:
        logger.error(f"❌ Error processing webhook: {str(e)}")
        return {"success": False, "error": str(e)}
    return {"success": True}


@router.get("/payment/success", response_class=HTMLResponse)
async def payment_success(session_id: str, mongo=Depends(get_db)):
    """Payment success page."""
    logger.info(f"📍 USER ON SUCCESS PAGE | Session ID: {session_id}")
    service = StripeService(mongo)
    try:
        logger.info(f"🔄 Syncing payment from session...")
        await service.sync_from_session_id(session_id)
        logger.info(f"✅ Payment synced successfully")
    except Exception as e:
        logger.error(f"⚠️  Sync error: {str(e)}")
    html_content = (
        '\n    <!DOCTYPE html>\n    <html lang="es">\n    <head>\n        <meta charset="UTF-8">\n        <meta name="viewport" content="width=device-width, initial-scale=1.0">\n        <title>¡Pago Exitoso!</title>\n        <style>\n            * {\n                margin: 0;\n                padding: 0;\n                box-sizing: border-box;\n            }\n            body {\n                font-family: \'Segoe UI\', Tahoma, Geneva, Verdana, sans-serif;\n                background: linear-gradient(135deg, #233FC9 0%, #6687FF 100%);\n                display: flex;\n                justify-content: center;\n                align-items: center;\n                min-height: 100vh;\n                padding: 20px;\n            }\n            .container {\n                background: white;\n                padding: 60px 40px;\n                border-radius: 20px;\n                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);\n                max-width: 600px;\n                text-align: center;\n                animation: slideUp 0.5s ease-out;\n            }\n            @keyframes slideUp {\n                from {\n                    opacity: 0;\n                    transform: translateY(30px);\n                }\n                to {\n                    opacity: 1;\n                    transform: translateY(0);\n                }\n            }\n            .success-icon {\n                width: 100px;\n                height: 100px;\n                margin: 0 auto 30px;\n                background: linear-gradient(135deg, #233FC9 0%, #6687FF 100%);\n                border-radius: 50%;\n                display: flex;\n                align-items: center;\n                justify-content: center;\n                font-size: 60px;\n                color: white;\n                box-shadow: 0 10px 30px rgba(35, 63, 201, 0.4);\n                animation: scaleIn 0.5s ease-out;\n            }\n            @keyframes scaleIn {\n                from {\n               '
        + session_id
        + "</p>\n                <p>Tu factura ha sido enviada a tu correo electrónico</p>\n            </div>\n        </div>\n\n        <script>\n            let seconds = 5;\n            const countdownEl = document.getElementById('countdown');\n\n            function goToFrontend() {\n                window.location.href = 'http://localhost:5173/chat?paymentSuccess=true';\n            }\n\n            const interval = setInterval(() => {\n                seconds--;\n                countdownEl.textContent = seconds;\n\n                if (seconds <= 0) {\n                    clearInterval(interval);\n                    goToFrontend();\n                }\n            }, 1000);\n        </script>\n    </body>\n    </html>\n    "
    )
    return html_content


@router.get("/payment/cancel", response_class=HTMLResponse)
async def payment_cancel(request: Request):
    """Retry page if user cancels checkout."""
    return templates.TemplateResponse(
        "payment_template.html",
        {
            "request": request,
            "title": "Pago Cancelado",
            "message": "No se realizó ningún cobro. Puedes intentarlo de nuevo cuando quieras.",
            "button_text": "Ver Planes",
            "button_url": "/pricing",
        },
    )