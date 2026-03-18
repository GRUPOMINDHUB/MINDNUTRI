from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta, date
from painel.models import Assinante, FichaTecnica, Notificacao
import random


NOMES = [
    ("Rodrigo Ferreira", "Burger Bros", "hamburguer", "+55 11 99876-5432", "@burgerbros.sp", "São Paulo - SP", 8, "R$ 45.000"),
    ("Camila Souza", "Pizzaria Bella Napoli", "pizza", "+55 21 98765-4321", "@bellanapoli.rj", "Rio de Janeiro - RJ", 5, "R$ 32.000"),
    ("Marco Antônio Lima", "Doce Tentação Confeitaria", "sobremesa", "+55 31 97654-3210", "@docetentacao", "Belo Horizonte - MG", 3, "R$ 18.000"),
    ("Juliana Mendes", "Sabor da Terra", "comida_brasileira", "+55 41 96543-2109", "@sabordaterra.cwb", "Curitiba - PR", 12, "R$ 67.000"),
    ("Felipe Carvalho", "The Smash Burger", "hamburguer", "+55 11 95432-1098", "@thesmash.sp", "São Paulo - SP", 6, "R$ 38.000"),
    ("Ana Paula Rocha", "La Pizza Nostra", "pizza", "+55 85 94321-0987", "@lapizzanostra", "Fortaleza - CE", 4, "R$ 25.000"),
    ("Lucas Oliveira", "Gelato & Cia", "sobremesa", "+55 51 93210-9876", "@gelatoecia.poa", "Porto Alegre - RS", 2, "R$ 12.000"),
    ("Fernanda Costa", "Tempero Mineiro", "comida_brasileira", "+55 34 92109-8765", "@temperomineiro", "Uberlândia - MG", 9, "R$ 52.000"),
]

PRATOS_BURGER = ["Burger Clássico", "Smash Duplo", "Bacon Lovers", "Veggie Burger", "BBQ Especial", "Crispy Chicken"]
PRATOS_PIZZA  = ["Margherita", "Calabresa", "Quatro Queijos", "Frango c/ Catupiry", "Portuguesa", "Pepperoni"]
PRATOS_DOCE   = ["Brownie c/ Sorvete", "Cheesecake", "Trufa de Chocolate", "Pavê de Limão", "Brigadeiro Gourmet"]
PRATOS_BR     = ["Frango à Parmegiana", "Picanha na Brasa", "Feijoada Completa", "Filé de Tilápia", "Arroz com Feijão"]

NICHOS_PRATOS = {
    'hamburguer': PRATOS_BURGER,
    'pizza': PRATOS_PIZZA,
    'sobremesa': PRATOS_DOCE,
    'comida_brasileira': PRATOS_BR,
    'outro': PRATOS_BR,
}

STATUS_POOL = ['ativo', 'ativo', 'ativo', 'ativo', 'ativo', 'bloqueado', 'inadimplente']


class Command(BaseCommand):
    help = 'Popula o banco de dados com dados de exemplo para demonstração'

    def handle(self, *args, **options):
        self.stdout.write("Limpando dados existentes...")
        Notificacao.objects.all().delete()
        FichaTecnica.objects.all().delete()
        Assinante.objects.all().delete()

        self.stdout.write("Criando assinantes...")
        assinantes_criados = []

        for i, (nome, estab, nicho, tel, ig, cidade, func, fat) in enumerate(NOMES):
            dias_atras = random.randint(5, 90)
            data_inicio = timezone.localdate() - timedelta(days=dias_atras)
            status = STATUS_POOL[i % len(STATUS_POOL)]
            fichas_mes = random.randint(0, 28)

            a = Assinante.objects.create(
                nome=nome,
                estabelecimento=estab,
                nicho=nicho,
                telefone=tel,
                instagram=ig,
                cidade=cidade,
                funcionarios=func,
                faturamento_estimado=fat,
                status=status,
                data_inicio=data_inicio,
                proxima_cobranca=data_inicio + timedelta(days=30),
                fichas_geradas_mes=fichas_mes,
                fichas_limite_mes=30,
                total_fichas_geradas=fichas_mes + random.randint(0, 50),
            )
            assinantes_criados.append(a)
            self.stdout.write(f"  + {nome} ({status})")

        self.stdout.write("Criando fichas técnicas...")
        tipos = ['tecnica', 'operacional', 'custo_rapido']
        for a in assinantes_criados:
            pratos = NICHOS_PRATOS.get(a.nicho, PRATOS_BR)
            for _ in range(a.fichas_geradas_mes):
                prato = random.choice(pratos)
                tipo  = random.choice(tipos)
                custo = round(random.uniform(5, 45), 2)
                FichaTecnica.objects.create(
                    assinante=a,
                    nome_prato=prato,
                    tipo=tipo,
                    codigo=f"{a.nicho[:3].upper()}{random.randint(100,999)}",
                    custo_total=custo,
                    custo_porcao=round(custo / random.randint(1, 12), 2),
                    num_porcoes=random.randint(1, 12),
                    criada_em=timezone.now() - timedelta(days=random.randint(0, 29)),
                )

        self.stdout.write("Criando notificações...")
        notifs = [
            ('inadimplencia', 'critico', 'Assinante inadimplente',
             f'{assinantes_criados[5].nome} está com pagamento em atraso há 5 dias.', assinantes_criados[5]),
            ('limite_fichas', 'aviso', 'Limite de fichas próximo',
             f'{assinantes_criados[0].nome} usou 28 de 30 fichas este mês.', assinantes_criados[0]),
            ('sem_entender', 'aviso', 'Agente não entendeu cliente',
             f'{assinantes_criados[3].nome} enviou 3 mensagens que o agente não conseguiu interpretar.', assinantes_criados[3]),
            ('novo_assinante', 'info', 'Novo assinante ativo',
             f'{assinantes_criados[4].nome} — {assinantes_criados[4].estabelecimento} acabou de ativar a assinatura.', assinantes_criados[4]),
            ('erro_sistema', 'critico', 'Falha na geração de PDF',
             'Erro ao gerar ficha operacional para Frango à Parmegiana. Timeout no storage.', None),
            ('limite_fichas', 'aviso', 'Limite de fichas próximo',
             f'{assinantes_criados[2].nome} usou 25 de 30 fichas este mês.', assinantes_criados[2]),
        ]

        for tipo, nivel, titulo, msg, ass in notifs:
            Notificacao.objects.create(
                tipo=tipo, nivel=nivel, titulo=titulo,
                mensagem=msg, assinante=ass,
                criada_em=timezone.now() - timedelta(hours=random.randint(1, 48)),
            )

        total_fichas = FichaTecnica.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f"\nBanco populado com sucesso!\n"
            f"   {Assinante.objects.count()} assinantes\n"
            f"   {total_fichas} fichas tecnicas\n"
            f"   {Notificacao.objects.count()} notificacoes\n"
        ))
