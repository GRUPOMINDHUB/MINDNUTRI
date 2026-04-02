FROM python:3.11-slim
WORKDIR /app

# Copia os arquivos da sua pasta mindnutri_painel para dentro do container
COPY . .

# Instala as dependências (Certifique-se de ter um requirements.txt nesta pasta com 'gunicorn' listado nele)
RUN pip install --no-cache-dir -r requirements.txt

# Expõe a porta que o Cloud Run usa
EXPOSE 8080

# Comando para preparar o banco e rodar o Django em produção
CMD ["sh", "-c", "python manage.py migrate --noinput && if [ -n \"$DJANGO_SUPERUSER_USERNAME\" ] && [ -n \"$DJANGO_SUPERUSER_PASSWORD\" ]; then python manage.py ensure_superuser; fi && gunicorn --bind 0.0.0.0:8080 core.wsgi:application"]
