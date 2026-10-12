#!/bin/bash

# Script para verificar que el webhook de Stripe está funcionando correctamente

echo "🔍 Verificando configuración del Webhook de Stripe"
echo "=================================================="

# 1. Verificar que el backend está corriendo
echo ""
echo "1️⃣  Verificando que el backend esté corriendo..."
curl -s http://localhost:5000/health > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "✅ Backend está corriendo en http://localhost:5000"
else
    echo "❌ Backend NO está corriendo. Inicia: docker-compose up"
    exit 1
fi

# 2. Verificar que el .env tiene WEBHOOK_SECRET
echo ""
echo "2️⃣  Verificando WEBHOOK_SECRET en .env..."
if grep -q "WEBHOOK_SECRET=" .env; then
    WEBHOOK_SECRET=$(grep "WEBHOOK_SECRET=" .env | cut -d'=' -f2)
    if [ -n "$WEBHOOK_SECRET" ]; then
        echo "✅ WEBHOOK_SECRET configurado: $WEBHOOK_SECRET"
    else
        echo "❌ WEBHOOK_SECRET está vacío en .env"
        exit 1
    fi
else
    echo "❌ WEBHOOK_SECRET no encontrado en .env"
    exit 1
fi

# 3. Instrucciones para iniciar el CLI listener
echo ""
echo "3️⃣  Para activar los webhooks en local:"
echo ""
echo "   Abre OTRA terminal y ejecuta:"
echo ""
echo "   docker run --rm -it \\"
echo "     stripe/stripe-cli:latest listen \\"
echo "     --api-key sk_test_REEMPLAZAR \\"
echo "     --forward-to http://host.docker.internal:5000/api/v2/stripe/webhook"
echo ""

# 4. Instrucciones para probar
echo "4️⃣  Para disparar un evento de prueba:"
echo ""
echo "   docker run --rm -it \\"
echo "     stripe/stripe-cli:latest trigger \\"
echo "     --api-key sk_test_REEMPLAZAR \\"
echo "     checkout.session.completed"
echo ""

# 5. Comprobar logs
echo "5️⃣  Monitorear logs del backend:"
echo ""
echo "   docker-compose logs -f api"
echo ""

echo "=================================================="
echo "✅ Configuración verificada. Sigue los pasos anteriores."
