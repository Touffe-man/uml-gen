from flask import Flask, request, jsonify, send_from_directory
import tree_sitter_cpp as tscpp
from tree_sitter import Language, Parser
import zipfile
import io
import requests as http_requests
import re
import os
import httpx
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")

app = Flask(__name__)

CPP_LANGUAGE = Language(tscpp.language())
parser = Parser(CPP_LANGUAGE)

def get_text(source, node):
    return source[node.start_byte:node.end_byte].decode("utf-8")

def get_full_type(source, node):
    """Extrait un type complet incluant templates, pointeurs, références."""
    txt = get_text(source, node).strip()
    # Nettoie les espaces multiples
    txt = re.sub(r'\s+', ' ', txt)
    return txt

def parse_params(source, params_node):
    """Extrait les paramètres d'une fonction : [(type, name), ...]"""
    params = []
    if params_node is None:
        return params
    
    for child in params_node.children:
        if child.type == "parameter_declaration":
            # Récupère tout le texte du paramètre et on le nettoie
            full = get_text(source, child).strip()
            full = re.sub(r'\s+', ' ', full)
            # Sépare type et nom : dernier token = nom si pas un type pur
            parts = full.rsplit(' ', 1)
            if len(parts) == 2:
                ptype = parts[0].strip().lstrip('(').rstrip(',')
                pname = parts[1].strip().rstrip(')').rstrip(',')
                # Si le nom ressemble à un identifiant valide
                if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', pname):
                    params.append((ptype, pname))
                else:
                    params.append((full, ''))
            else:
                params.append((full, ''))
    return params

def parse_class(source, node, namespace=None, is_struct=False):
    result = {
        "name": "",
        "attributes": [],
        "methods": [],
        "parents": [],
        "namespace": namespace,
        "is_struct": is_struct
    }

    for child in node.children:
        if child.type == "type_identifier":
            result["name"] = get_text(source, child)

        elif child.type == "base_class_clause":
            for base in child.children:
                if base.type in ("type_identifier", "qualified_identifier"):
                    result["parents"].append(get_text(source, base))

        elif child.type == "field_declaration_list":
            # struct = public par défaut, class = private par défaut
            current_access = "public" if is_struct else "private"

            for member in child.children:
                if member.type == "access_specifier":
                    current_access = get_text(source, member).replace(":", "").strip()

                elif member.type == "field_declaration":
                    _parse_field(source, member, current_access, result)

                elif member.type in ("function_definition",):
                    _parse_inline_method(source, member, current_access, result)

    return result

def _parse_field(source, member, current_access, result):
    """Parse un field_declaration (attribut ou méthode déclarée)."""
    visibility = "+" if current_access == "public" else ("-" if current_access == "private" else "#")

    # Détecte si c'est une méthode (contient function_declarator)
    func_decl = next((c for c in member.children if c.type == "function_declarator"), None)
    
    # Cherche le type — on prend tout sauf le declarator
    type_parts = []
    for c in member.children:
        if c.type in ("primitive_type", "type_identifier", "qualified_identifier",
                      "template_type", "pointer_type", "reference_declarator",
                      "type_qualifier", "storage_class_specifier"):
            type_parts.append(get_text(source, c).strip())
        elif c.type == "scoped_type_identifier":
            type_parts.append(get_text(source, c).strip())
    
    type_str = ' '.join(type_parts).strip() or "?"

    if func_decl:
        # C'est une méthode
        name_node = next((c for c in func_decl.children if c.type in ("field_identifier", "identifier")), None)
        params_node = next((c for c in func_decl.children if c.type == "parameter_list"), None)
        name_str = get_text(source, name_node) if name_node else "?"
        params = parse_params(source, params_node)
        param_str = ", ".join(f"{t} {n}".strip() for t, n in params)
        result["methods"].append({
            "name": name_str,
            "return_type": type_str,
            "params": param_str,
            "visibility": visibility
        })
    else:
        # C'est un attribut — cherche le nom
        name_node = None
        for c in member.children:
            if c.type == "field_identifier":
                name_node = c
                break
            elif c.type == "pointer_declarator":
                name_node = next((x for x in c.children if x.type == "field_identifier"), None)
                if name_node:
                    type_str = type_str + "*"
                    break
            elif c.type == "reference_declarator":
                name_node = next((x for x in c.children if x.type == "field_identifier"), None)
                if name_node:
                    type_str = type_str + "&"
                    break
            elif c.type == "array_declarator":
                name_node = next((x for x in c.children if x.type == "field_identifier"), None)
                if name_node:
                    break

        name_str = get_text(source, name_node) if name_node else "?"
        result["attributes"].append({
            "name": name_str,
            "type": type_str,
            "visibility": visibility
        })

def _parse_inline_method(source, node, current_access, result):
    """Parse une méthode définie inline dans la classe."""
    visibility = "+" if current_access == "public" else ("-" if current_access == "private" else "#")
    
    # Cherche le type de retour
    type_parts = []
    func_decl = None
    for c in node.children:
        if c.type == "function_declarator":
            func_decl = c
            break
        elif c.type in ("primitive_type", "type_identifier", "qualified_identifier", "template_type"):
            type_parts.append(get_text(source, c).strip())
    
    type_str = ' '.join(type_parts).strip() or "void"
    
    if func_decl:
        name_node = next((c for c in func_decl.children if c.type in ("field_identifier", "identifier")), None)
        params_node = next((c for c in func_decl.children if c.type == "parameter_list"), None)
        name_str = get_text(source, name_node) if name_node else "?"
        params = parse_params(source, params_node)
        param_str = ", ".join(f"{t} {n}".strip() for t, n in params)
        result["methods"].append({
            "name": name_str,
            "return_type": type_str,
            "params": param_str,
            "visibility": visibility
        })

def parse_enum(source, node, namespace=None):
    """Parse un enum class/struct."""
    result = {"name": "", "values": [], "namespace": namespace}
    for child in node.children:
        if child.type == "type_identifier":
            result["name"] = get_text(source, child)
        elif child.type == "enumerator_list":
            for item in child.children:
                if item.type == "enumerator":
                    val_node = next((c for c in item.children if c.type == "identifier"), None)
                    if val_node:
                        result["values"].append(get_text(source, val_node))
    return result

def to_mermaid(classes, enums=None):
    lines = ["classDiagram"]
    class_names = {c["name"] for c in classes}
    full_names = {}
    relations = []

    enums = enums or []

    for c in classes:
        full = f'{c["namespace"]}_{c["name"]}' if c["namespace"] else c["name"]
        full_names[c["name"]] = full

    # Classes et structs
    for c in classes:
        full = full_names[c["name"]]
        display = f'{c["namespace"]}::{c["name"]}' if c["namespace"] else c["name"]
        lines.append(f'    class {full} ["{display}"] {{')
        if c.get("is_struct"):
            lines.append(f'        <<struct>>')
        for attr in c["attributes"]:
            v = attr.get("visibility", "+")
            # Échappe les caractères spéciaux Mermaid dans le type
            t = attr["type"].replace("<", "~").replace(">", "~")
            lines.append(f'        {v}{t} {attr["name"]}')
        for method in c["methods"]:
            v = method.get("visibility", "+")
            t = method["return_type"].replace("<", "~").replace(">", "~")
            params = method.get("params", "")
            params = params.replace("<", "~").replace(">", "~")
            lines.append(f'        {v}{method["name"]}({params}) {t}')
        lines.append("    }")

    # Enums
    for e in enums:
        full = f'{e["namespace"]}_{e["name"]}' if e["namespace"] else e["name"]
        display = f'{e["namespace"]}::{e["name"]}' if e["namespace"] else e["name"]
        lines.append(f'    class {full} ["{display}"] {{')
        lines.append(f'        <<enumeration>>')
        for v in e["values"]:
            lines.append(f'        {v}')
        lines.append("    }")

    # Relations
    for c in classes:
        full = full_names[c["name"]]
        for attr in c["attributes"]:
            # Extrait le type de base (sans *, &, templates)
            attr_type = re.sub(r'[*&]', '', attr["type"]).strip()
            attr_type = attr_type.split("::")[-1].split("<")[0].strip()
            if attr_type in class_names:
                relations.append(f'    {full} --> {full_names[attr_type]}')
        for parent in c["parents"]:
            parent_base = parent.split("::")[-1].split("<")[0].strip()
            if parent_base in full_names:
                relations.append(f'    {full} --|> {full_names[parent_base]}')

    lines.extend(relations)
    return "\n".join(lines)

def extract_classes(source, tree):
    classes = []
    enums = []

    def walk(node, namespace=None):
        if node.type == "namespace_definition":
            ns_name = None
            for child in node.children:
                if child.type == "namespace_identifier":
                    ns_name = get_text(source, child)
            for child in node.children:
                if child.type == "declaration_list":
                    for sub in child.children:
                        walk(sub, namespace=ns_name)

        elif node.type == "class_specifier":
            classes.append(parse_class(source, node, namespace=namespace, is_struct=False))

        elif node.type == "struct_specifier":
            classes.append(parse_class(source, node, namespace=namespace, is_struct=True))

        elif node.type == "enum_specifier":
            # Seulement enum class/struct (pas les enums C basiques sans nom)
            e = parse_enum(source, node, namespace=namespace)
            if e["name"]:
                enums.append(e)

        else:
            for child in node.children:
                walk(child, namespace=namespace)

    walk(tree.root_node)
    return classes, enums

def parse_statechar(source, tree):
    states = set()
    transitions = []

    def find_switch(node):
        if node.type == "switch_statement":
            for child in node.children:
                if child.type == "compound_statement":
                    for case_node in child.children:
                        if case_node.type == "case_statement":
                            parse_case(case_node)
        for child in node.children:
            find_switch(child)

    def parse_case(case_node):
        current_state = None
        for child in case_node.children:
            if child.type == "identifier" and current_state is None:
                current_state = get_text(source, child)
                states.add(current_state)
            find_transitions(child, current_state)

    def find_transitions(node, current_state):
        if node.type == "assignment_expression":
            children = list(node.children)
            if len(children) >= 3 and children[1].type == "=":
                target = get_text(source, children[2])
                if target in states or True:
                    transitions.append((current_state, target))
        for child in node.children:
            find_transitions(child, current_state)

    find_switch(tree.root_node)

    real_transitions = [(s, t) for s, t in transitions if t in states]
    return states, real_transitions


def to_statemermaid(states, transitions):
    lines = ["stateDiagram-v2"]
    if states:
        first = next(iter(states))
        lines.append(f"    [*] --> {first}")
    for src, dst in transitions:
        lines.append(f"    {src} --> {dst}")
    return "\n".join(lines)

def extract_includes(source_text, filename):
    """Extrait les #include d'un fichier source."""
    includes = []
    for match in re.finditer(r'#include\s*["<]([^">]+)[">]', source_text):
        inc = match.group(1)
        # Garde seulement les includes locaux (pas <Arduino.h>, <vector>...)
        if not inc.startswith('/') and '.' in inc:
            includes.append(os.path.basename(inc))
    return includes

def to_dependency_mermaid(dep_graph):
    """Génère un diagramme de dépendances Mermaid."""
    lines = ["graph TD"]
    # Noeuds : nom de fichier sans extension comme identifiant
    def node_id(name):
        return re.sub(r'[^a-zA-Z0-9_]', '_', name.replace('.', '_'))

    added = set()
    for src, targets in dep_graph.items():
        sid = node_id(src)
        if sid not in added:
            lines.append(f'    {sid}["{src}"]')
            added.add(sid)
        for tgt in targets:
            tid = node_id(tgt)
            if tid not in added:
                lines.append(f'    {tid}["{tgt}"]')
                added.add(tid)
            lines.append(f'    {sid} --> {tid}')

    return "\n".join(lines)

# -------------------- ROUTES --------------------
@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    if not data or "code" not in data:
        return jsonify({"error": "Champ 'code' manquant"}), 400
    
    source = data["code"].encode("utf-8")
    tree = parser.parse(source)
    
    classes, enums = extract_classes(source, tree)
    if not classes:
        return jsonify({"error": "Aucune classe trouvée dans ce fichier"}), 404

    return jsonify({"mermaid": to_mermaid(classes, enums), "classes": classes})

@app.route("/analyze-zip", methods=["POST"])
def analyze_zip():
    if "file" not in request.files:
        return jsonify({"error": "Aucun fichier reçu"}), 400

    f = request.files["file"]
    if not f.filename.endswith(".zip"):
        return jsonify({"error": "Fichier .zip attendu"}), 400

    all_classes = []
    all_enums = []

    with zipfile.ZipFile(io.BytesIO(f.read())) as z:
        for name in z.namelist():
            if name.endswith((".cpp", ".h")) and not name.startswith("__"):
                with z.open(name) as code_file:
                    source = code_file.read()
                    tree = parser.parse(source)
                    c, e = extract_classes(source, tree)
                    all_classes.extend(c)
                    all_enums.extend(e)

    if not all_classes:
        return jsonify({"error": "Aucune classe trouvée dans le zip"}), 404

    return jsonify({
        "mermaid": to_mermaid(all_classes, all_enums),
        "classes": all_classes
    })

@app.route("/analyze-state", methods=["POST"])
def analyze_state():
    data = request.get_json()
    if not data or "code" not in data:
        return jsonify({"error": "Champ 'code' manquant"}), 400
    
    source = data["code"].encode("utf-8")
    tree = parser.parse(source)
    states, transitions = parse_statechar(source, tree)

    if not states:
        return jsonify({"error": "Aucun switch/case détecté"}), 404

    return jsonify({
        "mermaid": to_statemermaid(states, transitions),
        "states": list(states),
        "transitions": transitions
    })

@app.route("/analyze-github", methods=["POST"])
def analyze_github():
    data = request.get_json()
    if not data or "url" not in data:
        return jsonify({"error": "Champ 'url' manquant"}), 400

    url = data["url"].strip()

    # Extraire user/repo depuis l'URL
    match = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if not match:
        return jsonify({"error": "URL GitHub invalide (ex: https://github.com/user/repo)"}), 400

    user, repo = match.group(1), match.group(2)

    # Récupérer la liste des fichiers via l'API GitHub (récursif)
    api_url = f"https://api.github.com/repos/{user}/{repo}/git/trees/HEAD?recursive=1"
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

    headers = {}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    r = http_requests.get(api_url, headers=headers, timeout=10)
    if r.status_code != 200:
        return jsonify({"error": f"Repo introuvable ou privé ({r.status_code})"}), 404

    tree = r.json().get("tree", [])
    cpp_files = [f for f in tree if f["type"] == "blob" and f["path"].endswith((".cpp", ".h"))]

    if not cpp_files:
        return jsonify({"error": "Aucun fichier .cpp/.h trouvé dans ce repo"}), 404

    # Limiter à 30 fichiers pour le MVP
    cpp_files = cpp_files[:30]

    all_classes = []
    all_enums = []
    for f in cpp_files:
        raw_url = f"https://raw.githubusercontent.com/{user}/{repo}/HEAD/{f['path']}"
        resp = http_requests.get(raw_url, headers=headers, timeout=10)
        if resp.status_code != 200:
            continue
        source = resp.content
        parsed_tree = parser.parse(source)
        c, e = extract_classes(source, parsed_tree)
        all_classes.extend(c)
        all_enums.extend(e)

    if not all_classes:
        return jsonify({"error": "Aucune classe trouvée dans ce repo"}), 404

    # Chercher le README
    readme_content = ""
    readme_file = next((f for f in tree if f["type"] == "blob" and f["path"].lower() in ("readme.md", "readme.txt", "readme")), None)
    if readme_file:
        r = http_requests.get(
            f"https://raw.githubusercontent.com/{user}/{repo}/HEAD/{readme_file['path']}",
            headers=headers, timeout=10
        )
        if r.status_code == 200:
            readme_content = r.text[:3000]  # limite pour pas exploser le prompt

    return jsonify({
        "mermaid": to_mermaid(all_classes, all_enums),
        "classes": all_classes,
        "files_analyzed": len(cpp_files),
        "readme": readme_content
    })

@app.route("/explain", methods=["POST"])
def explain():
    data = request.get_json()
    if not data or "mermaid" not in data:
        return jsonify({"error": "Champ 'mermaid' manquant"}), 400

    if not MISTRAL_API_KEY:
        return jsonify({"error": "Clé MISTRAL_API_KEY non configurée"}), 500

    readme_text = data.get("readme", "")
    readme_section = f"\nContexte du projet (README) :\n{readme_text}\n" if readme_text else ""

    prompt = f"""Tu es un expert en architecture logicielle C++ et systèmes embarqués.
    {readme_section}
    Analyse ce diagramme UML Mermaid (classes, structs ET enumerations) et fournis :
    1. Une description courte de l'architecture générale
    2. Les design patterns détectés
    3. Les points forts
    4. Les points faibles ou risques
    5. Une suggestion d'amélioration

    Diagramme :
    {data['mermaid']}

    Réponds en français, de façon concise (max 300 mots)."""

    try:
        response = httpx.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {MISTRAL_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "mistral-small-latest",
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30
        )
        result = response.json()
        return jsonify({"explanation": result["choices"][0]["message"]["content"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/analyze-deps", methods=["POST"])
def analyze_deps():
    data = request.get_json()
    if not data or "code" not in data:
        return jsonify({"error": "Champ 'code' manquant"}), 400

    filename = data.get("filename", "file.cpp")
    source_text = data["code"]
    includes = extract_includes(source_text, filename)

    if not includes:
        return jsonify({"error": "Aucun #include local détecté"}), 404

    dep_graph = {os.path.basename(filename): includes}
    return jsonify({"mermaid": to_dependency_mermaid(dep_graph)})

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

if __name__ == "__main__":
    app.run(debug=True)