import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Cria ou atualiza um superusuario com base nas variaveis de ambiente do Django."

    def handle(self, *args, **options):
        username = os.getenv("DJANGO_SUPERUSER_USERNAME", "").strip()
        email = os.getenv("DJANGO_SUPERUSER_EMAIL", "").strip()
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD", "")

        if not username:
            raise CommandError("Defina DJANGO_SUPERUSER_USERNAME para criar o superusuario.")
        if not password:
            raise CommandError("Defina DJANGO_SUPERUSER_PASSWORD para criar o superusuario.")

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "is_staff": True,
                "is_superuser": True,
            },
        )

        updated_fields = []
        if email and user.email != email:
            user.email = email
            updated_fields.append("email")
        if not user.is_staff:
            user.is_staff = True
            updated_fields.append("is_staff")
        if not user.is_superuser:
            user.is_superuser = True
            updated_fields.append("is_superuser")

        user.set_password(password)
        updated_fields.append("password")
        user.save(update_fields=updated_fields)

        if created:
            self.stdout.write(self.style.SUCCESS(f"Superusuario '{username}' criado com sucesso."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Superusuario '{username}' atualizado com sucesso."))
