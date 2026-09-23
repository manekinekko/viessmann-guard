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

### Installation manuelle

L'implémentation est actuellement dans la branche
[`manekinekko-integration-viessmann-guard`](https://github.com/manekinekko/viessmann-guard/tree/manekinekko-integration-viessmann-guard),
avec la PR #1 en brouillon. Tant qu'elle n'est pas fusionnée, `main` ne contient
pas le composant utilisable. Il n'existe pas encore de release publiée ni de
référencement HACS officiel.

Téléchargez [le ZIP de cette branche](https://github.com/manekinekko/viessmann-guard/archive/refs/heads/manekinekko-integration-viessmann-guard.zip).
Copiez uniquement son dossier complet `custom_components/viessmann_guard`,
traductions comprises, dans le dossier de configuration HA contenant
`configuration.yaml`. Ne copiez pas la racine du dépôt, les tests ou `.venv`.
Sauvegardez d'abord la configuration et l'ancien composant.

Redémarrez **Home Assistant Core une fois** après la copie, puis actualisez
l'interface. Un simple rechargement ne suffit pas et aucun redémarrage de l'hôte
n'est nécessaire. Ajoutez **Viessmann Guard** dans **Paramètres > Appareils et
services > Ajouter une intégration**. Le [README anglais](../README.md#install)
donne l'arborescence exacte et les précautions de mise à jour.

HACS ne devient une alternative qu'après publication d'une version contenant le
composant sur la branche par défaut. Pour cette préversion, utilisez la copie
manuelle, pas le téléchargement du squelette `main`.

## Démarrage rapide

Après avoir choisi **Viessmann Guard** dans Ajouter une intégration :

- **Une seule PAC ViCare** : lisez le récapitulatif, puis validez. Une
  confirmation, aucun identifiant d'entité ni valeur à saisir.
- **Plusieurs PAC** : choisissez l'appareil dans la liste, validez ce choix,
  puis confirmez le récapitulatif. Trois interactions, deux formulaires.
  Donnez d'abord des noms distincts aux appareils homonymes si nécessaire.
- **Aucune PAC reconnue** : un chemin **Configuration manuelle avancée**
  est proposé. Ce chemin secondaire n'est pas annoncé comme « trois clics ».

Guard reconnaît les fonctions natives ViCare et leur appareil d'origine,
indépendamment des noms d'entités modifiés ou traduits. Une passerelle ne
fournissant que le Wi-Fi n'est pas une deuxième PAC. Le même compte, modèle
ou une liaison de passerelle ne suffisent pas à fusionner deux appareils.
Aucune entité source désactivée n'est activée à votre insu.

Le récapitulatif indique le débit, la phase réelle du compresseur, la circulation
du circuit de chauffage, le compresseur, les températures et la pression
disponibles. Plusieurs circuits ou compresseurs ambigus restent non associés.
Une pompe ECS ou un sélecteur de mode ECS ne remplace pas le contexte chauffage.
Le réglage `auto` d'un thermostat ne prouve pas un mode hydraulique actif.
Un défaut générique n'est pas automatiquement interprété comme un défaut de débit.

La phase native `ready` signifie arrêt/attente, jamais chauffage. Depuis 0.4.1,
ses rapports frais comptent comme des périodes exclues connues, pas des trous
inconnus. Au chargement, une migration contrôlée corrige uniquement les anciens
modes automatiques ViCare non personnalisés. Les associations manuelles/expertes,
emails et limites de fraîcheur restent inchangés. La référence saine, les captures
d'incident et les lignes historiques sont conservées, sans requalifier
rétroactivement les anciennes lignes inconnues. Les comparaisons demandent
toujours de vraies périodes fraîches de chauffage/refroidissement avec circulation.

**Vous pouvez commencer sans connaître le débit minimum constructeur.**
L'observation du débit, l'historique et le contexte des rapports deviennent
disponibles avec les mesures fraîches. Le minimum reste absent, jamais zéro
ou une valeur devinée. Les alertes absolues sont désactivées jusqu'au réglage
du minimum réel. Le suivi relatif demande toujours une référence saine
explicitement confirmée et un contexte comparable. Si ce contexte manque,
le diagnostic reste indisponible, sans afficher un faux état Normal.
**Les emails restent désactivés**, sans ajout de SMTP ni de destinataires.
Pour lire un rapport sans SMTP, ouvrez **Outils de développement > Actions >
Viessmann Guard : Lire le rapport d'observation** (`viessmann_guard.get_report`),
choisissez le moniteur, puis consultez la réponse. Cette action génère le
rapport localement, sans email ni changement d'état de l'incident.

## Options avancées après création

Dans **Configurer** sur l'intégration, chaque rubrique s'ouvre directement :
minimum facultatif, sources, règles, emails ou contenu des rapports. Vous
n'avez pas à refaire l'assistant complet.

**Débit minimum de l'installation (facultatif)** permet de renseigner le minimum
réel fourni par le constructeur/installateur en L/min. Videz ce champ pour
désactiver les alertes absolues. Une modification invalide la référence apprise,
mais ne résout pas un incident actif.

Les configurations manuelles existantes gardent leurs sources, seuils et
permission d'envoi. Les identités du registre permettent de suivre les
renommages d'entités après rechargement/redémarrage. La découverte ne remplace
jamais vos associations avancées.

### Sources manuelles

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

### Règles

Si vous le connaissez, renseignez le débit minimum propre à votre installation avec l'aide de la
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

### Emails

Configurez la connexion et les destinataires dans l'interface de l'intégration
**SMTP native de Home Assistant**. Sélectionnez ensuite ses entités `notify`
dans Guard. N'y recopiez ni mot de passe SMTP ni identifiant Viessmann.

**Créer un destinataire SMTP ne le sélectionne pas dans Guard.** Dans SMTP,
utilisez **Ajouter un destinataire** pour chaque adresse. Puis ouvrez
**Viessmann Guard > Configurer > Emails et destinataires > Entités destinataires SMTP**,
sélectionnez les entités existantes et enregistrez. Activez ensuite
**Activer les emails** volontairement. Aucun redémarrage n'est nécessaire pour
cette sélection.

Avec Gmail, activez la validation en deux étapes Google et créez un mot de passe
d'application. Saisissez-le uniquement dans HA SMTP : serveur `smtp.gmail.com`,
port `587`, sécurité `STARTTLS`, vérification du certificat activée. L'adresse
d'expéditeur et le nom d'utilisateur sont votre adresse Gmail complète.
Utilisez le mot de passe d'application, pas le mot de passe du compte.
SMTP natif n'utilise pas OAuth Google. Les destinataires peuvent être chez
n'importe quel fournisseur. Certaines politiques de compte Google interdisent
les mots de passe d'application ; ne désactivez pas la sécurité pour contourner
cette restriction.

Donnez aux entités SMTP des noms utiles et neutres, par exemple `Maintenance`
ou `Maison`, sans adresse email ni information personnelle. Le tableau de bord
affiche les libellés nettoyés par l'intégration, jamais les adresses brutes.

**Les emails sont désactivés par défaut, y compris les emails de test.**
L'option et l'interrupteur **Activer les emails** modifient le même réglage
persistant. Il faut au moins un destinataire valide pour les activer.

Le choix **Langue des emails et rapports** propose **English**, **Français**,
**Español** et **Deutsch**, indépendamment de l'interface Home Assistant.
L'anglais est le défaut des nouveaux moniteurs, même dans un HA français.
Les choix déjà enregistrés, notamment le français des anciens assistants
rapides, sont conservés. Une langue ancienne absente ou non prise en charge
utilise l'anglais ; les variantes régionales reconnues utilisent leur langue
de base. Le rapport local `get_report` utilise aussi ce choix.

Changer uniquement la langue ne change ni les destinataires, ni l'interrupteur,
ni les incidents. Cela ne déclenche aucun email et ne rejoue pas les envois
acceptés. Une prochaine tentative légitime utilise la nouvelle langue.
L'activation, en revanche, peut envoyer une alerte active fraîchement confirmée.
Le bouton **Envoyer un email de test** envoie réellement aux destinataires
sélectionnés lorsque les emails sont activés.

L'interface possède des traductions natives EN/FR/ES/DE et suit les mécanismes
HA, avec l'anglais comme base. Les noms personnalisés et les identifiants ne
changent pas. Le récapitulatif dynamique, les notifications persistantes et les
explications diagnostiques suivent la langue système HA, pas la langue email ni
le profil frontend de chaque utilisateur. Les codes et dictionnaires techniques
restent stables. Les légendes rédigées dans le tableau de bord d'exemple sont en
anglais et peuvent être adaptées.

Vous pouvez régler les rappels et l'envoi facultatif dès le stade de
surveillance. Guard vérifie le registre des entités,
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

### Contenu des rapports

Depuis la version 0.4.0, le rapport montre côte à côte le débit actuel et la
capture **immuable au déclenchement du niveau d'alerte affiché**. L'ouverture
en surveillance et une éventuelle escalade urgente ont des captures distinctes.
Les rappels conservent cette capture ; la récupération affiche le retour stable
confirmé et l'incident clôturé. Les heures de rapport HA, de décision,
d'ouverture, d'escalade et la durée réellement observée sont distinguées.
Un défaut natif sans débit exploitable affiche une valeur indisponible, pas zéro.
Pour un incident antérieur à cette version, le débit exact au déclenchement reste
inconnu : aucun débit actuel ou historique voisin ne le remplace.

Le graphique couvre **cinq jours calendaires dans le fuseau HA**, aujourd'hui
étant indiqué partiel, avec prise en compte des changements d'heure. Toutes
les valeurs sont en L/min, après conversion des unités source. Les barres HTML
rouges partagent une échelle partant de zéro, sans image distante ni suivi.

La collecte est locale et commence avec cette version, **sans rattrapage
Recorder**. Le premier contrôle de chaque minute UTC peut fournir un échantillon
frais admissible, via le minuteur existant de 15 secondes ou les événements
source. Les rafales de changements ne donnent pas davantage de poids à une
minute. Une valeur inchangée reste échantillonnable jusqu'à sa limite de fraîcheur,
sans devenir une nouvelle preuve de persistance. Arrêts, démarrages, dégivrages,
sources périmées/manquantes et interruptions restent des lacunes.
Aucun remplissage ni rattrapage après redémarrage n'est effectué.

Médiane et minimum décrivent ces échantillons, pas toutes les mesures brutes.
La couverture indique les créneaux minute comparables sur les créneaux
calendaires écoulés, y compris ceux où la PAC ne fonctionne pas. Ce n'est
**pas une durée continue mesurée**. Il faut au moins deux échantillons dans
chaque journée comparée ; une faible couverture ne prouve pas une journée
représentative. Le pourcentage compare les première et dernière médianes
journalières exploitables affichées, avec leurs dates, et reste indisponible
si la première médiane vaut zéro. Un jour manquant interdit de conclure à cinq
jours consécutifs de baisse. Une baisse des médianes ne signifie pas que chaque
mesure individuelle baisse.
La conclusion sur cinq jours exige aussi une observation à chaque créneau
minute écoulé, sans lacune de contexte inconnu ou périmé. Sinon, la preuve
est indiquée insuffisante, même si un pourcentage entre médianes disponibles
peut être calculé.
Un repos/dégivrage identifié fraîchement, une circulation confirmée arrêtée
ou un autre mode connu constituent des **exclusions observées**, même si le
débit n'est plus rapporté pendant ces périodes. Ce ne sont pas des trous inconnus
et la PAC n'a pas à tourner 24 h/24. Un mode manquant ou périmé ne suffit pas
à justifier une exclusion. L'objet signale d'emblée un historique partiel ;
son pourcentage limité aux points disponibles reste dans l'annexe technique.

Le mode, l'état de circulation et, si elle est connue, la vitesse avec sa
tolérance sont comparés au contexte capturé de l'alerte, ou au contexte actuel
frais en l'absence de capture. Sans vitesse mesurée, cette limite est explicite :
les conditions hydrauliques ne sont pas garanties identiques. Un changement de
sources ou de règles invalide cet historique ; un renommage suivi par le registre
préserve l'identité. Les modes chauffage/ECS et les vitesses incompatibles ne
sont pas mélangés.

Recorder ne permet pas de reconstituer avec certitude la fréquence des rapports
inchangés et leur fraîcheur. Son absence n'empêche donc ni ce rapport ni une
alerte. Le graphique du tableau de bord natif reste, lui, dépendant de Recorder.
Les jours initiaux vides sont normaux : attendre cinq jours calendaires de collecte.
La rétention locale est bornée à six jours et 8 641 échantillons compacts par
instance, sauvegardés environ toutes les cinq minutes et au déchargement.
Les captures d'incident et changements de livraison sont sauvegardés immédiatement.
Une panne peut perdre les derniers échantillons non sauvegardés, jamais en créer.
Les 120 derniers points bruts restent en annexe, sans alimenter ce graphique.

La version 0.4.0 accepte l'ancien stockage et écrit le schéma de données/moteur 2.
Avant son premier chargement, conserver une sauvegarde HA privée normale en
plus du dossier précédent du composant. Une simple copie de fichiers sans
redémarrage ne migre pas encore l'état. Après sauvegarde au schéma 2, un retour
à 0.3.0 exige la sauvegarde HA compatible d'avant mise à jour, pas seulement les
anciens fichiers Python. Ne pas modifier `.storage` manuellement.

Ce contexte ne crée pas de nouveau seuil d'alerte et ne calibre jamais une
référence automatiquement. Une baisse persistante peut justifier une inspection
professionnelle des filtres et du circuit. Nettoyer seulement si l'encrassement
est confirmé, conformément au fabricant ; circulateur, vannes, air et capteurs
restent des causes possibles. Ce n'est pas un dispositif de sécurité.

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
La carte d'état affiche aussi les limites du diagnostic. Le minimum non
renseigné apparaît inconnu, jamais comme un zéro inventé. L'observation seule
ou le suivi relatif ne constituent pas une protection complète.

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
