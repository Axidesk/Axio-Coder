import json
import time

from src.backend.ai.context import ErroContextoExcedido, eh_erro_contexto_limite, eh_erro_transitorio
from src.backend.ai.gemini import get_gemini_client
from src.backend.ai.deepseek import get_deepseek_client

def converter_schema_google_para_openai(schema):
    if not schema:
        return {"type": "object", "properties": {}}
    res = {"type": getattr(schema, "type", "string").lower() if isinstance(getattr(schema, "type", ""), str) else "object"}
    if hasattr(schema, 'properties') and schema.properties:
        res["properties"] = {k: converter_schema_google_para_openai(v) for k, v in schema.properties.items()}
    if hasattr(schema, 'required') and schema.required:
        res["required"] = schema.required
    if hasattr(schema, 'enum') and schema.enum:
        res["enum"] = schema.enum
    return res

def chamar_api_com_retry(historico, config, max_tentativas=5, use_deepseek=False):
    for tentativa in range(max_tentativas):
        try:
            if use_deepseek:
                mensagens_ds = []
                if config.system_instruction:
                    sys_text = ""
                    if isinstance(config.system_instruction, str):
                        sys_text = config.system_instruction
                    elif hasattr(config.system_instruction, 'parts'):
                        sys_text = "".join([p.text for p in config.system_instruction.parts if hasattr(p, 'text')])
                    else:
                        sys_text = str(config.system_instruction)
                    mensagens_ds.append({"role": "system", "content": sys_text})

                for i, h in enumerate(historico):
                    role = "assistant" if h.role == "model" else h.role
                    
                    # 1. Se for uma mensagem de resposta de ferramenta (do "user" no contexto Gemini)
                    is_tool_response = any(hasattr(p, 'function_response') and p.function_response for p in h.parts)
                    
                    if is_tool_response:
                        func_resp_index = 0
                        for p in h.parts:
                            if hasattr(p, 'function_response') and p.function_response:
                                mensagens_ds.append({
                                    "role": "tool",
                                    "tool_call_id": f"call_{i-1}_{func_resp_index}", # Refere-se à mensagem anterior
                                    "name": p.function_response.name,
                                    "content": json.dumps(p.function_response.response)
                                })
                                func_resp_index += 1
                        continue # Vai para a próxima mensagem do histórico

                    # 2. Se for uma mensagem normal (User ou Assistant/Model)
                    texto_bruto = ""
                    reasoning_bruto = ""
                    tool_calls = []
                    func_call_index = 0
                    for p in h.parts:
                        if hasattr(p, 'text') and p.text:
                            texto_bruto += p.text
                        if hasattr(p, 'reasoning_content') and p.reasoning_content:
                            reasoning_bruto += p.reasoning_content
                        if hasattr(p, 'function_call') and p.function_call:
                            tool_calls.append({
                                "id": f"call_{i}_{func_call_index}",
                                "type": "function",
                                "function": {
                                    "name": p.function_call.name,
                                    "arguments": json.dumps(p.function_call.args)
                                }
                            })
                            func_call_index += 1

                    # Limpeza de Pensamento (Thinking)
                    # Prioriza o campo reasoning_content preservado pelo MockResponse;
                    # se ausente, extrai das tags <think>...</think> legadas.
                    pensamento = reasoning_bruto.strip()
                    if "<think>" in texto_bruto and "</think>" in texto_bruto:
                        partes = texto_bruto.split("</think>", 1)
                        pensamento_tag = partes[0].replace("<think>", "").strip()
                        if pensamento_tag:
                            pensamento = pensamento_tag
                        conteudo_limpo = partes[1].strip() if len(partes) > 1 else ""
                    else:
                        conteudo_limpo = texto_bruto.strip()

                    # Montagem do dicionário da mensagem
                    msg_dict = {"role": role}
                    
                    # DeepSeek: Se houver tool_calls ou reasoning, content não pode ser None
                    msg_dict["content"] = conteudo_limpo if (conteudo_limpo or not tool_calls) else ""
                    
                    # DeepSeek exige que TODO assistant com tool_calls reenvie o reasoning_content
                    # (mesmo vazio) em toda request subsequente; sem isso retorna erro 400.
                    if role == "assistant" and (pensamento or tool_calls):
                        msg_dict["reasoning_content"] = pensamento
                    
                    if tool_calls:
                        msg_dict["tool_calls"] = tool_calls
                    
                    mensagens_ds.append(msg_dict)

                # Configuração das ferramentas (Tools)
                ds_tools = []
                if config.tools:
                    for tool in config.tools:
                        for f in tool.function_declarations:
                            ds_tools.append({
                                "type": "function",
                                "function": {
                                    "name": f.name,
                                    "description": f.description,
                                    "parameters": converter_schema_google_para_openai(getattr(f, 'parameters', None))
                                }
                            })

                response = get_deepseek_client().chat.completions.create(
                    model="deepseek-flash",
                    messages=mensagens_ds,
                    tools=ds_tools if ds_tools else None
                )
                
                print(f"[API] Modelo real que respondeu: {response.model}")
                
                res_msg = response.choices[0].message
                
                class MockResponse:
                    def __init__(self, msg_obj, idx_ref):
                        self.text = msg_obj.content or ""
                        self.reasoning_content = getattr(msg_obj, 'reasoning_content', None)
                        self.function_calls = []
                        parts = []
                        
                        if self.reasoning_content:
                            parts.append(type('obj', (object,), {
                                'text': f"<think>\n{self.reasoning_content}\n</think>\n",
                                'reasoning_content': self.reasoning_content
                            }))
                        
                        parts.append(type('obj', (object,), {'text': self.text}))

                        if msg_obj.tool_calls:
                            for j, tc in enumerate(msg_obj.tool_calls):
                                try:
                                    args = json.loads(tc.function.arguments)
                                except json.JSONDecodeError:
                                    args = {"error": "JSON inválido", "raw": tc.function.arguments}
                                self.function_calls.append(type('obj', (object,), {'name': tc.function.name, 'args': args}))
                                parts.append(type('obj', (object,), {
                                    'text': None,
                                    'function_call': type('obj', (object,), {'name': tc.function.name, 'args': args})
                                }))

                        self.candidates = [type('obj', (object,), {
                            'content': type('obj', (object,), {'role': 'model', 'parts': parts})
                        })]
                        self.usage_metadata = None

                return MockResponse(res_msg, len(historico))

            else:
                from google.genai import types

                if config is None:
                    config = types.GenerateContentConfig()
                
                # Timeout definitivo: 300000ms (5 minutos) via HttpOptions
                config.http_options = types.HttpOptions(timeout=300000)

                return get_gemini_client().models.generate_content(
                    model='gemini-3.1-pro-preview-customtools',
                    contents=historico,
                    config=config
                )
                
        except Exception as e:
            ultimo_erro = e
            msg = str(e)
            
            if eh_erro_contexto_limite(msg):
                raise ErroContextoExcedido(msg) from e
                
            if eh_erro_transitorio(msg):
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    tempo_espera = 30 * (tentativa + 1)
                    log_msg = f"[API] Cota limite excedida (429). Tentativa {tentativa + 1}/{max_tentativas}. Aguardando {tempo_espera}s..."
                else:
                    tempo_espera = 2 ** (tentativa + 1)
                    log_msg = f"[API] Erro de Serviço Interno. ({type(e).__name__}). Tentativa {tentativa + 1}/{max_tentativas}. Aguardando {tempo_espera}s..."

                print(log_msg)
                time.sleep(tempo_espera)
                continue
                
            raise e

    if "429" in str(ultimo_erro) or "RESOURCE_EXHAUSTED" in str(ultimo_erro):
        raise RuntimeError("Atingiu o limite de cota RPD/RPM. Tente mais tarde.") from ultimo_erro

    raise RuntimeError(f"Falha ao conectar com o Gemini após {max_tentativas} tentativas. Erro: {ultimo_erro}") from ultimo_erro
