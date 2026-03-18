import time
from datetime import datetime
from django.core.management.base import BaseCommand
from assinaturas.servico_assinaturas import verificar_vencimentos as _v
from assinaturas.servico_assinaturas import verificar_limites_fichas as _f
from django.utils import timezone
from datetime import date
from utils.banco import conn

def resetar_fichas_mensais():
    print(f"[{datetime.now():%H:%M:%S}] Resetando fichas mensais...")
    try:
        from painel.models import Assinante
        hoje = timezone.localdate()
        from datetime import timedelta
        
        assinantes = Assinante.objects.filter(status='ativo', proxima_cobranca=hoje)
        atualizados = 0
        for a in assinantes:
            a.fichas_geradas_mes = 0
            if a.proxima_cobranca:
                a.proxima_cobranca = a.proxima_cobranca + timedelta(days=30)
            a.save()
            atualizados += 1
            
        print(f"  ✓ {atualizados} assinante(s) renovado(s)")
    except Exception as e:
        print(f"  ✗ Erro: {e}")

class Command(BaseCommand):
    help = 'Tarefas agendadas Mindnutri (loop contínuo e verificações)'

    def add_arguments(self, parser):
        parser.add_argument("--verificar-vencimentos", action="store_true")
        parser.add_argument("--verificar-fichas",      action="store_true")
        parser.add_argument("--resetar-fichas",         action="store_true")
        parser.add_argument("--loop",                   action="store_true")
        parser.add_argument("--intervalo", type=int, default=60,
                            help="Intervalo em minutos para o loop (padrão: 60)")

    def handle(self, *args, **options):
        if options['verificar_vencimentos']:
            self.verificar_vencimentos()
        elif options['verificar_fichas']:
            self.verificar_fichas()
        elif options['resetar_fichas']:
            resetar_fichas_mensais()
        elif options['loop']:
            self.loop_continuo(options['intervalo'])
        else:
            self.stdout.write("Use --loop para rodar continuamente, ou uma flag específica.")
            self.stdout.write("Exemplo: python manage.py run_tarefas --loop --intervalo 30")

    def verificar_vencimentos(self):
        print(f"[{datetime.now():%H:%M:%S}] Verificando vencimentos...")
        try:
            _v()
            print("  ✓ Concluído")
        except Exception as e:
            print(f"  ✗ Erro: {e}")

    def verificar_fichas(self):
        print(f"[{datetime.now():%H:%M:%S}] Verificando limites de fichas...")
        try:
            _f()
            print("  ✓ Concluído")
        except Exception as e:
            print(f"  ✗ Erro: {e}")

    def loop_continuo(self, intervalo_minutos):
        print(f"[Tarefas] Iniciando loop a cada {intervalo_minutos} minutos...")
        print("  Pressione Ctrl+C para parar.\n")
        ultima_verificacao_dia = None

        while True:
            try:
                agora = datetime.now()
                self.verificar_fichas()
                hoje = agora.date()
                if agora.hour == 9 and ultima_verificacao_dia != hoje:
                    self.verificar_vencimentos()
                    resetar_fichas_mensais()
                    ultima_verificacao_dia = hoje

                time.sleep(intervalo_minutos * 60)

            except KeyboardInterrupt:
                print("\n[Tarefas] Encerrado.")
                break
            except Exception as e:
                print(f"[Tarefas] Erro no loop: {e}")
                time.sleep(60)
