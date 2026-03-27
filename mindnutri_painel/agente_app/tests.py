"""
Testes unitários das funções core do Mindnutri.
Cobre: normalização de ingredientes, processamento de mídia,
       fluxo de decisão, helpers e idempotência de webhook.

Executar: python manage.py test agente_app
"""
from unittest.mock import patch, MagicMock
from django.test import TestCase, RequestFactory
from django.conf import settings

from agente_app.nucleo import (
    _quer_comecar_do_zero,
    _eh_resposta_sim,
    _eh_resposta_nao,
    _normalizar_lista_modo_preparo,
    _formatar_qtd_operacional,
    _montar_ingredientes_operacionais,
    _calcular_custo_total,
    _montar_resumo_calculado,
    _processar_midia,
    _interpretar_metodo_pagamento,
)
from agente_app.gerador.xlsx_gerador import _normalizar_ingrediente, _safe_float


# ── HELPERS DE DETECÇÃO ──────────────────────────────────────────

class HelpersDeteccaoTest(TestCase):
    def test_quer_comecar_do_zero(self):
        self.assertTrue(_quer_comecar_do_zero("quero começar do zero"))
        self.assertTrue(_quer_comecar_do_zero("REINICIAR"))
        self.assertTrue(_quer_comecar_do_zero("apagar tudo"))
        self.assertFalse(_quer_comecar_do_zero("oi"))
        self.assertFalse(_quer_comecar_do_zero(""))
        self.assertFalse(_quer_comecar_do_zero(None))

    def test_eh_resposta_sim(self):
        self.assertTrue(_eh_resposta_sim("sim"))
        self.assertTrue(_eh_resposta_sim("Sim!"))
        self.assertTrue(_eh_resposta_sim("quero"))
        self.assertTrue(_eh_resposta_sim("pode gerar"))
        self.assertTrue(_eh_resposta_sim("OK"))
        self.assertFalse(_eh_resposta_sim("não"))
        self.assertFalse(_eh_resposta_sim(""))

    def test_eh_resposta_nao(self):
        self.assertTrue(_eh_resposta_nao("não"))
        self.assertTrue(_eh_resposta_nao("nao"))
        self.assertTrue(_eh_resposta_nao("agora não"))
        self.assertFalse(_eh_resposta_nao("sim"))
        self.assertFalse(_eh_resposta_nao(""))


# ── NORMALIZAÇÃO DE INGREDIENTES (XLSX) ─────────────────────────

class NormalizarIngredienteTest(TestCase):
    def test_converte_gramas_para_kg(self):
        ing = _normalizar_ingrediente({
            "nome": "Farinha",
            "unidade": "g",
            "peso_liquido": 500,
            "peso_bruto": 0,
            "fc": 1.0,
            "ic": 1.0,
            "custo_unit": 5.0,
        })
        self.assertEqual(ing["unidade"], "kg")
        self.assertAlmostEqual(ing["peso_liquido"], 0.5)

    def test_converte_ml_para_litros(self):
        ing = _normalizar_ingrediente({
            "nome": "Leite",
            "unidade": "ml",
            "peso_liquido": 200,
            "peso_bruto": 0,
            "fc": 1.0,
            "ic": 1.0,
            "custo_unit": 6.0,
        })
        self.assertEqual(ing["unidade"], "L")
        self.assertAlmostEqual(ing["peso_liquido"], 0.2)

    def test_calcula_peso_bruto_com_fc(self):
        ing = _normalizar_ingrediente({
            "nome": "Carne",
            "unidade": "kg",
            "peso_liquido": 1.0,
            "peso_bruto": 0,
            "fc": 1.35,
            "ic": 1.0,
            "custo_unit": 42.0,
        })
        self.assertAlmostEqual(ing["peso_bruto"], 1.35, places=2)

    def test_nao_altera_kg_e_litro(self):
        ing = _normalizar_ingrediente({
            "nome": "Agua",
            "unidade": "L",
            "peso_liquido": 2.0,
            "peso_bruto": 2.0,
            "fc": 1.0,
            "ic": 1.0,
            "custo_unit": 0,
        })
        # _normalizar_ingrediente lowercases units; "L" becomes "l"
        self.assertEqual(ing["unidade"], "l")
        self.assertAlmostEqual(ing["peso_liquido"], 2.0)

    def test_safe_float(self):
        self.assertEqual(_safe_float(3.14), 3.14)
        self.assertEqual(_safe_float("abc", 0.0), 0.0)
        self.assertEqual(_safe_float(None, 1.0), 1.0)
        self.assertEqual(_safe_float("", 0.0), 0.0)


# ── MODO DE PREPARO ──────────────────────────────────────────────

class ModoPreparoTest(TestCase):
    def test_separa_por_linhas(self):
        texto = "Misture os ingredientes\nLeve ao forno\nSirva quente"
        passos = _normalizar_lista_modo_preparo(texto)
        self.assertEqual(len(passos), 3)
        self.assertEqual(passos[0], "Misture os ingredientes")

    def test_remove_numeracao(self):
        texto = "1. Misture\n2. Asse\n3. Sirva"
        passos = _normalizar_lista_modo_preparo(texto)
        self.assertEqual(passos[0], "Misture")
        self.assertEqual(passos[1], "Asse")

    def test_texto_vazio(self):
        self.assertEqual(_normalizar_lista_modo_preparo(""), [])
        self.assertEqual(_normalizar_lista_modo_preparo(None), [])

    def test_lista_input(self):
        result = _normalizar_lista_modo_preparo(["Passo 1", "Passo 2"])
        self.assertEqual(result, ["Passo 1", "Passo 2"])

    def test_separacao_por_ponto_virgula(self):
        texto = "Misture tudo; Leve ao forno; Sirva"
        passos = _normalizar_lista_modo_preparo(texto)
        self.assertEqual(len(passos), 3)


# ── FORMATAÇÃO DE QUANTIDADE OPERACIONAL ─────────────────────────

class FormatarQtdTest(TestCase):
    def test_kg_menor_que_1_vira_gramas(self):
        self.assertEqual(_formatar_qtd_operacional(0.5, "kg"), "500g")
        self.assertEqual(_formatar_qtd_operacional(0.15, "kg"), "150g")

    def test_kg_maior_que_1_permanece(self):
        self.assertEqual(_formatar_qtd_operacional(1.5, "kg"), "1.5kg")

    def test_litro_menor_que_1_vira_ml(self):
        self.assertEqual(_formatar_qtd_operacional(0.2, "L"), "200ml")

    def test_string_input(self):
        result = _formatar_qtd_operacional("abc", "kg")
        self.assertEqual(result, "abc kg")


# ── CÁLCULO DE CUSTO TOTAL ───────────────────────────────────────

class CalculoCustoTest(TestCase):
    def test_custo_total_simples_sem_fc(self):
        """Sem FC (default 1.0), peso_bruto = peso_liquido."""
        dados = {
            "ingredientes": [
                {"custo_unit": 10.0, "peso_liquido": 0.5},
                {"custo_unit": 20.0, "peso_liquido": 0.3},
            ]
        }
        self.assertAlmostEqual(_calcular_custo_total(dados), 11.0)

    def test_custo_total_com_fc(self):
        """Custo deve ser custo_unit × peso_bruto (peso_liquido × FC)."""
        dados = {
            "ingredientes": [
                {"custo_unit": 42.0, "peso_liquido": 0.15, "fc": 1.22},
            ]
        }
        # 42.0 × (0.15 × 1.22) = 42.0 × 0.183 = 7.686
        self.assertAlmostEqual(_calcular_custo_total(dados), 7.69, places=2)

    def test_custo_total_com_peso_bruto_explicito(self):
        """Se peso_bruto já veio calculado, usa direto."""
        dados = {
            "ingredientes": [
                {"custo_unit": 42.0, "peso_bruto": 0.183, "peso_liquido": 0.15, "fc": 1.22},
            ]
        }
        # 42.0 × 0.183 = 7.686
        self.assertAlmostEqual(_calcular_custo_total(dados), 7.69, places=2)

    def test_custo_total_sem_ingredientes(self):
        self.assertEqual(_calcular_custo_total({}), 0.0)

    def test_montar_ingredientes_operacionais(self):
        dados = {
            "ingredientes": [
                {"nome": "Farinha", "peso_liquido": 0.5, "unidade": "kg"},
                {"nome": "Leite", "peso_liquido": 0.2, "unidade": "L"},
            ]
        }
        result = _montar_ingredientes_operacionais(dados)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["nome"], "Farinha")
        self.assertEqual(result[0]["qtd"], "500g")
        self.assertEqual(result[1]["qtd"], "200ml")


# ── RESUMO CALCULADO POR CÓDIGO ──────────────────────────────────

class ResumoCalculadoTest(TestCase):
    def test_resumo_custo_correto_com_fc(self):
        """Resumo deve usar peso_bruto (pl × FC) para custo."""
        dados = {
            "nome_prato": "Torta Nordestina",
            "ingredientes": [
                {"nome": "Carne seca", "peso_liquido": 0.5, "fc": 1.05, "ic": 1.0, "custo_unit": 80.0, "unidade": "kg"},
                {"nome": "Cebola", "peso_liquido": 0.3, "fc": 1.20, "ic": 1.0, "custo_unit": 5.0, "unidade": "kg"},
            ],
            "rendimento_porcoes": 10,
        }
        resumo = _montar_resumo_calculado(dados)
        # Carne: 0.5 × 1.05 = 0.525 × 80 = 42.00
        # Cebola: 0.3 × 1.20 = 0.36 × 5 = 1.80
        # Total: 43.80
        self.assertIn("R$ 42.00", resumo)
        self.assertIn("R$ 1.80", resumo)
        self.assertIn("R$ 43.80", resumo)
        self.assertIn("Porcoes: 10", resumo)
        self.assertIn("R$ 4.38", resumo)  # 43.80 / 10

    def test_resumo_porcoes_calculadas(self):
        """3kg rendimento / 0.3kg porção = 10 porções, não 3."""
        dados = {
            "nome_prato": "Torta",
            "ingredientes": [
                {"nome": "Massa", "peso_liquido": 3.0, "fc": 1.0, "ic": 1.0, "custo_unit": 10.0, "unidade": "kg"},
            ],
            "rendimento_porcoes": 10,
            "peso_porcao_kg": 0.3,
        }
        resumo = _montar_resumo_calculado(dados)
        self.assertIn("Porcoes: 10", resumo)
        self.assertIn("R$ 3.00", resumo)  # 30.00 / 10

    def test_resumo_sem_porcoes(self):
        """Sem rendimento_porcoes mas com peso_porcao, calcula automaticamente."""
        dados = {
            "nome_prato": "Bolo",
            "ingredientes": [
                {"nome": "Farinha", "peso_liquido": 1.0, "fc": 1.0, "ic": 1.0, "custo_unit": 5.0, "unidade": "kg"},
            ],
            "peso_porcao_kg": 0.1,
        }
        resumo = _montar_resumo_calculado(dados)
        # rendimento = 1.0 × IC 1.0 = 1.0kg, porção 0.1kg → 10 porções
        self.assertIn("Porcoes: 10", resumo)

    def test_resumo_sem_ingredientes(self):
        dados = {"nome_prato": "Vazio", "ingredientes": []}
        resumo = _montar_resumo_calculado(dados)
        self.assertIn("R$ 0.00", resumo)


# ── PROCESSAMENTO DE MÍDIA ───────────────────────────────────────

class ProcessarMidiaTest(TestCase):
    def test_texto_passa_direto(self):
        texto, tipo = _processar_midia("5511999999", "texto", "oi", None, "inicio")
        self.assertEqual(texto, "oi")
        self.assertEqual(tipo, "texto")

    @patch("agente_app.nucleo.midia.transcrever_audio", return_value="texto transcrito")
    def test_audio_transcreve(self, mock_whisper):
        texto, tipo = _processar_midia("5511999999", "audio", None, b"audio_bytes", "inicio")
        self.assertEqual(texto, "texto transcrito")
        mock_whisper.assert_called_once_with(b"audio_bytes")

    @patch("agente_app.nucleo.whatsapp.enviar_texto")
    @patch("agente_app.nucleo.midia.transcrever_audio", return_value=None)
    def test_audio_falha_retorna_none(self, mock_whisper, mock_enviar):
        texto, tipo = _processar_midia("5511999999", "audio", None, b"audio", "inicio")
        self.assertIsNone(texto)

    @patch("agente_app.nucleo.whatsapp.enviar_texto")
    def test_imagem_sem_bytes_retorna_none(self, mock_enviar):
        texto, tipo = _processar_midia("5511999999", "imagem", None, None, "inicio")
        self.assertIsNone(texto)

    def test_documento_retorna_texto(self):
        texto, tipo = _processar_midia("5511999999", "documento", None, b"pdf_bytes", "inicio")
        self.assertIn("DOCUMENTO ENVIADO", texto)

    @patch("agente_app.nucleo._salvar_foto_prato_operacional", return_value="/path/foto.jpg")
    def test_foto_no_fluxo_operacional(self, mock_salvar):
        texto, tipo = _processar_midia(
            "5511999999", "imagem", None, b"img_bytes", "aguardando_foto_operacional"
        )
        self.assertIn("[FOTO_PRATO]", texto)
        self.assertEqual(tipo, "texto")


# ── MÉTODO DE PAGAMENTO ──────────────────────────────────────────

class MetodoPagamentoTest(TestCase):
    def test_cartao(self):
        self.assertEqual(_interpretar_metodo_pagamento("1"), "cartao")
        self.assertEqual(_interpretar_metodo_pagamento("cartão de crédito"), "cartao")
        self.assertEqual(_interpretar_metodo_pagamento("cartao"), "cartao")

    def test_pix(self):
        self.assertEqual(_interpretar_metodo_pagamento("2"), "pix")
        self.assertEqual(_interpretar_metodo_pagamento("pix"), "pix")
        self.assertEqual(_interpretar_metodo_pagamento("quero pix"), "pix")

    def test_invalido(self):
        self.assertIsNone(_interpretar_metodo_pagamento("boleto"))
        self.assertIsNone(_interpretar_metodo_pagamento(""))


# ── IDEMPOTÊNCIA WEBHOOK ─────────────────────────────────────────

class WebhookIdempotenciaTest(TestCase):
    def test_registrar_e_verificar(self):
        from painel.models import WebhookProcessado
        evento_id = "PAYMENT_CONFIRMED:pay_test_123"

        self.assertFalse(WebhookProcessado.ja_processado(evento_id))
        WebhookProcessado.registrar(evento_id, "PAYMENT_CONFIRMED")
        self.assertTrue(WebhookProcessado.ja_processado(evento_id))

    def test_registrar_duplicado_nao_quebra(self):
        from painel.models import WebhookProcessado
        evento_id = "PAYMENT_RECEIVED:pay_dup_456"

        WebhookProcessado.registrar(evento_id, "PAYMENT_RECEIVED")
        WebhookProcessado.registrar(evento_id, "PAYMENT_RECEIVED")  # não deve dar erro
        self.assertEqual(
            WebhookProcessado.objects.filter(evento_id=evento_id).count(), 1
        )

    def test_limpar_antigos(self):
        from painel.models import WebhookProcessado
        from django.utils import timezone
        from datetime import timedelta

        # Cria um registro "antigo"
        wh = WebhookProcessado.objects.create(
            evento_id="OLD:test", evento_tipo="OLD"
        )
        WebhookProcessado.objects.filter(pk=wh.pk).update(
            processado_em=timezone.now() - timedelta(days=60)
        )

        removidos = WebhookProcessado.limpar_antigos(dias=30)
        self.assertEqual(removidos, 1)
