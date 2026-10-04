# Option Twilio testée puis désactivée

Un workflow n8n historique `Twilio_Tracker` a été testé pendant une période d’essai gratuite. Il interrogeait l’état du Tracker et pouvait déclencher un appel vocal lorsqu’un journal manquait. Cette option n’est plus retenue pour le fonctionnement courant, car elle dépend d’un service payant après l’essai.

Dans l’installation auditée, ce workflow a été dépublié. Son export privé est conservé hors de ce dépôt pour traçabilité. La route de compatibilité de l’API répond désormais `besoin_relance: false` afin qu’une réactivation accidentelle du vieux workflow ne puisse pas autoriser d’appel.

Pour réévaluer les appels plus tard, traiter séparément le prix, le consentement, les horaires, les quotas, les erreurs d’envoi et la protection des numéros de téléphone. Aucun numéro, SID, jeton ou credential Twilio n’est publié ici.
