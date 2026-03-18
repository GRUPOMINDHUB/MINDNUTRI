"""
Script de setup inicial do Mindnutri Agente.
Execute uma vez após instalar as dependências:
    python setup.py
"""
import os
import shutil
from pathlib import Path

BASE = Path(__file__).parent


def main():
    print("=" * 50)
    print("  Mindnutri — Setup Inicial")
    print("=" * 50)

    # 1. Cria pastas necessárias
    pastas = [
        BASE / "assets",
        BASE / "exemplos",
        BASE / "arquivos_gerados",
        BASE / "logs",
    ]
    for p in pastas:
        p.mkdir(exist_ok=True)
        print(f"  ✓ Pasta criada: {p.name}/")

    # 2. Verifica .env
    env_path = BASE / ".env"
    env_example = BASE / ".env.example"
    if not env_path.exists() and env_example.exists():
        shutil.copy(env_example, env_path)
        print("\n  ✓ Arquivo .env criado a partir do .env.example")
        print("  ⚠️  IMPORTANTE: Edite o .env e preencha suas chaves de API!")
    elif env_path.exists():
        print("  ✓ Arquivo .env já existe")
    else:
        print("  ⚠️  Crie um arquivo .env com base no .env.example")

    # 3. Inicializa banco de dados
    print("\n  Inicializando banco de dados...")
    try:
        from utils.banco import init_db
        init_db()
        print("  ✓ Banco SQLite inicializado")
    except Exception as e:
        print(f"  ✗ Erro ao inicializar banco: {e}")

    # 4. Verifica assets
    logo_src = BASE.parent / "mindnutri_painel" / "painel" / "static" / "painel" / "img" / "logo_mindhub.png"
    logo_dst = BASE / "assets" / "logo_mindhub.png"
    if logo_src.exists() and not logo_dst.exists():
        shutil.copy(logo_src, logo_dst)
        print("  ✓ Logo Mindhub copiada para assets/")
    elif logo_dst.exists():
        print("  ✓ Logo Mindhub já existe em assets/")
    else:
        print("  ⚠️  Coloque a logo da Mindhub em: assets/logo_mindhub.png")

    # 5. Verifica exemplos
    exemplos_src = BASE.parent
    for nicho in ["hamburguer", "pizza", "sobremesa"]:
        for ext in ["xlsx", "pdf"]:
            src = exemplos_src / f"exemplo_{nicho}.{ext}"
            dst = BASE / "exemplos" / f"exemplo_{nicho}.{ext}"
            if src.exists() and not dst.exists():
                shutil.copy(src, dst)
                print(f"  ✓ Exemplo copiado: exemplo_{nicho}.{ext}")
            elif dst.exists():
                print(f"  ✓ Exemplo já existe: exemplo_{nicho}.{ext}")

    print("\n" + "=" * 50)
    print("  Setup concluído!")
    print("\n  Próximos passos:")
    print("  1. Edite o .env com suas chaves de API")
    print("  2. Configure a Evolution API e o número do WhatsApp")
    print("  3. Execute: python manage.py runserver")
    print("  4. Configure o webhook da Evolution API para:")
    print("     http://SEU_IP:8000/webhook/whatsapp/")
    print("  5. Configure o webhook do Asaas para:")
    print("     http://SEU_IP:8000/webhook/asaas/")
    print("=" * 50)


if __name__ == "__main__":
    main()
