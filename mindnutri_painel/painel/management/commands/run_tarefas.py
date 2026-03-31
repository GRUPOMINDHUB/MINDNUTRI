import logging
import time
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from assinaturas.servico_assinaturas import verificar_vencimentos, verificar_limites_fichas

logger = logging.getLogger(__name__)


def resetar_fichas_mensais() -> None:
    """Reseta fichas mensais dos assinantes cuja cobrança vence hoje."""
    from datetime import timedelta
    from painel.models import Assinante

    logger.info("Resetando fichas mensais...")
    try:
        hoje = timezone.localdate()
        assinantes = Assinante.objects.filter(status='ativo', proxima_cobranca=hoje)
        atualizados = 0
        for a in assinantes:
            a.fichas_geradas_mes = 0
            if a.proxima_cobranca:
                a.proxima_cobranca = a.proxima_cobranca + timedelta(days=30)
            a.save()
            atualizados += 1
        logger.info("Fichas resetadas: %d assinante(s)", atualizados)
    except Exception as e:
        logger.error("Erro ao resetar fichas: %s", e)


def verificar_fichas_subutilizadas() -> None:
    """
    Verifica assinantes cujo prazo de 30 dias JÁ VENCEU e usaram
    menos de 50% das fichas disponíveis.
    Envia alerta para o grupo de suporte no WhatsApp.
    """
    from painel.models import Assinante
    from utils.alertas_grupo import alertar_negocio

    logger.info("Verificando fichas sub-utilizadas...")
    try:
        hoje = timezone.localdate()

        # Busca assinantes ativos cuja próxima cobrança já passou (prazo vencido)
        assinantes = Assinante.objects.filter(
            status='ativo',
            proxima_cobranca__lt=hoje,
        )

        alertados = 0
        for a in assinantes:
            limite = a.fichas_limite_mes or 30
            usadas = a.fichas_geradas_mes or 0
            percentual = (usadas / limite * 100) if limite > 0 else 0

            # Alerta se usou até 50% das fichas
            if percentual <= 50:
                nome = a.nome or a.telefone
                dias_vencido = (hoje - a.proxima_cobranca).days if a.proxima_cobranca else 0
                alertar_negocio(
                    "Fichas Sub-utilizadas",
                    "Prazo Vencido com Fichas Não Usadas",
                    f"Usou apenas {usadas}/{limite} fichas ({percentual:.0f}%).\n"
                    f"Prazo venceu há {dias_vencido} dia(s).",
                    telefone=a.telefone,
                    nome=nome,
                )
                alertados += 1

        logger.info("Fichas sub-utilizadas: %d alerta(s) enviado(s)", alertados)
    except Exception as e:
        logger.error("Erro ao verificar fichas sub-utilizadas: %s", e)


def verificar_pagamentos_pendentes() -> None:
    """
    Verifica usuários no estado 'aguardando_pagamento' há mais de 3 horas.
    Envia 1 único alerta por pagamento pendente (nunca repete).
    """
    from painel.models import EstadoConversa, Notificacao
    from utils.alertas_grupo import alertar_negocio
    from utils import banco

    logger.info("Verificando pagamentos pendentes...")
    try:
        limite = timezone.now() - timedelta(hours=3)

        pendentes = EstadoConversa.objects.filter(
            estado="aguardando_pagamento",
            atualizado_em__lt=limite,
        )

        alertados = 0
        for estado in pendentes:
            tel = estado.telefone

            # Só 1 alerta por pagamento pendente:
            # verifica se já tem notificação criada DEPOIS que entrou nesse estado
            ja_alertou = Notificacao.objects.filter(
                tipo="pagamento_pendente",
                assinante__telefone=tel,
                criada_em__gte=estado.atualizado_em,
            ).exists()
            if ja_alertou:
                continue

            assinante = banco.get_assinante(tel) or {}
            nome = assinante.get("nome", tel)
            horas = int((timezone.now() - estado.atualizado_em).total_seconds() / 3600)

            alertar_negocio(
                "Pagamento Pendente",
                "Pagamento Pendente há mais de 3h",
                f"Usuário está aguardando pagamento há {horas}h sem confirmação.",
                telefone=tel,
                nome=nome,
            )

            banco.criar_notificacao(
                "pagamento_pendente", "aviso",
                "Pagamento pendente",
                f"{nome} ({tel}) aguardando pagamento há {horas}h.",
                tel,
            )
            alertados += 1

        logger.info("Pagamentos pendentes: %d alerta(s) enviado(s)", alertados)
    except Exception as e:
        logger.error("Erro ao verificar pagamentos pendentes: %s", e)


class Command(BaseCommand):
    help = 'Tarefas agendadas Mindnutri (loop contínuo e verificações)'

    def add_arguments(self, parser):
        parser.add_argument("--verificar-vencimentos", action="store_true")
        parser.add_argument("--verificar-fichas", action="store_true")
        parser.add_argument("--verificar-fichas-subutilizadas", action="store_true")
        parser.add_argument("--verificar-pagamentos-pendentes", action="store_true")
        parser.add_argument("--resetar-fichas", action="store_true")
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--intervalo", type=int, default=60,
                            help="Intervalo em minutos para o loop (padrão: 60)")

    def handle(self, *args, **options):
        if options['verificar_vencimentos']:
            self._verificar_vencimentos()
        elif options['verificar_fichas']:
            self._verificar_fichas()
        elif options['verificar_fichas_subutilizadas']:
            self._verificar_fichas_subutilizadas()
        elif options['verificar_pagamentos_pendentes']:
            self._verificar_pagamentos_pendentes()
        elif options['resetar_fichas']:
            resetar_fichas_mensais()
        elif options['loop']:
            self._loop_continuo(options['intervalo'])
        else:
            self.stdout.write("Use --loop para rodar continuamente, ou uma flag específica.")

    def _verificar_vencimentos(self) -> None:
        logger.info("Verificando vencimentos...")
        try:
            verificar_vencimentos()
            logger.info("Verificacao de vencimentos concluida.")
        except Exception as e:
            logger.error("Erro ao verificar vencimentos: %s", e)

    def _verificar_fichas(self) -> None:
        logger.info("Verificando limites de fichas...")
        try:
            verificar_limites_fichas()
            logger.info("Verificacao de fichas concluida.")
        except Exception as e:
            logger.error("Erro ao verificar fichas: %s", e)

    def _verificar_fichas_subutilizadas(self) -> None:
        logger.info("Verificando fichas sub-utilizadas...")
        try:
            verificar_fichas_subutilizadas()
            logger.info("Verificacao de fichas sub-utilizadas concluida.")
        except Exception as e:
            logger.error("Erro ao verificar fichas sub-utilizadas: %s", e)

    def _verificar_pagamentos_pendentes(self) -> None:
        logger.info("Verificando pagamentos pendentes...")
        try:
            verificar_pagamentos_pendentes()
            logger.info("Verificacao de pagamentos pendentes concluida.")
        except Exception as e:
            logger.error("Erro ao verificar pagamentos pendentes: %s", e)

    def _loop_continuo(self, intervalo_minutos: int) -> None:
        logger.info("Iniciando loop a cada %d minutos...", intervalo_minutos)
        ultima_verificacao_dia = None

        while True:
            try:
                agora = datetime.now()
                self._verificar_fichas()
                self._verificar_pagamentos_pendentes()

                hoje = agora.date()
                if agora.hour == 9 and ultima_verificacao_dia != hoje:
                    self._verificar_vencimentos()
                    resetar_fichas_mensais()
                    self._verificar_fichas_subutilizadas()
                    ultima_verificacao_dia = hoje

                time.sleep(intervalo_minutos * 60)
            except KeyboardInterrupt:
                logger.info("Loop encerrado pelo usuario.")
                break
            except Exception as e:
                logger.error("Erro no loop de tarefas: %s", e)
                time.sleep(60)
