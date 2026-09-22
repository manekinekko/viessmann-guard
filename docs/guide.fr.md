# Guide français

Viessmann Guard surveille le débit hydraulique à partir d'entités déjà présentes
dans Home Assistant. Il signale une baisse persistante et peut envoyer des
emails à plusieurs destinataires. Le projet est communautaire et n'est pas
affilié à Viessmann.

**Ce n'est ni un dispositif de sécurité, ni un diagnostic de filtre colmaté.**
Un débit faible peut venir de la pompe, d'une vanne, d'air dans le circuit, de la
pression, d'un capteur ou du mode de fonctionnement. Respectez les alertes et
les consignes du fabricant. Faites intervenir un professionnel qualifié.
N'ouvrez pas le circuit et ne modifiez pas l'installation sur la seule base
de ces indications.

L'intégration ne pilote pas la PAC, ne change aucune consigne et n'ajoute aucun
appel à l'API Viessmann. Elle continue à surveiller lorsque le tableau de bord
est fermé.

## Installation

Il faut Home Assistant **2026.8.3 minimum** et Python **3.14.2 minimum**.
Home Assistant OS et Container gèrent leur propre version de Python.

### Avec HACS

1. Ouvrez les dépôts personnalisés dans HACS.
2. Ajoutez `https://github.com/manekinekko/viessmann-guard` avec la catégorie
   **Intégration**.
3. Téléchargez Viessmann Guard puis redémarrez Home Assistant.
4. Dans **Paramètres > Appareils et services > Ajouter une intégration**,
   recherchez **Viessmann Guard**.

Il s'agit d'un dépôt personnalisé, pas d'une inscription officielle au catalogue
HACS.

### Installation manuelle

Copiez le dossier `custom_components/viessmann_guard` du dépôt dans le dossier
de configuration Home Assistant, au même chemin. Redémarrez Home Assistant,
puis ajoutez l'intégration depuis l'interface. Sauvegardez votre configuration
avant une installation ou une mise à jour.

## 1. Choisir les sources

Si la version 0.1.0 n'apparaît pas dans **Ajouter une intégration**, ou si son
formulaire échoue, installez la version 0.1.1 ou ultérieure. Elle corrige la
catégorie du catalogue et la sérialisation des formulaires. Après la copie,
redémarrez Home Assistant au moment choisi, puis actualisez le navigateur.
Le message générique évoquant la « dernière version » ne justifie pas à lui seul
une mise à niveau d'un Home Assistant déjà en version 2026.8.3 ou ultérieure.

Donnez un nom au moniteur et sélectionnez les appareils concernés. Associez les
entités existantes à leur rôle :

- **Débit** : valeur numérique avec une unité volumique explicitement prise en
  charge : `L/min`, `L/h`, `m³/h` ou `m3/h`, `m³/s` ou `m3/s`, `US gal/min`.
  Une valeur sans unité ou avec l'unité ambiguë `gal/min` ne suffit pas.
- **Mode** : état brut du mode de fonctionnement.
- **Pompe en marche** : indispensable aux diagnostics actifs. L'assistant
  permet de ne pas la sélectionner, mais Guard ne supposera pas alors que la
  pompe fonctionne.
- **Vitesse de pompe** : facultative, numérique entre 0 et 100 et en `%`.
  Elle améliore la comparaison à fonctionnement équivalent.
- **Défaut** : facultatif, avec des valeurs distinctes pour défaut et absence
  de défaut.
- **Températures, pression, compresseur et vanne** : contexte facultatif pour
  les rapports.

Les sources doivent appartenir aux appareils sélectionnés. Un nom évocateur
n'est pas une preuve de la grandeur mesurée. Vérifiez l'unité et le sens de
chaque valeur dans les outils de développement de Home Assistant, sans publier
de diagnostic brut.

Les domaines pris en charge sont `sensor`, `binary_sensor`, `select`, `climate`
et `number`. Les sources `number` sont lues uniquement : aucune commande ne
modifie leur valeur.

## 2. Définir les règles

Renseignez le débit minimum propre à votre installation avec l'aide de la
documentation du matériel ou d'un professionnel. **Aucun seuil présenté par
ce projet ne constitue un minimum Viessmann.** Les valeurs des tests et des
démonstrations sont fictives.

Associez les **états bruts**, et non les libellés traduits, aux catégories :

- modes actifs ;
- modes au repos ;
- modes exclus, notamment le dégivrage ;
- pompe en marche et pompe à l'arrêt ;
- défaut et absence de défaut, si une source de défaut est configurée.

Les catégories incompatibles ne doivent pas se recouper. Un état inconnu ou
non associé ne devient jamais une preuve de bon fonctionnement.

Les durées de persistance évitent de réagir à un bref passage sous le seuil.
L'hystérésis et la durée de récupération évitent les basculements répétés.
Le tableau complet des options, valeurs par défaut et limites de saisie figure
dans [l'architecture](architecture.md#rules). Ce sont des paramètres logiciels,
pas des recommandations hydrauliques.

### Étalonnage sain et référence fixe

La détection relative nécessite une référence obtenue dans des conditions
connues comme saines et comparables : mode stable et vitesse de pompe
comparable si elle est disponible. Utilisez **Je confirme un fonctionnement sain : étalonner**
uniquement lorsque vous avez une raison fiable d'affirmer que l'installation
fonctionne correctement.

Les mesures de démarrage, de dégivrage, inconnues, périmées ou non admissibles
ne servent pas à l'étalonnage. Il faut suffisamment d'observations sur une
durée suffisante. La référence acceptée reste fixe ; elle ne descend pas
automatiquement avec une installation qui se dégrade.

**Enregistrer un nettoyage** conserve une date de maintenance. Cela ne prouve
pas la récupération, n'efface pas un incident et ne remplace pas la référence.
Cela annule aussi un étalonnage inachevé, sans modifier la référence déjà
acceptée. Un nouvel étalonnage demande une confirmation explicite.

### Comprendre la fraîcheur

Chaque mesure indique son statut, sa date de rapport Home Assistant et son âge.
`last_reported` correspond à un rapport reçu/émis dans HA, pas à l'instant de
mesure physique du contrôleur.

Une valeur identique reste fraîche si l'intégration source la publie à nouveau.
Si elle conserve simplement la même valeur en cache, Guard peut la considérer
comme périmée par prudence. Vérifiez la fréquence réelle des rapports avant
d'assouplir le délai de péremption.

Après un démarrage ou un rechargement, de nouveaux rapports sont nécessaires
avant tout envoi lié à un incident ou toute reconnaissance de récupération.
Un état restauré ne suffit pas.

## 3. Configurer les emails

Configurez la connexion et les destinataires dans l'interface de l'intégration
**SMTP native de Home Assistant**. Sélectionnez ensuite ses entités `notify`
dans Guard. N'y recopiez ni mot de passe SMTP ni identifiant Viessmann.

Donnez aux entités SMTP des noms utiles et neutres, par exemple `Maintenance`
ou `Maison`, sans adresse email ni information personnelle. Le tableau de bord
affiche les libellés nettoyés par l'intégration, jamais les adresses brutes.

**Les emails sont désactivés par défaut, y compris les emails de test.**
L'option et l'interrupteur **Activer les emails** modifient le même réglage
persistant. Il faut au moins un destinataire valide pour les activer.

Vous pouvez choisir la langue française des rapports, leur rappel et l'envoi
facultatif dès le stade de surveillance. Guard vérifie le registre des entités,
l'appartenance à SMTP et les sous-entrées de destinataires, plutôt que de faire
confiance au seul nom `notify.*`.

Le dédoublonnage conserve la casse de la partie avant `@` et normalise le domaine
en minuscules. Il ne peut pas reconnaître tous les alias ou transferts vers
une même boîte.

Une entité de destinataire SMTP jamais utilisée peut afficher `unknown` :
cet état initial normal ne bloque pas un test. Une entité absente ou
`unavailable` ne permet pas l'envoi. Ne confondez pas cet état initial avec
un **résultat d'envoi inconnu** après une interruption.

### Ce que signifie le statut d'envoi

Le résultat est suivi séparément pour chaque destinataire. Un échec peut être
réessayé après 60 puis 300 secondes, avec trois tentatives maximum. Un succès
pour un destinataire n'est pas réexpédié parce qu'un autre destinataire échoue.

Un appel SMTP terminé ne garantit pas l'arrivée dans la boîte de réception.
Un envoi interrompu peut rester de résultat **inconnu** : Guard ne le réexpédie
pas aveuglément. Une livraison exactement une fois ne peut pas être garantie.

Désactiver les emails invalide les envois en attente et les tests, mais ne
rappelle pas un message déjà en cours d'envoi ou accepté par SMTP. La
réactivation ne rejoue pas un ancien stock d'alertes : l'incident courant doit
être confirmé à nouveau par des données fraîches.

## 4. Limiter les rapports

L'inventaire est limité aux appareils sélectionnés et à certaines catégories de
mesures. Vous pouvez ajouter des entités explicitement ou en exclure.
Les entités `number` peuvent être incluses en lecture seule ; leur valeur
n'est jamais modifiée.
Les sources diagnostiques explicitement associées restent visibles, même si
elles figurent aussi dans les exclusions.

Les valeurs manquantes ou périmées sont signalées comme telles. L'intégration
n'exporte pas de diagnostic brut ni d'ensemble arbitraire d'attributs, de
localisation, de numéros de série ou d'identifiants secrets.

Relisez les noms et les valeurs que vous sélectionnez. Nommez les entités de
façon neutre. Avant de partager un rapport, masquez les adresses email, noms de
personnes, lieux, identifiants et autres données sensibles.

## Tableau de bord natif

Copiez [`examples/dashboard.yaml`](../examples/dashboard.yaml) dans l'éditeur de
configuration brute d'un nouveau tableau de bord, puis remplacez tous les
identifiants d'exemple. `sensor.demo_guard_state` correspond uniquement à un
exemple de nom d'entrée, **pas à une entité découverte sur votre installation**.
Les identifiants réels dépendent du nom de l'entrée ou de l'appareil, des
renommages et des entités déjà présentes. Les suffixes par défaut utilisent
des clés stables, indépendantes des libellés traduits.

Les cartes sont natives : entités, historique, texte et boutons nommés.
Elles reprennent votre thème et ne nécessitent aucun composant frontend
supplémentaire. Le graphique utilise l'historique de Recorder.

Lisez toujours le motif avec l'état. Les cinq états publics sont `normal`,
`learning`, `watch`, `urgent` et `diagnostic_unavailable`. `normal` peut
correspondre à un seuil en attente, une référence absente ou un mode au repos,
sans garantir le bon état du matériel. Un mode exclu donne
`diagnostic_unavailable` avec le motif `mode_excluded`. `learning` couvre le
délai de démarrage et l'étalonnage explicitement autorisé.

Un incident peut rester enregistré pendant une pause ou une indisponibilité.
Lorsqu'un incident actif est conservé au repos, au démarrage ou en mode exclu,
l'état public reste `diagnostic_unavailable`, jamais `normal` ou `learning`.
Seule une récupération confirmée résout l'incident.
Un défaut natif explicitement associé n'est pas forcément un défaut hydraulique.

| Commande | Effet |
| --- | --- |
| Acquitter | Indique que l'incident a été vu, sans le résoudre |
| Suspendre les rappels pendant 24 h | Suspend uniquement les rappels, pas les nouvelles tentatives d'alerte initiale ni le passage à une alerte urgente ; l'expiration n'est pas une récupération |
| Enregistrer un nettoyage | Conserve une date et annule l'étalonnage inachevé, sans effacer l'incident ni changer la référence acceptée |
| Je confirme un fonctionnement sain : étalonner | Autorise explicitement un étalonnage en conditions saines et comparables |
| Envoyer un email de test | Demande un test uniquement si les emails sont activés |

Les boutons de nettoyage et d'étalonnage du tableau de bord demandent
confirmation. Le bouton d'entité d'étalonnage constitue lui-même une affirmation
explicite d'un fonctionnement sain ; une automatisation qui appelle
`button.press` n'affiche pas la boîte de dialogue du tableau de bord. Les services
`viessmann_guard.acknowledge`, `snooze`, `record_cleaning`,
`confirm_calibration` et `test_email` prennent l'identifiant `entry_id`.
`snooze` suspend uniquement les rappels et accepte `hours` de 1 à 168 ;
`confirm_calibration` exige
`confirmed: true`. Ces services ne pilotent jamais la PAC.

## Dépannage et contribution

Pour une démonstration locale dans le terminal, sans connexion à votre
installation, installez les dépendances de développement puis lancez :

```sh
uv sync --frozen
uv run python examples/showcase.py
```

Le scénario utilise des entités fictives dans une instance de test isolée.
Il imprime l'étalonnage, la baisse relative, le débit faible persistant, les
actions de maintenance, la récupération et la péremption. Les emails restent
désactivés. Les valeurs sont fictives, jamais des minima fabricant. Ce n'est
pas un aperçu du tableau de bord dans un navigateur.

Les suites de développement utilisent Home Assistant 2026.8.3 et 2026.9.3 dans
des environnements de test isolés, avec accès réseau bloqué et transport SMTP
simulé. Elles ne contactent ni installation réelle ni serveur SMTP réel.

- **Diagnostic indisponible** : vérifiez la source de pompe, les associations de
  modes, les unités et la fraîcheur de chaque source nécessaire.
- **Référence absente** : vérifiez la confirmation d'étalonnage et la présence
  d'observations saines et comparables en nombre et en durée suffisants.
- **Email absent** : vérifiez **Activer les emails**, la sélection SMTP, le statut
  de chaque destinataire et les restrictions de fraîcheur. Un statut inconnu
  ne doit pas entraîner un renvoi automatique.
- **Entité introuvable dans le tableau de bord** : remplacez l'identifiant
  d'exemple par celui du registre HA.

Pour signaler un problème, fournissez les versions de Home Assistant et de
Guard, les rôles des sources, les unités et une courte chronologie anonymisée.
Ne publiez pas d'export complet de diagnostics, de sauvegarde HA ou de
configuration contenant des secrets. Consultez
[CONTRIBUTING.md](../CONTRIBUTING.md) pour les vérifications locales.
