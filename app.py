from flask import Flask, request, jsonify, send_from_directory
import tree_sitter_cpp as tscpp
from tree_sitter import Language, Parser
import zipfile
import io

app = Flask(__name__)

CPP_LANGUAGE = Language(tscpp.language())
parser = Parser(CPP_LANGUAGE)

def get_text(source, node):
    return source[node.start_byte:node.end_byte].decode("utf-8")

def parse_class(source, node, namespace=None):
    result = {"name": "", "attributes": [], "methods": [], "parents": [], "namespace": namespace}

    for child in node.children:
        if child.type == "type_identifier":
            result["name"] = get_text(source, child)
        elif child.type == "base_class_clause":
            for base in child.children:
                if base.type == "type_identifier":
                    result["parents"].append(get_text(source, base))
        elif child.type == "field_declaration_list":
            for member in child.children:
                if member.type == "field_declaration":
                    has_func = any(c.type == "function_declarator" for c in member.children)
                    type_node = next((c for c in member.children if c.type in ("primitive_type", "type_identifier", "qualified_identifier")), None)
                    name_node = next((c for c in member.children if c.type == "field_identifier"), None)
                    if not name_node:
                        for c in member.children:
                            if c.type == "function_declarator":
                                name_node = next((x for x in c.children if x.type == "field_identifier"), None)
                    type_str = get_text(source, type_node) if type_node else "?"
                    name_str = get_text(source, name_node) if name_node else "?"
                    if has_func:
                        result["methods"].append({"name": name_str, "return_type": type_str})
                    else:
                        result["attributes"].append({"name": name_str, "type": type_str})

    return result

def to_mermaid(classes):
    lines = ["classDiagram"]
    class_names = {c["name"] for c in classes}
    full_names = {}  # name -> qualified name
    relations = []

    for c in classes:
        full = f'{c["namespace"]}_{c["name"]}' if c["namespace"] else c["name"]
        full_names[c["name"]] = full

    for c in classes:
        full = full_names[c["name"]]
        display = f'{c["namespace"]}::{c["name"]}' if c["namespace"] else c["name"]
        lines.append(f'    class {full} ["{display}"] {{')
        for attr in c["attributes"]:
            lines.append(f'        +{attr["type"]} {attr["name"]}')
        for method in c["methods"]:
            lines.append(f'        +{method["name"]}() {method["return_type"]}')
        lines.append("    }")

    for c in classes:
        full = full_names[c["name"]]
        for attr in c["attributes"]:
            # gère Hardware::Moteur → extrait "Moteur"
            attr_type = attr["type"].split("::")[-1]
            if attr_type in class_names:
                lines.append(f'    {full} --> {full_names[attr_type]}')
        for parent in c["parents"]:
            parent_base = parent.split("::")[-1]
            if parent_base in full_names:
                lines.append(f'    {full} --|> {full_names[parent_base]}')

    return "\n".join(lines)

def extract_classes(source, tree):
    classes = []
    
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
            classes.append(parse_class(source, node, namespace=namespace))
        else:
            for child in node.children:
                walk(child, namespace=namespace)
    
    walk(tree.root_node)
    return classes

def parse_statechar(source, tree):
    states = set()
    transitions = []

    def find_switch(node):
        if node.type == "switch_statement":
            # extraire la variable switchée (ex: "etat")
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
            # cherche les assignments etat = NEXT_STATE
            find_transitions(child, current_state)

    def find_transitions(node, current_state):
        if node.type == "assignment_expression":
            children = list(node.children)
            if len(children) >= 3 and children[1].type == "=":
                target = get_text(source, children[2])
                if target in states or True:  # on collecte tout, on filtrera après
                    transitions.append((current_state, target))
        for child in node.children:
            find_transitions(child, current_state)

    find_switch(tree.root_node)

    # filtrer les transitions dont la cible est un état connu
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


# -------------------- ROUTES --------------------
@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json()
    if not data or "code" not in data:
        return jsonify({"error": "Champ 'code' manquant"}), 400
    
    source = data["code"].encode("utf-8")
    tree = parser.parse(source)
    
    classes = extract_classes(source, tree)
    
    return jsonify({"mermaid": to_mermaid(classes), "classes": classes})

@app.route("/analyze-zip", methods=["POST"])
def analyze_zip():
    if "file" not in request.files:
        return jsonify({"error": "Aucun fichier reçu"}), 400

    f = request.files["file"]
    if not f.filename.endswith(".zip"):
        return jsonify({"error": "Fichier .zip attendu"}), 400

    all_classes = []

    with zipfile.ZipFile(io.BytesIO(f.read())) as z:
        for name in z.namelist():
            if name.endswith((".cpp", ".h")) and not name.startswith("__"):
                with z.open(name) as code_file:
                    source = code_file.read()
                    tree = parser.parse(source)
                    all_classes.extend(extract_classes(source, tree))

    if not all_classes:
        return jsonify({"error": "Aucune classe trouvée dans le zip"}), 404

    return jsonify({
        "mermaid": to_mermaid(all_classes),
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

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

if __name__ == "__main__":
    app.run(debug=True)