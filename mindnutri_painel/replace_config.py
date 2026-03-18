import os

target_dir = r"c:\Users\User\Desktop\CLAUDE\mindnutri_completo\mindnutri_painel"

for root, dirs, files in os.walk(target_dir):
    for f in files:
        if f.endswith(".py"):
            filepath = os.path.join(root, f)
            with open(filepath, "r", encoding="utf-8") as file:
                content = file.read()
            
            if "from django.conf import settings as config" in content:
                content = content.replace("from django.conf import settings as config", "from django.conf import settings as config")
                with open(filepath, "w", encoding="utf-8") as file:
                    file.write(content)
                print(f"Updated {filepath}")
