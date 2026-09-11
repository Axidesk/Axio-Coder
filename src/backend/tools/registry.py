"""Registro central de ferramentas do agente (padrão Registry / Open-Closed).

Cada tool é registrada com @register(nome, description, parameters) e o loop
de IA lê TOOL_REGISTRY dinamicamente. parameters é um dict puro (desacoplado
do SDK Gemini); build_function_declarations converte para FunctionDeclaration.
"""

TOOL_REGISTRY = {}

def register(name, description, parameters):
    def decorator(fn):
        TOOL_REGISTRY[name] = {
            "handler": fn,
            "description": description,
            "parameters": parameters,
        }
        return fn
    return decorator

def tool_names():
    return list(TOOL_REGISTRY.keys())

def dispatch(name, args):
    entry = TOOL_REGISTRY.get(name)
    if entry is None:
        return "Ferramenta desconhecida."
    return entry["handler"](**args)

def build_function_declarations(types):
    decls = []
    for name, entry in TOOL_REGISTRY.items():
        params = entry["parameters"]
        properties = {}
        for pname, pmeta in params.get("properties", {}).items():
            properties[pname] = types.Schema(
                type=getattr(types.Type, pmeta.get("type", "STRING")),
                description=pmeta.get("description", ""),
            )
        decls.append(
            types.FunctionDeclaration(
                name=name,
                description=entry["description"],
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties=properties,
                    required=params.get("required", []),
                ),
            )
        )
    return decls
