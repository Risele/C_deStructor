#!/usr/bin/env python3
"""
Модуль для генерации C++-хедера для одной структуры.
Если переданная инициализация представляет массив структур,
будет возвращена пустая строка.
Если структура не соответствует ожидаемому описанию, возвращается пустая строка.
"""

import re
import logging
from typing import List, Tuple, Dict, Optional, Union

logging.basicConfig(filename="log.log", level=logging.DEBUG, filemode='w')

# Представление поля: (имя_поля, тип_поля, размер_массива или None)
Field = Tuple[str, str, Optional[List[int]]]

class Token:
    def __init__(self, type: str, value: str):
        self.type = type
        self.value = value
    def __repr__(self):
        return f"Token({self.type}, {self.value})"

class C_deStructor:
    def __init__(self, header_file: str, view_file: str,
                 init_text: str,
                 target_struct: str, target_view: str,
                 mapping_file: Optional[str] = None, specifier: str = ""):
        self.header_file = header_file
        self.view_file = view_file
        self.init_text = init_text
        self.target_struct = target_struct
        self.target_view = target_view
        self.mapping_file = mapping_file
        self.specifier = specifier

        # Переменные, которые будут заполнены методами загрузки
        self.structs: Dict[str, List[Field]] = {}
        self.view_defs: Dict[str, List[Field]] = {}
        self.view_tree: Union[str, Dict] = {}
        self.explicit_mapping: Dict[str, str] = {}
        self.flat_fields: List[str] = []
        
        self.postfix=""

    # --- Токенизация ---
    def tokenize(self, text: str) -> List[Token]:
        token_specification = [
            ('STRING',   r'"(?:\\.|[^"\\])*"'),
            ('NUMBER',   r'\d+(\.\d*)?'),
            ('ID',       r'[A-Za-z_]\w*'),
            ('LBRACE',   r'\{'),
            ('RBRACE',   r'\}'),
            ('LBRACKET', r'\['),
            ('RBRACKET', r'\]'),
            ('SEMICOLON',r';'),
            ('COMMA',    r','),
            ('LPAREN',   r'\('),
            ('RPAREN',   r'\)'),
            ('ASSIGN',   r'='),
            ('DOT',      r'\.'),
            ('OTHER',    r'.'),
        ]
        tok_regex = '|'.join(f"(?P<{pair[0]}>{pair[1]})" for pair in token_specification)
        tokens = []
        for mo in re.finditer(tok_regex, text):
            kind = mo.lastgroup
            value = mo.group()
            if kind == 'OTHER' and value.isspace():
                continue
            if kind == 'OTHER' and value not in ('_',):
                continue
            tokens.append(Token(kind, value))
        return tokens

    # --- Парсинг полного описания структур ---
    def parse_typedef_structs(self, tokens: List[Token]) -> Dict[str, List[Field]]:
        structs = {}
        pos = 0
        while pos < len(tokens):
            if tokens[pos].type == 'ID' and tokens[pos].value == 'typedef':
                pos += 1
                if pos < len(tokens) and tokens[pos].type == 'ID' and tokens[pos].value == 'struct':
                    pos += 1
                    if pos < len(tokens) and tokens[pos].type == 'LBRACE':
                        pos += 1
                        fields = []
                        while pos < len(tokens) and tokens[pos].type != 'RBRACE':
                            field_tokens = []
                            while pos < len(tokens) and tokens[pos].type != 'SEMICOLON':
                                field_tokens.append(tokens[pos])
                                pos += 1
                            if pos < len(tokens) and tokens[pos].type == 'SEMICOLON':
                                pos += 1
                            if not field_tokens:
                                continue
                            array_dims = []
                            while len(field_tokens) >= 3 and \
                                  field_tokens[-3].type == 'LBRACKET' and \
                                  field_tokens[-2].type == 'NUMBER' and \
                                  field_tokens[-1].type == 'RBRACKET':
                                dim = int(float(field_tokens[-2].value))
                                array_dims.insert(0, dim)
                                field_tokens = field_tokens[:-3]
                            field_name = field_tokens[-1].value
                            field_type = " ".join(token.value for token in field_tokens[:-1]).strip()
                            fields.append((field_name, field_type, array_dims if array_dims else None))
                        if pos < len(tokens) and tokens[pos].type == 'RBRACE':
                            pos += 1
                        if pos < len(tokens) and tokens[pos].type == 'ID':
                            struct_name = tokens[pos].value
                            pos += 1
                            if pos < len(tokens) and tokens[pos].type == 'SEMICOLON':
                                pos += 1
                            structs[struct_name] = fields
                        else:
                            raise ValueError("Ожидалось имя структуры после '}'")
                    else:
                        pos += 1
                else:
                    pos += 1
            else:
                pos += 1
        return structs

    # --- Рекурсивное flattening структуры ---
    def normalize_path(self, path: str) -> str:
        return re.sub(r'\[\d+\]', '', path)

    def flatten_struct_fields(self, structs: Dict[str, List[Field]],
                              struct_name: str,
                              source_prefix: str = "",
                              output_prefix: str = "",
                              explicit_mapping: Optional[Dict[str, str]] = None) -> List[str]:
        result = []
        if struct_name not in structs:
            return result
        for field_name, field_type, array_dims in structs[struct_name]:
            full_source_path = field_name if not source_prefix else f"{source_prefix}.{field_name}"
            norm_path = self.normalize_path(full_source_path)
            if explicit_mapping and norm_path in explicit_mapping:
                current_output = explicit_mapping[norm_path]
            elif explicit_mapping and field_name in explicit_mapping:
                current_output = explicit_mapping[field_name]
            else:
                current_output = field_name
            if explicit_mapping and (norm_path in explicit_mapping or field_name in explicit_mapping):
                new_output_prefix = current_output
            else:
                new_output_prefix = current_output if not output_prefix else f"{output_prefix}_{current_output}"
            if field_type in structs:
                if array_dims is None:
                    nested = self.flatten_struct_fields(structs, field_type, full_source_path, new_output_prefix, explicit_mapping)
                    result.extend(nested)
                else:
                    if len(array_dims) == 1:
                        count = array_dims[0]
                        for i in range(count):
                            nested_source = f"{full_source_path}[{i}]"
                            nested_output_prefix = f"{new_output_prefix}_{i}"
                            nested = self.flatten_struct_fields(structs, field_type, nested_source, nested_output_prefix, explicit_mapping)
                            result.extend(nested)
                    else:
                        def gen_indices(dims, cur=''):
                            if not dims:
                                yield cur.lstrip('_')
                            else:
                                for j in range(dims[0]):
                                    yield from gen_indices(dims[1:], f"{cur}_{j}")
                        for idx in gen_indices(array_dims):
                            nested_source = f"{full_source_path}[{idx}]"
                            nested_output_prefix = f"{new_output_prefix}_{idx}"
                            nested = self.flatten_struct_fields(structs, field_type, nested_source, nested_output_prefix, explicit_mapping)
                            result.extend(nested)
            else:
                if array_dims:
                    if len(array_dims) == 1:
                        count = array_dims[0]
                        for i in range(count):
                            result.append(f"{new_output_prefix}_{i}")
                    else:
                        def gen_indices(dims, cur=''):
                            if not dims:
                                yield cur.lstrip('_')
                            else:
                                for j in range(dims[0]):
                                    yield from gen_indices(dims[1:], f"{cur}_{j}")
                        for idx in gen_indices(array_dims):
                            result.append(f"{new_output_prefix}_{idx}")
                else:
                    result.append(new_output_prefix)
        return result

    # --- Загрузка полного описания ---
    def load_full_structs(self):
        with open(self.header_file, 'r', encoding='utf-8') as f:
            header_text = f.read()
        tokens = self.tokenize(header_text)
        self.structs = self.parse_typedef_structs(tokens)
        logging.debug("Найденные структуры: %s", self.structs)

    # --- Парсинг view‑структур ---
    def parse_view_structs(self, view_header: str) -> Dict[str, List[Tuple[str, str, Optional[List[int]]]]]:
        with open(view_header, 'r', encoding='utf-8') as f:
            content = f.read()
        pattern = r'typedef\s+struct\s*{([^}]*)}\s*(\w+)\s*;'
        matches = re.findall(pattern, content, re.DOTALL)
        view_structs = {}
        for body, struct_name in matches:
            fields = []
            for line in body.splitlines():
                line = line.strip()
                if not line or line.startswith('//'):
                    continue
                m = re.match(r'(\w+)\s+(\w+)(\s*\[\s*(\d+)\s*\])?;', line)
                if m:
                    field_type = m.group(1)
                    name = m.group(2)
                    if m.group(3):
                        array_dims = [int(m.group(4))]
                    else:
                        array_dims = None
                    fields.append((name, field_type, array_dims))
            view_structs[struct_name] = fields
        return view_structs

    def build_view_tree(self, view_defs: Dict[str, List[Tuple[str, str, Optional[List[int]]]]],
                        struct_name: str) -> Union[str, Dict]:
        if struct_name not in view_defs:
            return struct_name
        tree = {}
        for field_name, field_type, array_dims in view_defs[struct_name]:
            if field_type in view_defs:
                subtree = self.build_view_tree(view_defs, field_type)
            else:
                subtree = field_type
            if array_dims is not None:
                size = array_dims[0] if len(array_dims) >= 1 else 1
                tree[field_name] = {"array": size, "fields": subtree}
            else:
                tree[field_name] = subtree
        return tree

    def load_view_structs(self):
        self.view_defs = self.parse_view_structs(self.view_file)
        self.view_tree = self.build_view_tree(self.view_defs, self.target_view)
        logging.debug("Вложенное представление view‑структуры '%s': %s", self.target_view, self.view_tree)

    # --- Загрузка маппинга ---
    def load_mapping(self):
        if self.mapping_file:
            with open(self.mapping_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            self.explicit_mapping = {}
            for line in lines:
                line = line.strip()
                if line and not line.startswith('#') and ':' in line:
                    key, value = line.split(':', 1)
                    self.explicit_mapping[key.strip()] = value.strip()
        logging.debug("Явный маппинг: %s", self.explicit_mapping)

    # --- Парсинг инициализации ---
    def parse_initialization(self, init_text: str) -> Union[List, str]:
        text = re.sub(r'//.*?\n|/\*.*?\*/', '', init_text, flags=re.S)
        tokens = self.tokenize(text)
        pos = 0
        def parse_block() -> Union[List, str]:
            nonlocal pos
            result = []
            if pos < len(tokens) and tokens[pos].type == 'LBRACE':
                pos += 1
                while pos < len(tokens) and tokens[pos].type != 'RBRACE':
                    if tokens[pos].type == 'LBRACE':
                        result.append(parse_block())
                    elif tokens[pos].type in ('NUMBER', 'ID', 'DOT', 'STRING'):
                        result.append(tokens[pos].value)
                        pos += 1
                    elif tokens[pos].type == 'COMMA':
                        pos += 1
                    else:
                        pos += 1
                if pos < len(tokens) and tokens[pos].type == 'RBRACE':
                    pos += 1
                return result
            else:
                value = tokens[pos].value
                pos += 1
                return value
        parsed = parse_block()
        return parsed

    def flatten_initialization(self, init_structure: Union[List, str]) -> List[str]:
        if isinstance(init_structure, list):
            flat = []
            for item in init_structure:
                flat.extend(self.flatten_initialization(item))
            return flat
        else:
            return [init_structure]

    # --- Генерация сопоставления полей ---
    def generate_field_map(self, field_names: List[str], init_values: List[str]) -> Dict[str, Union[str, List[str]]]:
        result = {}
        temp_array = {}
        index = 0
        for field in field_names:
            if index >= len(init_values):
                break
            m = re.match(r'(.+?)_(\d+)$', field)
            if m:
                base = m.group(1)
                if base not in temp_array:
                    temp_array[base] = []
                temp_array[base].append(init_values[index])
            else:
                result[field] = init_values[index]
            index += 1
        for base, values in temp_array.items():
            result[base] = values
        return result

    # --- Генерация вложённого инициализатора ---
    def generate_nested_initializer(self, view_tree: Union[Dict, str], field_map: Dict[str, Union[str, List[str]]], prefix: str = "") -> str:
        if isinstance(view_tree, str):
            return field_map.get(prefix, "0")
        elif isinstance(view_tree, dict):
            parts = []
            for key, sub in view_tree.items():
                full_key = key if not prefix else f"{prefix}_{key}"
                if isinstance(sub, dict) and "array" in sub and "fields" in sub:
                    size = sub["array"]
                    elems = []
                    for i in range(size):
                        elem_key = f"{full_key}_{i}"
                        if elem_key in field_map:
                            elems.append(field_map[elem_key])
                        else:
                            elems.append(self.generate_nested_initializer(sub["fields"], field_map, elem_key))
                    parts.append("{" + ", ".join(elems) + "}")
                else:
                    if full_key in field_map:
                        parts.append(field_map[full_key])
                    else:
                        parts.append(self.generate_nested_initializer(sub, field_map, full_key))
            return "{" + ", ".join(parts) + "}"
        else:
            return "0"

    # --- Проверка структуры ---
    def check_structure_type(self, flat_values: List[str]) -> bool:
        expected = len(self.flatten_struct_fields(self.structs, self.target_struct, "", "", self.explicit_mapping))
        if len(flat_values) < expected:
            logging.warning("Обнаружено меньше полей (%d), чем ожидается (%d)", len(flat_values), expected)
            return False
        return True

    # --- Обработка одного блока инициализации ---
    def process_structure(self, init_block: str) -> str:
        parsed = self.parse_initialization(init_block)

        # Обработка массива структур
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], list):
            result_items = []
            for item in parsed:
                flat_values = self.flatten_initialization(item)
                if not self.check_structure_type(flat_values):
                    logging.warning("Элемент массива не соответствует структуре.")
                    continue
                self.flat_fields = self.flatten_struct_fields(self.structs, self.target_struct, "", "", self.explicit_mapping)
                field_map = self.generate_field_map(self.flat_fields, flat_values)
                result_items.append(self.generate_nested_initializer(self.view_tree, field_map))
            return "{\n" + ",\n".join(result_items) + "\n}"
        else:
            flat_values = self.flatten_initialization(parsed)
            if not self.check_structure_type(flat_values):
                return ""
            self.flat_fields = self.flatten_struct_fields(self.structs, self.target_struct, "", "", self.explicit_mapping)
            field_map = self.generate_field_map(self.flat_fields, flat_values)
            return self.generate_nested_initializer(self.view_tree, field_map)
            # --- Получение размера массива из файла инициализации ---
    def extract_declaration_info(self) -> Tuple[str, Optional[str], str, str]:
        """
        Извлекает из self.init_text объявление инициализации для структуры с именем target_struct.
        Ожидается, что объявление имеет вид (с произвольными спецификаторами опционально):
        
          [<specifiers>] <target_struct> <varName>[<размер>] = { ... };
          
        Метод возвращает кортеж:
          (спецификаторы, имя переменной, размер массива (например, "2" или "[]" если скобки присутствуют без числа, либо None), блок инициализации)
        Если объявление не найдено, возвращается кортеж с пустыми значениями.
        """
        pattern = r'^(?P<spec>(?:\w+\s+)*)' + re.escape(self.target_struct) + r'\s+(?P<var>\w+)\s*(\[\s*(?P<size>\d*)\s*\])?\s*=\s*(?P<init>\{.*?\})\s*;'
        m = re.search(pattern, self.init_text, flags=re.S | re.M)
        if m:
            spec = m.group("spec").strip()
            var_name = m.group("var")
            size = m.group("size")
            if m.group(3):  # присутствуют квадратные скобки
                array_size = "[]" if size == "" else size
            else:
                array_size = None
            init_block = m.group("init")
            ##return (spec, var_name, array_size, init_block)
            
            self.prefix = (spec +" ") if spec else ""
            self.var_nameSrc = var_name
            self.array_size=array_size
            self.init_block=init_block
        ##return ("", None, None, "")



    def generate_declaration(self, init_str: str, var_name: str = "view_array",) -> str:
        """
        Оборачивает обработанный блок инициализации в полное объявление.
        
        Параметры:
          init_str: Строка с блоком инициализации (например, "{ ... }").
          var_name: Имя переменной, по умолчанию "view_array".
          array_size: Размер массива, если указан (например, "2" или "[]" для пустых скобок); если None – одиночная структура.
          prefix_specifier: Префиксный спецификатор, который вставляется перед типом структуры  (например,"const", "static").
          specifier: Дополнительный спецификатор, который добавляется после объявления (например, "PROGMEM").
        
        Возвращает полное объявление, например:
          static const unit view_array[2] PROGMEM = { ... };
        """
        
        if self.array_size is not None:
            if self.array_size == "[]":
                return f"{self.prefix} {self.target_struct} {var_name}[]{self.postfix} = {init_str};"
            else:
                return f"{self.prefix} {self.target_struct} {var_name}[{self.array_size}]{self.postfix} = {init_str};"
        else:
            return f"{self.prefix} {self.target_struct} {var_name}{self.postfix} = {init_str};"
    def setPostfix(self,postfix):
        self.postfix = (postfix+" ") if postfix else ""
        
    def run(self,newVarName="") -> str:
        self.load_full_structs()
        self.load_view_structs()
        self.load_mapping()
        self.extract_declaration_info()
        if not self.init_block:
            logging.warning("Не найден блок инициализации для структуры %s", self.target_struct)
            return ""
        init_str = self.process_structure(self.init_block)
        
        var_name = newVarName if newVarName else self.var_nameSrc
        
        return self.generate_declaration(init_str, var_name=var_name)



# Пример использования:
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Обработка одного объявления инициализации структуры")
    parser.add_argument('--header', required=True, help="Путь к файлу с объявлением полных структур")
    parser.add_argument('--view-file', required=True, help="Путь к файлу с описанием view-структур")
    parser.add_argument('--struct', required=True, help="Имя основной структуры (например, unit)")
    parser.add_argument('--target-view', required=True, help="Имя view-структуры, которая должна быть использована")
    parser.add_argument('--mapping-file', required=False, help="Путь к файлу с маппингом вложенных полей")
    parser.add_argument('--init-block', required=False, help="Строка с инициализацией (блоком) одной структуры")
    parser.add_argument('--specifier', required=False, default="", help="Опциональный спецификатор (например, PROGMEM)")
    parser.add_argument('--init-file', required=True, help="Путь к файлу с инициализацией (блоком) одной структуры")
    args = parser.parse_args()

    
    with open(args.init_file, "r", encoding="utf-8") as f:
        init_text = f.read()
    processor = C_deStructor(args.header, args.view_file,init_text, args.struct, args.target_view, args.mapping_file, args.specifier)
    
    result = processor.run()
    print("Полное объявление:")
    print(result)
