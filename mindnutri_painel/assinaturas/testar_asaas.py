"""
Script de teste da integração Asaas no ambiente sandbox.
Execute para validar que as credenciais e a integração estão corretas.

    python testar_asaas.py
"""
import os
import sys
from pathlib import Path

# Garante que o .env é carregado
sys.path.insert(0, str(Path(__file__).parent.parent / "mindnutri_agente"))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / "mindnutri_agente" / ".env")
except Exception:
    pass

from django.conf import settings as config
from asaas_client import asaas


def separador(titulo):
    print(f"\n{'─'*50}")
    print(f"  {titulo}")
    print('─'*50)


def main():
    print("=" * 50)
    print("  Mindnutri — Teste de Integração Asaas")
    print(f"  Ambiente: {'SANDBOX' if 'sandbox' in config.ASAAS_BASE_URL else 'PRODUÇÃO'}")
    print("=" * 50)

    if not config.ASAAS_API_KEY or config.ASAAS_API_KEY.startswith("COLOQUE"):
        print("\n❌ ASAAS_API_KEY não configurada no .env")
        print("   Configure a chave do Asaas Sandbox em:")
        print("   https://sandbox.asaas.com → Configurações → API")
        return

    erros = []

    # ── TESTE 1: Criar cliente ──────────────────────────────────
    separador("1. Criar cliente de teste")
    try:
        cliente = asaas.criar_cliente(
            nome="Teste Mindnutri",
            telefone="5511987654321",
            email="teste@mindnutri.com"
        )
        customer_id = cliente["id"]
        print(f"  ✓ Cliente criado: {customer_id}")
    except Exception as e:
        customer_id = None
        erros.append(f"Criar cliente: {e}")
        print(f"  ✗ Erro: {e}")

    if not customer_id:
        print("\n❌ Não foi possível criar cliente. Verifique a chave API.")
        return

    # ── TESTE 2: Buscar cliente ─────────────────────────────────
    separador("2. Buscar cliente por telefone")
    try:
        encontrado = asaas.buscar_cliente_por_telefone("5511987654321")
        if encontrado:
            print(f"  ✓ Cliente encontrado: {encontrado['name']}")
        else:
            print("  ⚠️  Cliente não encontrado (pode haver delay)")
    except Exception as e:
        erros.append(f"Buscar cliente: {e}")
        print(f"  ✗ Erro: {e}")

    # ── TESTE 3: Criar assinatura ───────────────────────────────
    separador("3. Criar assinatura mensal")
    subscription_id = None
    try:
        assinatura = asaas.criar_assinatura(
            customer_id=customer_id,
            valor=59.90,
            descricao="Mindnutri — Teste de assinatura",
        )
        subscription_id = assinatura["id"]
        print(f"  ✓ Assinatura criada: {subscription_id}")
        print(f"  ✓ Status: {assinatura.get('status')}")
    except Exception as e:
        erros.append(f"Criar assinatura: {e}")
        print(f"  ✗ Erro: {e}")

    # ── TESTE 4: Link de pagamento ──────────────────────────────
    separador("4. Obter link de pagamento")
    if subscription_id:
        try:
            link = asaas.link_pagamento_assinatura(subscription_id)
            if link:
                print(f"  ✓ Link gerado: {link[:60]}...")
            else:
                print("  ⚠️  Link não disponível (pode estar sendo gerado)")
        except Exception as e:
            erros.append(f"Link de pagamento: {e}")
            print(f"  ✗ Erro: {e}")

    # ── TESTE 5: Cobrança avulsa ────────────────────────────────
    separador("5. Criar cobrança avulsa")
    try:
        from datetime import date, timedelta
        cobranca = asaas.criar_cobranca(
            customer_id=customer_id,
            valor=59.90,
            descricao="Mindnutri — Teste cobrança avulsa",
            vencimento=date.today() + timedelta(days=7),
        )
        print(f"  ✓ Cobrança criada: {cobranca['id']}")
        print(f"  ✓ Valor: R$ {cobranca['value']:.2f}")
        print(f"  ✓ Vencimento: {cobranca['dueDate']}")
    except Exception as e:
        erros.append(f"Cobrança avulsa: {e}")
        print(f"  ✗ Erro: {e}")

    # ── TESTE 6: Cancelar assinatura de teste ───────────────────
    separador("6. Cancelar assinatura de teste")
    if subscription_id:
        try:
            asaas.cancelar_assinatura(subscription_id)
            print(f"  ✓ Assinatura de teste cancelada")
        except Exception as e:
            print(f"  ⚠️  Não cancelou (ok para sandbox): {e}")

    # ── RESULTADO ───────────────────────────────────────────────
    print(f"\n{'='*50}")
    if not erros:
        print("  ✅ Todos os testes passaram!")
        print("  A integração com o Asaas está funcionando.")
    else:
        print(f"  ⚠️  {len(erros)} erro(s) encontrado(s):")
        for e in erros:
            print(f"  • {e}")
    print('='*50)

    print("\n  Próximo passo:")
    print("  Configure o webhook do Asaas em:")
    print("  https://sandbox.asaas.com → Configurações → Webhooks")
    print("  URL: https://SEU_NGROK/webhook/asaas/")
    print("  Eventos: PAYMENT_CONFIRMED, PAYMENT_OVERDUE,")
    print("           SUBSCRIPTION_INACTIVATED")


if __name__ == "__main__":
    main()
