# On part d'une base Python légère
FROM python:3.11.17-slim
# On définit le dossier de travail dans le conteneur
WORKDIR /app
# On copie d'abord les requirements (optimisation du cache Docker)
COPY requirements.txt .
COPY constraints.txt .
# On installe les dépendances sans garder de cache pour alléger le conteneur
RUN pip install --no-cache-dir -c constraints.txt -r requirements.txt
# On copie ton code (agent_tracker.py)
COPY . .
# On ouvre le port 8000 pour que n8n puisse communiquer
EXPOSE 8000
# La commande de démarrage du serveur API
CMD ["uvicorn", "agent_tracker:app", "--host", "0.0.0.0", "--port", "8000"]
