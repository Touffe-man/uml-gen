import tree_sitter_cpp as tscpp
from tree_sitter import Language, Parser

CPP_LANGUAGE = Language(tscpp.language())
parser = Parser(CPP_LANGUAGE)

with open("test_state.cpp", "rb") as f:
    source = f.read()

tree = parser.parse(source)

def print_tree(node, indent=0):
    print(" " * indent + f"{node.type}: {repr(source[node.start_byte:node.end_byte].decode()[:40])}")
    for child in node.children:
        print_tree(child, indent + 2)

print_tree(tree.root_node)