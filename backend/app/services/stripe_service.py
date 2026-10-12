"""
Stripe Service - Pagos, Suscripciones y Webhooks.
Single Source of Truth con Config, Fail-Fast en inicialización y resolución dinámica segura.
"""
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests
import stripe
from bson import ObjectId
from fastapi import HTTPException
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError
from config import Config
from app.core.constants import Collections
from app.core.db_utils import canonicalize_email
logger = logging.getLogger(__name__)

class PlanCharacteristics(BaseModel):
    characteristics: list[str]

class StripeService:

    def __init__(self, mongo_db):
        self.mongo = mongo_db
        stripe.api_key = Config.STRIPE_SECRET_KEY
        if not stripe.api_key:
            logger.warning('[stripe_service] STRIPE_SECRET_KEY no está configurada. Las operaciones de pago fallarán.')

    def _now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    async def send_invoice_email(self, user_email: str, user_name: str, plan: str, stripe_subscription_id: str, session_id: str) -> None:
        """Envía la factura de Stripe como adjunto por correo al usuario usando template HTML."""
        try:
            logger.info(f'📄 Recuperando factura de Stripe | Suscripción: {stripe_subscription_id}')
            subscription = stripe.Subscription.retrieve(stripe_subscription_id)
            invoice = None
            invoice_pdf_url = None
            invoice_number = session_id
            amount_paid = 0
            pdf_bytes = None
            if subscription.latest_invoice:
                invoice = stripe.Invoice.retrieve(subscription.latest_invoice)
                invoice_pdf_url = invoice.invoice_pdf
                invoice_number = invoice.number or session_id
                amount_paid = invoice.amount_paid / 100 if invoice.amount_paid else 0
                logger.info(f'✓ Factura encontrada | Número: {invoice_number}')
                if invoice_pdf_url:
                    try:
                        logger.info(f'📥 Descargando PDF de la factura...')
                        response = requests.get(invoice_pdf_url, timeout=30)
                        if response.status_code == 200:
                            pdf_bytes = response.content
                            logger.info(f'✓ PDF descargado exitosamente ({len(pdf_bytes)} bytes)')
                        else:
                            logger.warning(f'⚠️  No se pudo descargar el PDF (status: {response.status_code})')
                    except Exception as e:
                        logger.error(f'⚠️  Error descargando PDF: {str(e)}')
            template_path = os.path.join(os.path.dirname(__file__), '..', 'email_templates', 'invoice.html')
            with open(template_path, 'r', encoding='utf-8') as f:
                html_template = f.read()
            html_body = html_template.replace('{{user_name}}', user_name)
            html_body = html_body.replace('{{plan}}', plan.upper())
            html_body = html_body.replace('{{amount}}', f'{amount_paid:.2f}')
            html_body = html_body.replace('{{date}}', datetime.now(timezone.utc).strftime('%d/%m/%Y'))
            html_body = html_body.replace('{{invoice_number}}', invoice_number)
            subject = f'📄 Factura #{invoice_number} — HyperShifu {plan.upper()}'
            if pdf_bytes:
                from email.message import EmailMessage
                from app.utils.mail import _env, _smtp_from, _smtp_send, validate_smtp_config
                validate_smtp_config()
                msg = EmailMessage()
                msg['Subject'] = subject
                msg['From'] = f'HyperShifu Pagos <{_smtp_from()}>'
                msg['To'] = user_email
                msg.set_content('Este correo contiene información sobre tu factura.')
                msg.add_alternative(html_body, subtype='html')
                msg.add_attachment(pdf_bytes, maintype='application', subtype='pdf', filename=f'Factura-HyperShifu-{invoice_number}.pdf')
                _smtp_send(msg)
                logger.info(f'📧 Factura PDF adjunta (HTML) enviada a {user_email}')
            else:
                from email.message import EmailMessage
                from app.utils.mail import _env, _smtp_from, _smtp_send, validate_smtp_config
                validate_smtp_config()
                msg = EmailMessage()
                msg['Subject'] = subject
                msg['From'] = f'HyperShifu Pagos <{_smtp_from()}>'
                msg['To'] = user_email
                msg.set_content('Este correo contiene información sobre tu factura.')
                msg.add_alternative(html_body, subtype='html')
                _smtp_send(msg)
                logger.info(f'📧 Factura (HTML) enviada a {user_email} (sin adjunto)')
        except Exception as e:
            logger.error(f'❌ Error enviando factura por correo: {str(e)}')

    def _normalize_slug(self, slug: str) -> str:
        return (slug or '').strip().lower()

    def _serialize_product(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        if not doc:
            return {}
        serialized = dict(doc)
        if '_id' in serialized:
            serialized['id'] = str(serialized.pop('_id'))
        return serialized

    async def resolve_plan_code_from_slug(self, product_slug: Optional[str]) -> Optional[str]:
        slug = self._normalize_slug(product_slug or '')
        if not slug:
            return None
        product = await self.mongo.stripe_products.find_one({'slug': slug}, {'plan_code': 1, 'slug': 1})
        if not product:
            return slug
        return product.get('plan_code') or product.get('slug')

    async def create_checkout(self, user_id: str, email: str, plan: str, success_url: str, cancel_url: str):
        """Genera la URL de Stripe Checkout y registra el pago pendiente."""
        price_attr = f'STRIPE_PRICE_{plan.upper()}'
        price_id = getattr(Config, price_attr, None)
        if not price_id:
            raise ValueError(f'Plan {plan} no configurado en variables de entorno ({price_attr}).')
        try:
            session = stripe.checkout.Session.create(customer_email=email, payment_method_types=['card'], mode='subscription', line_items=[{'price': price_id, 'quantity': 1}], success_url=success_url, cancel_url=cancel_url, metadata={'user_id': user_id, 'plan': plan})
            await self.mongo.payments.insert_one({'user_id': user_id, 'stripe_session_id': session.id, 'plan': plan, 'status': 'pending', 'created_at': self._now_utc()})
            return session.url
        except Exception as e:
            logger.error(f'Error creando sesión de Stripe: {str(e)}')
            raise

    async def list_products(self, active_only: bool=True) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {'active': True} if active_only else {}
        cursor = self.mongo.stripe_products.find(query).sort('slug', 1)
        docs = await cursor.to_list(length=500)
        return [self._serialize_product(doc) for doc in docs]

    async def get_product_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        normalized = self._normalize_slug(slug)
        if not normalized:
            return None
        doc = await self.mongo.stripe_products.find_one({'slug': normalized})
        if not doc:
            return None
        return self._serialize_product(doc)

    async def upsert_product(self, *, slug: str, name: str, description: Optional[str]=None, plan_code: Optional[str]=None, stripe_product_id: Optional[str]=None, stripe_price_id: Optional[str]=None, unit_amount: Optional[int]=None, currency: str='usd', interval: str='month', active: bool=True) -> Dict[str, Any]:
        normalized_slug = self._normalize_slug(slug)
        if not normalized_slug:
            raise ValueError('El slug es obligatorio.')
        normalized_plan = self._normalize_slug(plan_code or normalized_slug)
        now = self._now_utc()
        if unit_amount == 0 and (not stripe_price_id):
            await self.mongo.stripe_products.update_one({'slug': normalized_slug}, {'$set': {'slug': normalized_slug, 'name': name, 'description': description, 'plan_code': normalized_plan, 'stripe_product_id': None, 'stripe_price_id': None, 'stripe_payment_link': None, 'unit_amount': 0, 'currency': currency.lower(), 'interval': interval, 'active': active, 'is_free': True, 'updated_at': now}, '$setOnInsert': {'created_at': now}}, upsert=True)
            saved = await self.mongo.stripe_products.find_one({'slug': normalized_slug})
            return self._serialize_product(saved)
        if stripe_price_id:
            price = stripe.Price.retrieve(stripe_price_id)
            stripe_product_id = str(price.product)
            stripe_price_id = price.id
            if price.unit_amount is not None:
                unit_amount = int(price.unit_amount)
            currency = (price.currency or currency).lower()
            if getattr(price, 'recurring', None):
                interval = price.recurring.get('interval', interval)
        else:
            if not stripe_product_id:
                product = stripe.Product.create(name=name, description=description, metadata={'slug': normalized_slug, 'plan_code': normalized_plan})
                stripe_product_id = product.id
            else:
                stripe.Product.modify(stripe_product_id, name=name, description=description, metadata={'slug': normalized_slug, 'plan_code': normalized_plan})
            if unit_amount is None:
                raise ValueError('unit_amount es obligatorio cuando no se envía stripe_price_id.')
            price = stripe.Price.create(product=stripe_product_id, unit_amount=unit_amount, currency=currency.lower(), recurring={'interval': interval})
            stripe_price_id = price.id
        payment_link = stripe.PaymentLink.create(line_items=[{'price': stripe_price_id, 'quantity': 1}], metadata={'product_slug': normalized_slug, 'plan': normalized_plan})
        await self.mongo.stripe_products.update_one({'slug': normalized_slug}, {'$set': {'slug': normalized_slug, 'name': name, 'description': description, 'plan_code': normalized_plan, 'stripe_product_id': stripe_product_id, 'stripe_price_id': stripe_price_id, 'stripe_payment_link': payment_link.url, 'unit_amount': unit_amount, 'currency': currency.lower(), 'interval': interval, 'active': active, 'updated_at': now}, '$setOnInsert': {'created_at': now}}, upsert=True)
        saved = await self.mongo.stripe_products.find_one({'slug': normalized_slug})
        return self._serialize_product(saved)

    async def delete_product(self, slug: str) -> bool:
        normalized = self._normalize_slug(slug)
        if not normalized:
            return False
        result = await self.mongo.stripe_products.delete_one({'slug': normalized})
        return result.deleted_count > 0

    async def add_characteristics_products(self, id: str, new_value: str):
        if not ObjectId.is_valid(id):
            raise HTTPException(400, 'ID de producto no válido')
        result = await self.mongo.stripe_products.find_one_and_update({'_id': ObjectId(id)}, {'$addToSet': {'characteristics': new_value}}, return_document=True)
        if not result:
            raise HTTPException(404, 'Producto no encontrado')
        return PlanCharacteristics.model_validate(result)

    async def update_characteristics_products(self, id: str, body_id: int, body_value: str):
        field = f'characteristics.{body_id}'
        result = await self.mongo.stripe_products.update_one({'_id': ObjectId(id)}, {'$set': {field: body_value}})
        if result.matched_count == 0:
            raise HTTPException(404, 'Plan no encontrado')
        doc = await self.mongo.stripe_products.find_one({'_id': ObjectId(id)}, {'characteristics': 1, '_id': 0})
        return doc

    async def get_characteristics_products(self, id: str):
        data = await self.mongo.stripe_products.find_one({'_id': ObjectId(id)}, {'characteristics': 1, '_id': 0})
        if data is None:
            raise HTTPException(404, 'Plan no encontrado')
        return PlanCharacteristics.model_validate(data)

    async def delete_characteristics_products(self, id: str, body_id: int):
        data = await self.get_characteristics_products(id)
        try:
            char_to_delete = data.characteristics[body_id]
            _result = await self.mongo.stripe_products.find_one_and_update({'_id': ObjectId(id)}, {'$pull': {'characteristics': char_to_delete}}, return_document=True)
            return {'success': True, 'delete': char_to_delete}
        except IndexError:
            raise HTTPException(404, 'Index fuera de rango')
        except Exception as e:
            raise HTTPException(500, f'Error no manejado: {e}')

    async def get_or_create_payment_link(self, slug: str) -> str:
        product = await self.get_product_by_slug(slug)
        if not product:
            raise ValueError('Producto no encontrado.')
        if product.get('stripe_payment_link'):
            return product['stripe_payment_link']
        if not product.get('stripe_price_id'):
            raise ValueError('El producto no tiene stripe_price_id configurado.')
        payment_link = stripe.PaymentLink.create(line_items=[{'price': product['stripe_price_id'], 'quantity': 1}], metadata={'product_slug': product['slug'], 'plan': product.get('plan_code') or product['slug']})
        await self.mongo.stripe_products.update_one({'slug': product['slug']}, {'$set': {'stripe_payment_link': payment_link.url, 'updated_at': self._now_utc()}})
        return payment_link.url

    async def create_checkout_for_product_slug(self, *, user_id: str, email: str, product_slug: str, success_url: str, cancel_url: str) -> str:
        product = await self.get_product_by_slug(product_slug)
        if not product or not product.get('active', True):
            raise ValueError('Producto no disponible para cobro.')
        if product.get('is_free') or product.get('unit_amount', 1) == 0:
            raise ValueError('El plan gratuito no requiere checkout. Asigna el plan directamente al registrar al usuario.')
        price_id = product.get('stripe_price_id')
        if not price_id:
            raise ValueError('El producto no tiene stripe_price_id configurado.')
        plan_code = product.get('plan_code') or product['slug']
        session = stripe.checkout.Session.create(customer_email=email, payment_method_types=['card'], mode='subscription', line_items=[{'price': price_id, 'quantity': 1}], success_url=success_url, cancel_url=cancel_url, metadata={'user_id': user_id, 'plan': plan_code, 'product_slug': product['slug']})
        await self.mongo.payments.insert_one({'user_id': user_id, 'stripe_session_id': session.id, 'plan': plan_code, 'product_slug': product['slug'], 'status': 'pending', 'created_at': self._now_utc()})
        return session.url

    async def _downgrade_to_free(self, customer_id: Optional[str]) -> None:
        """Degrada a un usuario a 'free' cuando su suscripción se cancela o queda impaga."""
        if not customer_id:
            return
        result = await self.mongo[Collections.USERS].update_one(
            {'subscription.stripe_customer_id': customer_id},
            {'$set': {'plan': 'free', 'subscription.active': False, 'subscription.status': 'canceled', 'updated_at': self._now_utc()}},
        )
        if result.modified_count:
            logger.info(f'[WEBHOOK] Usuario degradado a free (customer={customer_id})')

    async def handle_webhook_event(self, event):
        """Maneja los eventos asíncronos enviados por Stripe. Idempotente por event['id']."""
        event_id = event.get('id')
        if event_id:
            try:
                await self.mongo[Collections.STRIPE_EVENTS].insert_one(
                    {'_id': event_id, 'type': event.get('type'), 'received_at': self._now_utc()}
                )
            except DuplicateKeyError:
                logger.info(f'[WEBHOOK] Evento duplicado ignorado: {event_id}')
                return
        event_type = event['type']
        obj = event['data']['object']
        if event_type == 'checkout.session.completed':
            logger.info(f'[WEBHOOK] checkout.session.completed: {obj.id}')
            user_id = obj.metadata.get('user_id') if obj.metadata else None
            plan = obj.metadata.get('plan') if obj.metadata else None
            product_slug = obj.metadata.get('product_slug') if obj.metadata else None
            if not plan and product_slug:
                plan = await self.resolve_plan_code_from_slug(product_slug)
            if obj.subscription and user_id and plan:
                logger.info(f'💳 PAGO COMPLETADO | Usuario: {user_id} | Plan: {plan} | Suscripción: {obj.subscription}')
                await self.finalize_subscription(obj.subscription, user_id, plan, obj.customer)
            await self.mongo.payments.update_one({'stripe_session_id': obj.id}, {'$set': {'status': 'completed', 'plan': plan, 'product_slug': product_slug, 'completed_at': self._now_utc()}})
            logger.info(f'[WEBHOOK] Pago registrado: usuario={user_id}, plan={plan}')
        elif event_type == 'invoice.payment_succeeded':
            logger.info(f'[WEBHOOK] invoice.payment_succeeded: {obj.id}')
            user_id = obj.metadata.get('user_id') if obj.metadata else None
            amount_paid = obj.amount_paid / 100 if obj.amount_paid else 0
            currency = obj.currency or 'usd'
            logger.info(f'💰 PAGO FACTURA | Usuario: {user_id} | Monto: {amount_paid} {currency.upper()} | Factura: {obj.id}')
            try:
                await self.mongo.invoices.insert_one({'user_id': user_id, 'stripe_invoice_id': obj.id, 'stripe_subscription_id': obj.subscription, 'amount_paid': amount_paid, 'currency': currency, 'pdf_url': obj.invoice_pdf, 'status': 'paid', 'created_at': self._now_utc()})
            except Exception as e:
                logger.error(f'[WEBHOOK] Error guardando invoice: {str(e)}')
        elif event_type == 'customer.subscription.updated':
            status = obj.get('status')
            customer_id = obj.get('customer')
            logger.info(f'[WEBHOOK] customer.subscription.updated status={status} customer={customer_id}')
            if status == 'past_due':
                # Tarjeta rechazada: se mantiene el acceso, solo se marca para avisar al usuario.
                await self.mongo[Collections.USERS].update_one(
                    {'subscription.stripe_customer_id': customer_id},
                    {'$set': {'subscription.status': 'past_due', 'updated_at': self._now_utc()}},
                )
            elif status in ('canceled', 'unpaid'):
                await self._downgrade_to_free(customer_id)
        elif event_type == 'customer.subscription.deleted':
            customer_id = obj.get('customer')
            logger.info(f'[WEBHOOK] customer.subscription.deleted customer={customer_id}')
            await self._downgrade_to_free(customer_id)

    async def sync_from_session_id(self, session_id: str):
        """Sincroniza la DB inmediatamente después de un pago exitoso (UX proactiva)."""
        try:
            logger.info(f'[STEP 1/5] 🔍 Recuperando sesión de Stripe | Session ID: {session_id}')
            session = stripe.checkout.Session.retrieve(session_id)
            logger.info(f'[STEP 2/5] ✓ Sesión recuperada | Estado: {session.payment_status}')
            if session.payment_status == 'paid':
                user_id = session.metadata.get('user_id')
                plan = session.metadata.get('plan')
                product_slug = session.metadata.get('product_slug')
                logger.info(f'[STEP 3/5] 📋 Extrayendo datos | Usuario: {user_id} | Plan: {plan} | Producto: {product_slug}')
                if not plan and product_slug:
                    plan = await self.resolve_plan_code_from_slug(product_slug)
                    logger.info(f'[STEP 3/5] 📋 Plan resuelto desde slug: {plan}')
                if session.subscription and user_id and plan:
                    logger.info(f'[STEP 4/5] 💾 Actualizando suscripción en BD | Usuario: {user_id} | Plan: {plan}')
                    await self.finalize_subscription(session.subscription, user_id, plan, session.customer)
                    logger.info(f'[STEP 5/5] ✅ Suscripción finalizada exitosamente')
                    logger.info(f'[STEP 5.5] 📧 Enviando factura por correo...')
                    user = await self.mongo[Collections.USERS].find_one({'_id': ObjectId(user_id)})
                    if user and user.get('email'):
                        user_name = user.get('name', 'Usuario')
                        user_email = user.get('email')
                        await self.send_invoice_email(user_email, user_name, plan, session.subscription, session_id)
                    else:
                        logger.warning(f'⚠️  No se encontró email del usuario {user_id}')
            else:
                logger.warning(f'⚠️  Sesión no pagada | Estado: {session.payment_status}')
        except Exception as e:
            logger.error(f'❌ Error en sincronización manual: {str(e)}')
            raise

    async def finalize_subscription(self, stripe_sub_id: str, user_id: str, plan: str, customer_id: str):
        """Actualiza el documento del usuario con los privilegios del nuevo plan."""
        try:
            logger.info(f'  [4.1] Recuperando detalles de suscripción Stripe | Suscripción: {stripe_sub_id}')
            sub = stripe.Subscription.retrieve(stripe_sub_id)
            update_data = {'plan': plan, 'subscription.active': True, 'subscription.stripe_subscription_id': stripe_sub_id, 'subscription.stripe_customer_id': customer_id, 'updated_at': self._now_utc()}
            if hasattr(sub, 'current_period_end') and sub.current_period_end:
                end_date = datetime.fromtimestamp(sub.current_period_end, tz=timezone.utc)
                update_data['subscription.end_date'] = end_date
                logger.info(f"  [4.2] Fecha de vencimiento: {end_date.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f'  [4.3] Actualizando documento de usuario en MongoDB')
            result = await self.mongo[Collections.USERS].update_one({'_id': ObjectId(user_id)}, {'$set': update_data})
            if result.modified_count > 0:
                logger.info(f'  [4.4] ✓ Usuario actualizado exitosamente')
                logger.info(f"💳 SUSCRIPCIÓN ACTIVADA | Usuario: {user_id} | Plan: {plan} | Activa hasta: {update_data.get('subscription.end_date', 'N/A')}")
            else:
                logger.warning(f'  [4.4] ⚠️  No se modificaron documentos (usuario podría no existir)')
        except Exception as e:
            logger.error(f'❌ Error finalizando suscripción: {str(e)}')
            raise

    async def send_cancellation_email(self, user_email: str, user_name: str, plan: str, stripe_subscription_id: str, benefits_until: Optional[datetime]=None) -> None:
        """Envía notificación de cancelación de suscripción al usuario."""
        try:
            logger.info(f'📧 Preparando notificación de cancelación | Usuario: {user_email} | Plan: {plan}')
            cancellation_date = datetime.now(timezone.utc).strftime('%d/%m/%Y')
            benefits_until_date = 'N/A'
            try:
                subscription = stripe.Subscription.retrieve(stripe_subscription_id, expand=['items'])
                logger.info(f"📅 Status Stripe: {subscription.get('status')}")
                period_end = None
                items = subscription.get('items', {})
                if items and items.get('data') and (len(items.get('data', [])) > 0):
                    first_item = items['data'][0]
                    logger.info(f"📅 Item 0 - current_period_end: {first_item.get('billing_cycle_anchor_config', {}).get('day_of_month')}")
                    if 'billing_cycle_anchor_config' in first_item:
                        logger.info(f'📅 Atributos del item: {list(first_item.keys())}')
                    period_end = first_item.get('current_period_end')
                    logger.info(f'📅 current_period_end del item: {period_end}')
                if not period_end:
                    period_end = subscription.get('billing_cycle_anchor')
                    logger.info(f'📅 Usando billing_cycle_anchor: {period_end}')
                if period_end:
                    logger.info(f'📅 Timestamp de Stripe: {period_end}')
                    benefits_until = datetime.fromtimestamp(period_end, tz=timezone.utc)
                    logger.info(f'✓ Fecha obtenida de Stripe: {benefits_until}')
                else:
                    logger.warning(f'⚠️  No se encontró período válido en Stripe')
            except Exception as stripe_error:
                logger.warning(f'⚠️  Error obteniendo datos de Stripe: {str(stripe_error)}', exc_info=True)
            if benefits_until:
                try:
                    if isinstance(benefits_until, datetime):
                        benefits_until_date = benefits_until.strftime('%d/%m/%Y')
                    else:
                        benefits_until_date = benefits_until.strftime('%d/%m/%Y')
                    logger.info(f'📅 Acceso disponible hasta: {benefits_until_date}')
                except Exception as date_error:
                    logger.warning(f'⚠️  Error procesando fecha: {str(date_error)}')
            else:
                logger.warning(f'⚠️  No se encontró fecha de vencimiento')
            template_path = os.path.join(os.path.dirname(__file__), '..', 'email_templates', 'cancellation.html')
            with open(template_path, 'r', encoding='utf-8') as f:
                html_template = f.read()
            html_body = html_template.replace('{{user_name}}', user_name)
            html_body = html_body.replace('{{plan}}', plan.upper())
            html_body = html_body.replace('{{cancellation_date}}', cancellation_date)
            html_body = html_body.replace('{{benefits_until_date}}', benefits_until_date)
            subject = f'🔔 Tu suscripción a HyperShifu {plan.upper()} ha sido cancelada'
            from email.message import EmailMessage
            from app.utils.mail import _smtp_from, _smtp_send, validate_smtp_config
            validate_smtp_config()
            msg = EmailMessage()
            msg['Subject'] = subject
            msg['From'] = f'HyperShifu Notificaciones <{_smtp_from()}>'
            msg['To'] = user_email
            msg.set_content('Este correo contiene información sobre tu cancelación de suscripción.')
            msg.add_alternative(html_body, subtype='html')
            _smtp_send(msg)
            logger.info(f'📧 Notificación de cancelación enviada a {user_email} | Acceso hasta: {benefits_until_date}')
        except Exception as e:
            logger.error(f'❌ Error enviando notificación de cancelación: {str(e)}', exc_info=True)

    async def cancel_subscription(self, user_id: str, at_period_end: bool=True) -> dict:
        """Cancela la suscripción de un usuario."""
        try:
            user = await self.mongo[Collections.USERS].find_one({'_id': ObjectId(user_id)})
            if not user:
                raise ValueError('Usuario no encontrado')
            stripe_sub_id = user.get('subscription', {}).get('stripe_subscription_id')
            if not stripe_sub_id:
                raise ValueError('El usuario no tiene una suscripción activa')
            if at_period_end:
                cancelled_sub = stripe.Subscription.modify(stripe_sub_id, cancel_at_period_end=True)
            else:
                cancelled_sub = stripe.Subscription.delete(stripe_sub_id)
            update_data = {'subscription.active': False, 'subscription.cancelled_at': self._now_utc(), 'subscription.cancel_at_period_end': at_period_end, 'subscription.status': 'cancelled', 'updated_at': self._now_utc()}
            if not at_period_end:
                update_data['plan'] = 'free'
            await self.mongo[Collections.USERS].update_one({'_id': ObjectId(user_id)}, {'$set': update_data})
            logger.info(f'Suscripción cancelada para usuario {user_id} (at_period_end={at_period_end})')
            try:
                user_email = user.get('email')
                user_name = user.get('name', 'Usuario')
                plan = user.get('plan', 'basic')
                benefits_until = user.get('subscription', {}).get('end_date')
                if user_email:
                    await self.send_cancellation_email(user_email, user_name, plan, stripe_sub_id, benefits_until)
                else:
                    logger.warning(f'⚠️  No se encontró email del usuario {user_id} para enviar notificación de cancelación')
            except Exception as e:
                logger.error(f'⚠️  Error enviando notificación de cancelación: {str(e)}')
            return {'success': True, 'message': 'Suscripción cancelada exitosamente', 'cancelled_at': cancelled_sub.cancelled_at if hasattr(cancelled_sub, 'cancelled_at') else None, 'cancel_at_period_end': cancelled_sub.cancel_at_period_end if hasattr(cancelled_sub, 'cancel_at_period_end') else None}
        except ValueError as ve:
            logger.error(f'Error cancelando suscripción: {str(ve)}')
            raise
        except Exception as e:
            logger.error(f'Error cancelando suscripción: {str(e)}')
            raise

    async def change_subscription(self, user_id: str, new_plan: str, email: str) -> dict:
        """Cambia el plan de suscripción de un usuario (cancela la actual y crea nueva checkout session)."""
        try:
            user = await self.mongo[Collections.USERS].find_one({'_id': ObjectId(user_id)})
            if not user:
                raise ValueError('Usuario no encontrado')
            stripe_sub_id = user.get('subscription', {}).get('stripe_subscription_id')
            if stripe_sub_id:
                try:
                    stripe.Subscription.modify(stripe_sub_id, cancel_at_period_end=False)
                    stripe.Subscription.delete(stripe_sub_id)
                except Exception as e:
                    logger.warning(f'No se pudo cancelar suscripción anterior {stripe_sub_id}: {e}')
            product = await self.mongo['stripe_products'].find_one({'slug': new_plan})
            if not product:
                product = await self.mongo['stripe_products'].find_one({'plan_code': new_plan})
            if not product or not product.get('stripe_price_id'):
                raise ValueError(f'Plan "{new_plan}" no encontrado o sin precio configurado')
            checkout_url = await self.create_checkout_for_product_slug(
                user_id=user_id,
                email=email,
                product_slug=product['slug'],
                success_url=f'{Config.FRONTEND_URL or "http://localhost:5173"}/chat?paymentSuccess=true',
                cancel_url=f'{Config.FRONTEND_URL or "http://localhost:5173"}/pricing',
            )
            return {'success': True, 'checkout_url': checkout_url, 'message': f'Se creó sesión de checkout para plan {new_plan}'}
        except ValueError:
            raise
        except Exception as e:
            logger.error(f'Error cambiando suscripción: {str(e)}')
            raise

    async def reactivate_subscription(self, user_id: str, product_slug: str = None) -> dict:
        """Reactiva una suscripción cancelada (cancel_at_period_end)."""
        try:
            user = await self.mongo[Collections.USERS].find_one({'_id': ObjectId(user_id)})
            if not user:
                raise ValueError('Usuario no encontrado')
            stripe_sub_id = user.get('subscription', {}).get('stripe_subscription_id')
            if not stripe_sub_id:
                raise ValueError('El usuario no tiene una suscripción previa')
            try:
                sub = stripe.Subscription.retrieve(stripe_sub_id)
                if sub.status in ('canceled', 'unpaid'):
                    raise ValueError('La suscripción ya fue cancelada completamente. Se necesita una nueva suscripción.')
                stripe.Subscription.modify(stripe_sub_id, cancel_at_period_end=False)
            except stripe.error.InvalidRequestError:
                raise ValueError('La suscripción ya fue cancelada completamente. Se necesita una nueva suscripción.')
            await self.mongo[Collections.USERS].update_one(
                {'_id': ObjectId(user_id)},
                {'$set': {
                    'subscription.active': True,
                    'subscription.cancelled_at': None,
                    'subscription.cancel_at_period_end': False,
                    'subscription.status': 'active',
                    'updated_at': self._now_utc(),
                }}
            )
            logger.info(f'Suscripción reactivada para usuario {user_id}')
            return {'success': True, 'message': 'Suscripción reactivada exitosamente'}
        except ValueError:
            raise
        except Exception as e:
            logger.error(f'Error reactivando suscripción: {str(e)}')
            raise
