# Agent Tracker — journal personnel et rappels Telegram

Prototype personnel : une API FastAPI enregistre des observations textuelles dans un journal Markdown. Deux workflows n8n servent d’interface Telegram : réception/réponse et rappel facultatif. Le service ne pose aucun diagnostic et ne recommande aucun traitement.

## Ce qui fonctionne

- `POST /webhook/telegram` reçoit `{ "chat_id": "...", "message": "..." }` et renvoie `{ "reply": "..." }`. Les messages ordinaires sont enregistrés ; un échec d’écriture renvoie HTTP 503 sans prétendre que le log est sauvé.
- Une heure de référence T0 n’est retenue que si la prise est explicitement écrite, par exemple `pris à 08h30`. `RESET` ouvre un nouveau cycle ; les heures des cycles ou jours précédents ne sont pas réutilisées.
- `/rappel_on` autorise les rappels pendant sept jours. `/rappel_off` les arrête, `/rappel_pause` les suspend pendant 24 h, `/rappel_fait` évite une autre relance le jour même et `/rappel_statut` donne l’état.
- `POST /rappels/claim/{chat_id}` réserve au plus un rappel par jour dans SQLite, entre 08 h et 21 h (Europe/Paris), uniquement après l’activation par la personne concernée et en l’absence de log du jour. n8n transmet alors un texte générique par Telegram.
- L’ancienne route `GET /webhook/telegram/etat/{chat_id}` répond toujours `besoin_relance: false` : elle ne peut plus déclencher un appel.

Le rappel est une **notification Telegram**, dont le son et la visibilité dépendent des réglages du téléphone. Il ne remplace pas un appel, une alarme fiable ni un suivi médical.

## Déployer localement

Le `Dockerfile` utilise Python 3.11. Configurer les variables d’environnement hors du dépôt :

| Variable | Rôle |
| --- | --- |
| `TRACKER_JOURNAL_PATH` | Journal Markdown monté en volume, par défaut `/data/journal.md` |
| `TRACKER_STATE_DB` | Fichier SQLite persistant des rappels, par défaut `/data/tracker_state.sqlite3` |
| `TRACKER_ALLOWED_CHAT_IDS` | Liste facultative d’identifiants Telegram autorisés, séparés par des virgules ; à définir pour une instance personnelle |
| `TRACKER_API_KEY` | Clé du proxy LLM facultatif ; ne jamais la committer |
| `TRACKER_MODEL` | Nom du modèle d’extraction facultatif |
| `TRACKER_LLM_BASE_URL` | URL facultative du proxy OpenAI compatible |

L’extraction LLM ajoute seulement des étiquettes d’observation. Elle peut être indisponible sans empêcher l’enregistrement du texte. Éviter d’envoyer des données sensibles à un fournisseur non choisi et maîtrisé.

Monter le journal et le répertoire SQLite dans des volumes persistants. L’API écoute sur le port 8000 ; `GET /health` donne l’état de base du stockage. Ne pas exposer l’API publiquement sans authentification et contrôle réseau. La liste `TRACKER_ALLOWED_CHAT_IDS` limite les identifiants acceptés, mais ne remplace pas une authentification réseau du webhook.

Les fichiers de `workflows/` sont des **modèles expurgés** : ils ne contiennent ni identifiants de projet, ni credentials, ni ID de chat, ni adresse interne. Après import dans n8n, renseigner les credentials Telegram, remplacer `CHAT_ID` par le destinataire voulu, adapter `http://tracker:8000` au réseau local, vérifier les expressions, puis publier. Le bot et la relance utilisent le même bot Telegram. La relance ne produit rien avant `/rappel_on`.

## Vérifier

```bash
docker build -t agent-tracker .
docker run --rm -e PYTHONPATH=/app agent-tracker python -m unittest discover -s /app/tests -v
```

Les tests couvrent l’extraction stricte de T0, le changement de jour, `RESET`, les erreurs d’écriture, les commandes Telegram et la limite de rappel quotidienne. Une instance n8n de production exige en plus un test de bout en bout avec un chat de test et ses propres credentials.

## Périmètre et confidentialité

Le journal, la base SQLite, les messages, les identifiants de chat et les credentials ne sont pas inclus. Les exports n8n ont été nettoyés avant publication. La route de réservation marque le rappel comme consommé avant l’envoi Telegram ; un échec d’envoi n’est donc pas renvoyé automatiquement le même jour. Ce point doit être amélioré avec un accusé de livraison si l’on recherche une garantie plus forte.

L’essai historique d’appel Twilio et les conditions d’une éventuelle [réactivation payante](docs/twilio-historical.md) sont documentés. Le workflow vocal reste désactivé dans l’installation d’origine ; il faudrait une nouvelle intégration avec consentement, quotas et choix exclusif du canal avant de le proposer de nouveau.
