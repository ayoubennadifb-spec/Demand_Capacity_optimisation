# Simulateur Capacité–Commande — Maghreb Steel (site de Tit Mellil)

**Live Demo:** https://maghreb-steel-planning-studio-preview.onrender.com

Projet de Recherche Opérationnelle — **EMINES – UM6P**, promotion 2028.
Cas d'application réel proposé par **Maghreb Steel** (laminage à froid, Tit Mellil).

**Équipe :** Ayoub EN-NADIF · Ennaji Soufiane · Tarik Elbaraka · Hakim Abdelhakim · Amine Oubella.

Le simulateur arbitre, sur un horizon de **4 semaines**, entre un carnet de
**66 commandes** (~17 200 T, volontairement supérieur à la capacité) et les
capacités de l'usine, afin de **maximiser la marge sur coût variable** sous
contraintes de capacité machine, flux métallurgique, disponibilité du HRC et
stocks de produits finis. C'est un **programme linéaire** (continu) résolu avec
PuLP/CBC en moins d'une seconde ; les bonus ajoutent retards, stockage, et
campagnes (MILP).

## Résultats de référence
| Indicateur | Valeur |
|---|---|
| Statut solveur | **Optimal** (CBC, < 1 s) |
| Marge sur coût variable | **34 190 405 MAD** (≈ 34,19 MMAD) |
| Taux de service | **79,8 %** (13 536 / 16 958 T) — **50/65 commandes pleines** |
| Commandes non honorées | 15 (11 refus + 4 partielles) |
| Goulot dominant | **LGA semaine 1** (shadow price 588 355 MAD/jour) |
| Matière la plus tendue | HRC **S320** (épuisé), puis DX51 / DX52 |

> Baseline = marge (O1) + règle galva + stocks PF + **stock PK qualifié par grade** (net du min de
> sécurité, clarification de l'encadrement). Variante `objectif="nb_commandes"` : **55/65** commandes
> pour −1,49 MMAD.
>
> Validation **indépendante du solveur** : toutes les contraintes sont revérifiées à partir des seules
> valeurs de production (tolérance 1e-4 T, cohérente avec CBC) → **TOUT OK**.

## Structure du dépôt
```
simulateur_maghreb_steel/
├── data/        Donnees_MaghrebSteel.xlsx        (source de données, 9 onglets)
├── src/         code source (package Python)
│   ├── config.py        constantes, routes métallurgiques, options (toggles)
│   ├── data_loader.py   lecture rigoureuse de l'Excel + contrôles
│   ├── routes.py        coefficients par (commande, route) : rendements, marge
│   ├── model.py         construction du PL/MILP PuLP (E5–E10, B2/B3/B4)
│   ├── solve.py         résolution CBC + extraction (duales, coûts réduits)
│   ├── validation.py    revérification indépendante des contraintes (E15)
│   ├── reporting.py     KPIs, plan de marche, shadow prices, refus, figures
│   ├── sensitivity.py   scénarios E20/E21/E22 + B8 (enveloppe) + B9 (robustesse)
│   └── extensions.py    B5 : statistiques Branch-and-Bound du MILP campagnes
├── app/         streamlit_app.py                 application interactive (B6)
├── tests/       tests unitaires pytest (30 tests)
├── outputs/     résultats générés (Excel, CSV, JSON, figures)
├── rapport/     rapport technique (LaTeX + PDF)
├── main.py      orchestrateur : lecture → modèle → résolution → validation → export
├── requirements.txt
└── PROGRESS.md  suivi d'avancement
```

## Installation
Python **3.10+** (testé sur 3.12).
```bash
cd simulateur_maghreb_steel
python -m venv .venv && . .venv/Scripts/activate    # Windows ; (source .venv/bin/activate sous Linux/Mac)
pip install -r requirements.txt
```
Le solveur **CBC** est livré avec PuLP — aucune installation séparée n'est requise.

## Utilisation
```bash
# Pipeline complet : résout, valide, exporte, affiche tous les indicateurs (E13–E19)
python main.py

# + analyse de sensibilité (E20 HRC+10 %, E21 panne LGB, E22 commande urgente, B9, coût galva)
python main.py --sensibilite

# Variante MILP avec campagnes (B4) + statistiques de Branch-and-Bound (B5)
python main.py --campagnes

# Analyse "sans la règle galva" (choix LGA/LGB du HDG laissé libre)
python main.py --sans-galva

# Modules exécutables individuellement
python -m src.solve          # résolution + KPIs + top shadow prices
python -m src.validation     # validation indépendante (E15)
python -m src.reporting      # toutes les tables + exports outputs/
python -m src.sensitivity    # scénarios de sensibilité
python -m src.extensions     # B4/B5 campagnes + Branch-and-Bound

# Tests unitaires
python -m pytest -q

# Application interactive de planification (bonus B6)
streamlit run app/streamlit_app.py
```
> **Windows** : si la console plante sur un caractère Unicode, exporter
> `set PYTHONIOENCODING=utf-8` (les points d'entrée le configurent déjà).

## Déploiement en ligne (Streamlit Community Cloud)
L'application se déploie gratuitement et publiquement :
1. **Pousser ce dossier** (`simulateur_maghreb_steel/` = racine du dépôt) sur un dépôt **GitHub public**.
   Doivent être versionnés : `requirements.txt`, `packages.txt`, `app/streamlit_app.py`, `src/`,
   `data/Donnees_MaghrebSteel.xlsx`, `.streamlit/config.toml`.
2. Aller sur **share.streamlit.io** → *New app* → autoriser GitHub.
3. Renseigner : *Repository* = votre dépôt · *Branch* = `main` ·
   **Main file path** = `app/streamlit_app.py` · *Advanced settings* → Python **3.12**.
4. *Deploy*. Streamlit installe `requirements.txt` (et `coinor-cbc` via `packages.txt`) puis lance l'app.

Notes : le solveur **CBC** est fourni par PuLP ; `packages.txt` n'est qu'un filet de sécurité. L'app
n'écrit rien sur le disque (le téléchargement du plan est généré en mémoire), ce qui convient au
système de fichiers éphémère du cloud.

## Fichiers de sortie (`outputs/`)
- `kpis.json` — indicateurs globaux (marge, taux de service, refus).
- `plan_de_marche.xlsx` — plan par famille×semaine, charge par ligne, utilisation,
  marges, refus, shadow prices (un onglet chacun).
- `commandes_refusees.csv` — commandes non honorées + **contrainte bloquante** (tracée par les duales).
- `shadow_prices.csv` — valeurs marginales des ressources saturées.
- `figures/` — utilisation des lignes, marge par famille, courbe d'enveloppe.

## Choix de modélisation (options `ModelOptions`)
| Option | Défaut | Question | Effet |
|---|---|---|---|
| `galva_rule_hdg` | `True` | hypothèse | HDG ep≤0,6→LGA, >0,6→LGB. **Hors note de cadrage** : conservée par choix, documentée, coût chiffré (≈ −3,19 MMAD). |
| `inclure_stock_pk` | `True` | clarif. prof | ajoute le stock PK qualifié par grade à la matière dispo (net du min sécurité). |
| `stocks_pf` | `True` | E8 | bilans de stock produits finis + bornes min/max. |
| `objectif` | `"marge"` | O1 / prof | `"marge"` (O1) ou `"nb_commandes"` (max nombre de commandes, MILP accept/reject). |
| `retards_autorises` | `False` | B2 | livraison après échéance pénalisée. |
| `cout_stockage` | `False` | B3 | coûts de stockage dans l'objectif. |
| `campagnes` | `False` | B4 | binaires de campagne (= une famille/ligne/semaine) + tonnage minimum (MILP). |

## Correspondance questions ↔ code
- **E1–E4, E10, E23–E24, B1, B10** : analyse rédigée dans `rapport/`.
- **E5–E9** (formulation) : `model.py` + `routes.py` ; **E11** solveur : `requirements.txt` / `rapport/`.
- **E12** implémentation : `main.py` + `src/` ; **E13–E14** : `reporting.py` ; **E15** : `validation.py`.
- **E16–E19** : `reporting.py` ; **E20–E22, B8, B9** : `sensitivity.py` ; **B7** : `reporting.commandes_extremes`.
- **B2/B3/B4** : options de `model.py` ; **B5** : `extensions.py` ; **B6** : `app/streamlit_app.py`.

## Données
Toutes les valeurs sont **synthétiques** (ordres de grandeur réalistes, fournies
par l'énoncé). Elles ne représentent pas la situation réelle de Maghreb Steel et
ne doivent pas être utilisées hors du cadre académique.

## Déclaration d'utilisation d'IA
Conformément à la politique du projet, un assistant IA a aidé à la **syntaxe
PuLP/openpyxl, au débogage et à la mise en forme**. La formulation mathématique,
l'interprétation des résultats et les recommandations sont comprises et
défendues par les membres du groupe (détail en annexe du rapport).
