<div align="center">
  <h1>Trackr</h1>
  <p>Une application Windows de tracking de temps d'écran 100% hors-ligne, élégante et ultra-légère.</p>
</div>

![Aperçu du Tableau de bord](screen1.png)

Trackr est votre compagnon de productivité. Il tourne discrètement en arrière-plan, analyse vos habitudes sur Windows et vous restitue des statistiques détaillées pour mieux comprendre où passe votre temps, tout cela en garantissant une confidentialité totale de vos données.

## ✨ Fonctionnalités

- 📊 **Tableau de bord intelligent** : Visualisez instantanément votre temps actif, inactif et l'application la plus utilisée de la journée.
- 📈 **Analyses & Graphiques (Chart.js)** : 
  - **Activité de la journée** : Frise chronologique heure par heure pour repérer vos pics de concentration.
  - **Top 5 Applications** : Classement détaillé de vos logiciels les plus chronophages avec leur durée exacte et pourcentage.
  - **Intensité (Semaine)** : Heatmap type "GitHub" montrant vos heures d'activité les plus intenses.
  - **Évolution par catégorie** : temps quotidien empilé par catégorie, comparaison avec la période précédente.
- 🕒 **Chronologie** : déroulé heure par heure de n'importe quelle journée, liste des sessions et fenêtres utilisées.
- 🧠 **Sessions & concentration** : nombre et durée des sessions, plus longues sessions, temps concentré (sessions ≥ 25 min), changements d'application par heure, pauses, heures moyennes de début et de fin de journée.
- 🔍 **Détail par application** : temps par jour et par heure, sessions, et titres de fenêtres les plus utilisés (sites, fichiers, projets...).
- 🕵️ **100% Hors-Ligne & Léger** : Aucune donnée ne quitte votre PC. Tout est stocké dans une base SQLite locale. La détection d'activité utilise l'API native Windows (`GetLastInputInfo`) pour un impact nul sur le CPU.
- ⚙️ **Configuration Flexible** :
  - Lancement automatique et silencieux (System Tray) avec Windows.
  - Intervalles d'actualisation ajustables.
  - Détection du mode plein écran (pour les jeux/films) et de l'inactivité désactivables.
  - Système de catégorisation d'applications entièrement personnalisable.
- 📉 **Export des données** : Exportez facilement vos logs complets au format CSV.
- 🎨 **Interface Moderne** : UI épurée développée avec PyWebView et TailwindCSS (Dark Mode).

## 🚀 Installation & Compilation

Si vous souhaitez modifier le code ou compiler vous-même l'application :

### Prérequis
- Python 3.10 ou supérieur
- Windows

### Instructions

1. Clonez ce dépôt.
2. Activez un environnement virtuel et installez les dépendances :
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. Lancez l'application en mode développement :
   ```powershell
   python run.py
   ```
4. **Compilez l'exécutable final (.exe)** :
   ```powershell
   python build.py
   ```
   *Un exécutable standalone (Trackr.exe) sera généré dans le dossier `dist/`.*

### 📦 Version portable

`Trackr.exe` est déjà une version portable : un seul fichier, sans installation ni droits administrateur. Il suffit de le copier où vous voulez (par exemple `C:\Outils\Trackr\Trackr.exe`) et de le lancer.

- **Prérequis sur le PC cible** : Windows 10 ou 11 avec le runtime **Microsoft Edge WebView2**. Il est présent par défaut sur Windows 11 et sur les Windows 10 à jour. Sinon, il s'installe depuis le site de Microsoft.
- **Où sont les données ?** L'exécutable est portable, mais pas les données. La configuration et la base (`config.json`, `trackr.db`) sont stockées dans `%APPDATA%\Trackr`, propre à chaque utilisateur Windows. Pour garder votre historique sur un autre PC, copiez ce dossier.
- **Premier lancement** : Windows SmartScreen peut afficher un avertissement, car l'exécutable n'est pas signé. Cliquez sur « Informations complémentaires » puis « Exécuter quand même ».
- Trackr démarre dans la zone de notification (près de l'horloge). Fermer la fenêtre la masque sans quitter l'application ; pour quitter, faites un clic droit sur l'icône puis « Quitter ».

### 🔁 Démarrage automatique avec Windows

L'option **« Démarrer avec Windows »** (Paramètres, activée par défaut) fonctionne aussi avec la version portable :

- À chaque lancement, `Trackr.exe` enregistre son propre chemin dans la clé de registre utilisateur `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, avec l'option `--hidden`. Aucun droit administrateur n'est requis. À l'ouverture de session, Trackr démarre donc caché dans la zone de notification.
- **Si vous déplacez l'exécutable**, l'ancien chemin n'est plus valide. Relancez `Trackr.exe` une fois depuis son nouvel emplacement : l'entrée de démarrage est mise à jour automatiquement.
- **Sur une clé USB ou un disque amovible**, le démarrage automatique échoue si le disque n'est pas branché à l'ouverture de session. Préférez un dossier sur le disque interne.
- Si Trackr a été désactivé dans *Paramètres Windows › Applications › Démarrage* (ou dans le Gestionnaire des tâches), Windows ignore l'entrée. La page Paramètres de Trackr le signale ; enregistrer avec l'option activée la réactive.
- Pour désactiver le démarrage automatique, décochez l'option et enregistrez. L'entrée est alors supprimée du registre.

> En mode développement (`python run.py`), l'entrée de démarrage n'est créée que si vous enregistrez les paramètres avec l'option activée. Elle lance alors `pythonw.exe run.py --hidden` depuis votre environnement virtuel.

## 🛠️ Stack Technique

- **Backend** : Python, SQLite3, `pywin32` (WinAPI), `psutil`, `pystray`.
- **Frontend** : PyWebView, HTML/Vanilla JS, Tailwind CSS, Chart.js, Lucide Icons.
- **Build** : PyInstaller.

---
*Analysez. Comprenez. Optimisez votre temps.*
