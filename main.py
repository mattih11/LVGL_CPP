import os
import re
import pycparser_fake_libc
from pycparser import parse_file, c_ast
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import ttk

def to_upper_camel_case(name):
    """Convert a string to UpperCamelCase."""
    return ''.join(word.capitalize() for word in name.split('_'))

def to_lower_case(name):
    """Convert a string to lowercase."""
    return name.lower()

def to_upper_case(name):
    """Convert a string to uppercase."""
    return name.upper()

def generate_class_methods(functions, lowercase_classname, base_functions):
    """Generate class methods based on the parsed functions."""
    methods = []
    for func in functions:
        if func["name"] in base_functions:
            continue  # Skip functions defined in the base class

        params = func["args"]
        param_names = [param["name"] for param in params]
        param_list = ", ".join(f"{param['type']} {param['name']}" for param in params)
        param_forward = ", ".join(str(param["name"]) for param in params)
        return_type = func["return_type"]
        method_name = re.sub(f"lv_{lowercase_classname}_", "", func["name"])

        methods.append(f"""
    {return_type} {method_name}({param_list}) {{
        return lv_{lowercase_classname}_{method_name}(getRoot().get(), {param_forward});
    }}
""")
    return "\n".join(methods)

def generate_class_enums(enums):
    """Generate `constexpr static` members for enums."""
    enum_lines = []
    #for enum_name, members in enums.items():
    #    for name, value in members.items():
    #        enum_line = f"    constexpr static int {name} = {value if value else enum_lines.count};"
    #        enum_lines.append(enum_line)
    return "\n".join(enum_lines)

def parse_and_generate_class(
    class_name, lowercase_classname, base_class, output_file,
    base_functions, base_enums, functions, enums
):
    """Generate the corresponding C++ class using pre-extracted details."""
    # Determine if this is a standalone class
    standalone = False
    for func in functions:
        #tqdm.write(f"[{class_name} | Function:] {func}")
        if func["name"] == f"lv_{lowercase_classname}_create":
            # Check if the first parameter is `lv_obj_t * parent`
            params = func["args"]
            tqdm.write(f"[Write: FunctionParams]{params[0]}")
            first_arg = params[0]
            tqdm.write(f"[Write: FunctionParams]{params[0]} | FirstArg:{first_arg["type"], first_arg["name"]}")
            if not params or not str.startswith(first_arg["type"],"lv_obj_t*"):
                standalone = True
            break

    # Generate methods and enums
    methods = generate_class_methods(functions, lowercase_classname, base_functions)
    enum_lines = generate_class_enums({k: v for k, v in enums.items() if k not in base_enums})

    include_guard = f"{class_name.upper()}_HPP"

    # Adjust class definition based on standalone or base class
    if standalone:
        constructor = f"""
    explicit {class_name}() {{
        setRoot(std::shared_ptr<lv_obj_t>(
            lv_{lowercase_classname}_create(),
            [](lv_obj_t* obj) {{ lv_obj_del(obj); }}
        ));
    }}
"""
        base_class_declaration = ""
    else:
        constructor = f"""
    explicit {class_name}({base_class}& parent)
        : {base_class}() {{
        setRoot(std::shared_ptr<lv_obj_t>(
            lv_{lowercase_classname}_create(parent.getRoot().get()),
            [](lv_obj_t* obj) {{ lv_obj_del(obj); }}
        ));
    }}
"""
        base_class_declaration = f" : public {base_class}"

    cpp_content = f"""\
#ifndef {include_guard}
#define {include_guard}

#include "{base_class}.hpp"

// {class_name} class, auto-generated
class {class_name}{base_class_declaration} {{
public:
{constructor}

    ~{class_name}() = default;

{methods}

{enum_lines}
}};

#endif // {include_guard}
"""

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w') as file:
        file.write(cpp_content)

    print(f"[INFO] Generated: {output_file}")

def process_and_generate_class(root, file, cpp_class, output_path):
    """Process a single file and generate a C++ class."""
    header_path = os.path.join(root, file)
    c_class = file.replace("lv_", "").replace(".h", "")
    class_name = to_upper_camel_case(c_class)
    lowercase_classname = to_lower_case(c_class)
    base_class = "BaseClass"  # Replace with actual base class if needed
    output_file = os.path.join(output_path, f"{class_name}.hpp")

    try:
        # Process the file and extract details
        process_single_file_with_details(root, file, cpp_class, "-I" + pycparser_fake_libc.directory)

        # Extract details from the processed data
        if c_class in cpp_class:
            data = cpp_class[c_class]
            functions = data["functions"]
            enums = {enum["name"]: enum["type"] for enum in data.get("typedefs", [])}
            variables = data["variables"]

            # Generate the class
            base_functions = []  # Define or load base functions
            base_enums = []  # Define or load base enums
            parse_and_generate_class(
                class_name, lowercase_classname, base_class, output_file,
                base_functions, base_enums, functions, enums
            )
        else:
            print(f"[WARNING] No data found for {c_class}")

    except Exception as e:
        print(f"[ERROR] Failed to process {header_path}: {e}")


class ASTVisitor(c_ast.NodeVisitor):
    def __init__(self, header_path):
        self.header_path = header_path
        self.functions = []
        self.variables = []
        self.typedefs = []
        self.includes = []

    # Function to filter nodes by source file
    def is_from_current_file(self, node):
        return node.coord and node.coord.file == self.header_path

    def visit_FuncDecl(self, node):
        # Check if the function declaration is from the current file
        if not self.is_from_current_file(node):
            return

        try:
            # Get the name of the function from its parent declaration

            if isinstance(node.type, c_ast.TypeDecl):
                func_name = getattr(node.type, "declname", None)
                return_type = getattr(node.type.type, "names", ["unknown"])[0]
            elif isinstance(node.type, c_ast.PtrDecl):
                func_name = getattr(node.type.type, "declname", None)
                tqdm.write(f"[Function] {func_name}")
                return_type = getattr(node.type.type.type, "names", ["unknown"])[0] + "*"
            else:
                func_name = None
                return_type = None
            if not func_name:
                return  # Skip if the function name is not available
            if str.endswith(func_name,"_create"):
                tqdm.write("constructor found")
            # Extract the return type (names list or default to "unknown")

            # Extract the function arguments
            args = []
            if node.args:
                for param in node.args.params:
                    if isinstance(param.type, c_ast.TypeDecl):
                        param_name = param.name or "unnamed"
                        param_type = getattr(param.type.type, "names", ["unknown"])
                        arg = {}
                        arg["name"] = param_name
                        if len(param_type) == 1:
                            arg["type"] = param_type[0]
                        else:
                            arg["type"] = param_type[0]
                        args.append(arg)
                    elif  isinstance(param.type, c_ast.PtrDecl):
                        param_name = param.name or "unnamed"
                        param_type = getattr(param.type.type.type, "names", ["unknown"])
                        arg = {}
                        arg["name"] = param_name
                        if len(param_type) == 1:
                            arg["type"] = param_type[0] + "*"
                        else:
                            arg["type"] = param_type[0]
                        args.append(arg)


            # Add the function details to the function list
            self.functions.append({
                "name": func_name,
                "return_type": return_type,
                "args": args,
                "ast" : node
            })

        except AttributeError as e:
            tqdm.write(f"[Skipping]: Error processing function for {self.header_path} - {str(e)}")

        # Continue visiting other nodes
        self.generic_visit(node)

    #def visit_Decl(self, node):
    #    if(not self.is_from_current_file(node)):
    #        return
    #    try:
    #        if isinstance(node.type, c_ast.TypeDecl):
    #            var_name = node.name
    #            tqdm.write(f"[Decl] {var_name}")
    #            var_type = getattr(node.type.type, "names", None)
    #            self.variables.append({"name": var_name, "type": var_type})
    #    except AttributeError as e:
    #        tqdm.write(f"[Skipping]: Error processing variable {node.name} - {str(e)}")
    #    self.generic_visit(node)

    def visit_Typedef(self, node):
        if(not self.is_from_current_file(node)):
            return
        try:
            typedef_name = node.name
            tqdm.write(f"[Typedef] {typedef_name}")
            typedef_type = getattr(node.type.type, "names", None)
            self.typedefs.append({"name": typedef_name, "type": typedef_type})
        except AttributeError as e:
            tqdm.write(f"[Skipping]: Error processing typedef {node.name} - {str(e)}")
        self.generic_visit(node)

    # Include visitor is skipped because pycparser doesn't preprocess includes directly
def process_folders(base_path, output_path, parallel=False):
    """Process all folders and generate detailed class data."""
    print(f"[INFO] Walking: {base_path}")

    # Collect all relevant files
    header_files = []
    for root, _, files in os.walk(base_path, topdown=False):
        for file in files:
            if file.endswith(".h") and file.startswith("lv_") and not file.endswith("_private.h"):
                header_files.append((root, file))

    print(f"{len(header_files)} files found")

    # Progress bar and thread pool for concurrent processing
    cpp_class = {}
    with tqdm(total=len(header_files), desc="Processing files", dynamic_ncols=True) as pbar:

        if parallel:
            with ThreadPoolExecutor() as executor:
                futures = [
                    executor.submit(process_and_generate_class, root, file, cpp_class, output_path)
                    for root, file in header_files
                ]

                for future in futures:
                    future.result()  # Ensure all tasks complete
                    pbar.update(1)
        else:
            for root, file in header_files:
                process_and_generate_class(root, file, cpp_class, output_path)
                pbar.update(1)

    print("[INFO] Class generation complete.")
    return cpp_class


def process_single_file_with_details(root, file, cpp_class, cpp_args=None):
    """
    Process a single file, extract functions, variables, typedefs, and headers,
    and add them to the cpp_class dictionary.
    """

    # Prepare paths
    header_path = os.path.join(root, file)
    c_class = file.replace("lv_", "").replace(".h", "")
    class_name = to_upper_camel_case(c_class)

    try:
        # Read and preprocess the header file
        with open(header_path, 'r') as original:
            data = original.read()

        temp_header_path = header_path + "_parse"
        with open(temp_header_path, 'w') as modified:
            modified.write("#define __attribute__(x)\n" + data)

        # Parse the file and extract AST data
        ast = parse_file(temp_header_path, use_cpp=True, cpp_args=cpp_args)

        # Extract details using the ASTVisitor
        visitor = ASTVisitor(temp_header_path)
        visitor.visit(ast)
        if len(visitor.functions) > 0 or len(visitor.variables) > 0 or len(visitor.typedefs) > 0 or len(visitor.includes) > 0:
            # Add the extracted details to the cpp_class dictionary
            cpp_class[c_class] = {
                "name": class_name,
                "functions": visitor.functions,
                "variables": visitor.variables,
                "typedefs": visitor.typedefs,
                "includes": visitor.includes,
                #"ast": visitor.ast,
            }

    except Exception as e:
        cpp_class[c_class] = {"error" : e}
        tqdm.write(f"[Skipping]: Compilation failed for {file} - {str(e)}")
    finally:
        # Clean up the temporary file
        if os.path.exists(header_path + "_parse"):
            os.remove(header_path + "_parse")

def show_tree_view(cpp_class):
    """
    Create a tree-like UI to display cpp_class data with fold/unfold functionality.
    """
    # Create the main Tkinter window
    root = tk.Tk()
    root.title("CppClass Tree Viewer")
    root.geometry("800x600")

    # Create a Treeview widget
    tree = ttk.Treeview(root)
    tree.pack(fill=tk.BOTH, expand=True)

    # Define columns
    tree["columns"] = ("Details",)
    tree.heading("#0", text="Class Structure", anchor=tk.W)
    tree.heading("Details", text="Details", anchor=tk.W)
    tree.tag_configure('r', background='red')

    # Recursive function to populate the tree
    def populate_tree(parent, key, value):
        if isinstance(value, dict):
            if(value["name"] is not None):
                key = value["name"]
            node = tree.insert(parent, "end", text=key, open=False)
            for sub_key, sub_value in value.items():
                populate_tree(node, sub_key, sub_value)
        elif isinstance(value, list):
            node = tree.insert(parent, "end", text=key, open=False)
            for idx, item in enumerate(value, start=1):
                populate_tree(node, f"{key} #{idx}", item)
        else:
            tree.insert(parent, "end", text=key, values=(value,))

    # Populate the tree with cpp_class data
    for class_name, class_data in cpp_class.items():
        if("error" in class_data.keys()):
            class_node = tree.insert("", "end", text=class_name, values=(class_data["error"],), tags=('r',),
                                     open=False)
        else:
            class_node = tree.insert("", "end", text=class_name,
                                         open=False)
        for key, value in class_data.items():
            populate_tree(class_node, key, value)

    # Run the Tkinter main loop
    root.mainloop()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate C++ widget classes from LVGL headers.")
    parser.add_argument("input_path", help="Path to the base directory containing folders.")
    parser.add_argument("output_path", help="Path to the directory where .hpp files will be generated.")
    args = parser.parse_args()

    input_path = args.input_path
    output_path = args.output_path

    print(f"[INFO] Input directory: {input_path}")
    print(f"[INFO] Output directory: {output_path}")

    d = process_folders(input_path, output_path, True)
    show_tree_view(d)
