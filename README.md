# UML Gen

Analyse statique de code C++ et génération automatique de diagrammes d'architecture.

🔗 **[uml-gen.onrender.com](https://uml-gen.onrender.com)**

---

## Aperçu

UML Gen parse du code C++ via Tree-sitter et génère des diagrammes interactifs directement dans le navigateur. Aucune installation requise.

---

## Fonctionnalités

**Diagrammes**
- Classes — attributs, méthodes, visibilité, héritage, structs, enums
- Statecharts — détection des machines à états via switch/case
- Dépendances — graphe hiérarchique des `#include` internes

**Sources**
- Fichier unique `.cpp` / `.h`
- Archive `.zip` multi-fichiers
- Dépôt GitHub public (URL directe)

**Analyse IA**
- Explication de l'architecture via Mistral AI
- Détection de design patterns, points forts, risques, suggestions

**Export**
- SVG vectoriel
- PNG haute résolution

---

## Stack

| | |
|---|---|
| Backend | Python / Flask |
| Parsing | Tree-sitter (C++) |
| Diagrammes | Mermaid.js |
| Graphe de dépendances | D3.js + Dagre |
| IA | Mistral AI |
| Déploiement | Render |

---

## Lancer en local

```bash
git clone https://github.com/Touffe-man/uml-gen
cd uml-gen
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

```env
MISTRAL_API_KEY=...        # requis pour l'analyse IA
GITHUB_TOKEN=...           # optionnel — augmente le rate limit GitHub (60 → 5000 req/h)
```

```bash
python app.py
```

---
