import tree_sitter_cpp as tscpp
from tree_sitter import Language, Parser

CPP_LANGUAGE = Language(tscpp.language())
parser = Parser(CPP_LANGUAGE)

with open("test.cpp", "rb") as f:
    source = f.read()

tree = parser.parse(source)

def get_text(node):
    return source[node.start_byte:node.end_byte].decode("utf-8")

def parse_class(node):
    result = {"name": "", "attributes": [], "methods": []}

    for child in node.children:
        if child.type == "type_identifier":
            result["name"] = get_text(child)
        elif child.type == "field_declaration_list":
            for member in child.children:
                if member.type == "field_declaration":
                    # Est-ce une méthode ou un attribut ?
                    has_func = any(c.type == "function_declarator" for c in member.children)
                    type_node = next((c for c in member.children if c.type in ("primitive_type", "type_identifier")), None)
                    name_node = next((c for c in member.children if c.type == "field_identifier"), None)
                    if not name_node:
                        for c in member.children:
                            if c.type == "function_declarator":
                                name_node = next((x for x in c.children if x.type == "field_identifier"), None)

                    type_str = get_text(type_node) if type_node else "?"
                    name_str = get_text(name_node) if name_node else "?"

                    if has_func:
                        result["methods"].append({"name": name_str, "return_type": type_str})
                    else:
                        result["attributes"].append({"name": name_str, "type": type_str})

    return result

classes = []
for node in tree.root_node.children:
    if node.type == "class_specifier":
        classes.append(parse_class(node))

for c in classes:
    print(c)

def to_mermaid(classes):
    lines = ["classDiagram"]
    
    # Noms de classes connus
    class_names = {c["name"] for c in classes}
    relations = []

    for c in classes:
        lines.append(f'    class {c["name"]} {{')
        for attr in c["attributes"]:
            lines.append(f'        +{attr["type"]} {attr["name"]}')
            if attr["type"] in class_names:
                relations.append(f'    {c["name"]} --> {attr["type"]}')
        for method in c["methods"]:
            lines.append(f'        +{method["name"]}() {method["return_type"]}')
        lines.append("    }")

    lines.extend(relations)
    return "\n".join(lines)

print(to_mermaid(classes))