"""
Cliente HTTP para a API do Asaas.
Cobre todas as operações necessárias para o Mindnutri:
- Clientes
- Assinaturas recorrentes
- Cobranças avulsas
- Consultas de status
"""
import requests
from datetime import date, timedelta
from typing import Optional
from django.conf import settings as config


class AsaasClient:
    def __init__(self):
        self.base_url = config.ASAAS_BASE_URL.rstrip("/")
        self.headers = {
            "access_token": config.ASAAS_API_KEY,
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict = None) -> dict:
        r = requests.get(
            f"{self.base_url}/{path}",
            headers=self.headers,
            params=params or {},
            timeout=20,
        )
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict) -> dict:
        r = requests.post(
            f"{self.base_url}/{path}",
            headers=self.headers,
            json=body,
            timeout=20,
        )
        r.raise_for_status()
        return r.json()

    def _delete(self, path: str) -> dict:
        r = requests.delete(
            f"{self.base_url}/{path}",
            headers=self.headers,
            timeout=20,
        )
        r.raise_for_status()
        return r.json()

    # ── CLIENTES ──────────────────────────────────────────────────

    def criar_cliente(self, nome: str, telefone: str,
                       email: str = None) -> dict:
        """Cria um cliente no Asaas."""
        fone = telefone.replace("+", "").replace("-", "").replace(" ", "")
        body = {
            "name": nome,
            "mobilePhone": fone,
            "notificationDisabled": False,
        }
        if email:
            body["email"] = email
        return self._post("customers", body)

    def buscar_cliente_por_telefone(self, telefone: str) -> Optional[dict]:
        """Busca cliente pelo telefone."""
        fone = telefone.replace("+", "").replace("-", "").replace(" ", "")
        data = self._get("customers", {"mobilePhone": fone})
        items = data.get("data", [])
        return items[0] if items else None

    def atualizar_cliente(self, customer_id: str, campos: dict) -> dict:
        r = requests.put(
            f"{self.base_url}/customers/{customer_id}",
            headers=self.headers,
            json=campos,
            timeout=20,
        )
        r.raise_for_status()
        return r.json()

    # ── ASSINATURAS ───────────────────────────────────────────────

    def criar_assinatura(self, customer_id: str, valor: float,
                          descricao: str = "Mindhub Mindnutri — Mensal") -> dict:
        """
        Cria assinatura mensal recorrente.
        billingType=UNDEFINED → cliente escolhe Pix ou cartão no link.
        """
        return self._post("subscriptions", {
            "customer":     customer_id,
            "billingType":  "UNDEFINED",
            "value":        valor,
            "nextDueDate":  date.today().isoformat(),
            "cycle":        "MONTHLY",
            "description":  descricao,
            "maxPayments":  None,  # Recorrente sem limite
        })

    def buscar_assinatura(self, subscription_id: str) -> dict:
        return self._get(f"subscriptions/{subscription_id}")

    def cancelar_assinatura(self, subscription_id: str) -> dict:
        return self._delete(f"subscriptions/{subscription_id}")

    def listar_pagamentos_assinatura(self, subscription_id: str) -> list:
        data = self._get(f"subscriptions/{subscription_id}/payments")
        return data.get("data", [])

    def link_pagamento_assinatura(self, subscription_id: str) -> str:
        """Retorna o link de pagamento da primeira cobrança pendente."""
        pagamentos = self.listar_pagamentos_assinatura(subscription_id)
        for p in pagamentos:
            if p.get("status") in ("PENDING", "OVERDUE"):
                return p.get("invoiceUrl") or p.get("bankSlipUrl", "")
        # Se nenhum pendente, retorna o primeiro
        if pagamentos:
            return pagamentos[0].get("invoiceUrl", "")
        return ""

    # ── COBRANÇAS AVULSAS ─────────────────────────────────────────

    def criar_cobranca(self, customer_id: str, valor: float,
                        descricao: str, vencimento: date = None) -> dict:
        """Cria cobrança avulsa (renovação antecipada, etc.)."""
        return self._post("payments", {
            "customer":    customer_id,
            "billingType": "UNDEFINED",
            "value":       valor,
            "dueDate":     (vencimento or date.today()).isoformat(),
            "description": descricao,
        })

    def buscar_cobranca(self, payment_id: str) -> dict:
        return self._get(f"payments/{payment_id}")

    # ── CONSULTAS ─────────────────────────────────────────────────

    def listar_cobrancas_vencendo(self, dias: int = 3) -> list:
        """Lista cobranças que vencem nos próximos N dias."""
        ate = (date.today() + timedelta(days=dias)).isoformat()
        data = self._get("payments", {
            "status": "PENDING",
            "dueDateLe": ate,
            "dueDateGe": date.today().isoformat(),
        })
        return data.get("data", [])

    def listar_inadimplentes(self) -> list:
        """Lista cobranças em atraso."""
        data = self._get("payments", {"status": "OVERDUE"})
        return data.get("data", [])


# Instância global
asaas = AsaasClient()
