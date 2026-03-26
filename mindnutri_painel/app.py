from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from functools import wraps
from datetime import datetime, timedelta
import random

app = Flask(__name__)
app.secret_key = "mindnutri_secret_2024"

# ── Credenciais do admin ──────────────────────────────────────────
ADMIN_USER = "admin"
ADMIN_PASS = "mindhub2024"

# ── Dados mock de assinantes ─────────────────────────────────────
ASSINANTES = [
    {
        "id": 1, "nome": "Rodrigo Ferreira", "estabelecimento": "Burger Bros",
        "nicho": "Hambúrguer", "telefone": "+55 11 99876-5432",
        "instagram": "@burgerbros.sp", "cidade": "São Paulo - SP",
        "funcionarios": 8, "faturamento": "R$ 45.000",
        "status": "ativo", "plano": "Mensal R$89,90",
        "fichas_geradas": 18, "fichas_limite": 30,
        "data_inicio": "2024-02-10", "proxima_cobranca": "2024-03