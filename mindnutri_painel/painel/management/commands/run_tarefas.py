import logging
import time
from datetime import datetime

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


class Command(BaseCommand):
    help = 'Tarefas agendadas Mindnutri (loop contínuo e verificações)'

    def add_arguments(self, parser):
        parser.add_argument("--verificar-vencimentos", action="store_true")
        parser.add_argument("--verificar-fichas", action="store_true")
        parser.add_argument("--resetar-fichas", action="store_true")
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--intervalo", type=int, default=60,
                            help="Intervalo em minutos para o loop (padrão: 60)")

    def handle(self, *args, **options):
        if options['verificar_vencimentos']:
            self._verificar_vencimentos()
        elif options['verificar_fichas']:
            self._verificar_fichas()
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

    def _loop_continuo(self, intervalo_minutos: int) -> None:
        logger.info("Iniciando loop a cada %d minutos...", intervalo_minutos)
        ultima_verificacao_dia = None

        while True:
            try:
                agora = datetime.now()
                self._verificar_fichas()

                hoje = agora.date()
                if agora.hour == 9 and ultima_verificacao_dia != hoje:
                    self._verificar_vencimentos()
                    resetar_fichas_mensais()
                    ultima_verificacao_dia = hoje

                time.sleep(intervalo_minutos * 60)
            except KeyboardInterrupt:
                logger.info("Loop encerrado pelo usuario.")
                break
            except Exception as e:
                logger.error("Erro no loop de tarefas: %s", e)
                time.sleep(60)
