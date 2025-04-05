import re
import os
import argparse
from C_deStructor import C_deStructor  # Импортируйте ваш класс

def extract_init_declarations_from_text(init_text: str, target_struct: str) -> list:
    """
    Извлекает из входного текста все объявления инициализации для структуры target_struct.
    Ожидается, что объявления имеют вид (спецификаторы могут быть произвольными):
      [<specifiers>] <target_struct> <varName>[<size>] = { ... };
    Возвращает список кортежей: (var_name, array_size, init_block)
    """
    pattern = r'^(?P<spec>(?:\w+\s+)*)' + re.escape(target_struct) + r'\s+(?P<var>\w+)\s*(\[\s*(?P<size>\d*)\s*\])?\s*=\s*(?P<init>\{.*?\})\s*;'
    declarations = []
    for m in re.finditer(pattern, init_text, flags=re.S | re.M):
        var_name = m.group("var")
        size = m.group("size")
        if m.group(3):  # если квадратные скобки присутствуют
            array_size = "[]" if size == "" else size
        else:
            array_size = None
        init_block = m.group("init")
        spec = m.group("spec").strip()
        # Полное объявление можно сформировать позже, здесь сохраняем базовую информацию
        declarations.append((spec, var_name, array_size, init_block))
    return declarations

def update_output_file(new_decls: dict, output_file: str) -> None:
    """
    Обновляет выходной файл, заменяя существующие объявления с такими же именами переменных
    на новые (из словаря new_decls), а если объявления нет – добавляет его.
    
    new_decls: словарь, где ключ – имя переменной, значение – полный текст объявления.
    """
    if os.path.exists(output_file):
        with open(output_file, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        content = ""
    for var, decl in new_decls.items():
        # Ищем существующее объявление с именем var.
        # Шаблон: слово "const", затем любое слово (тип), затем имя переменной, затем опциональный размер, затем "=" и блок до ";"
        pattern = r'(const\s+\S+\s+' + re.escape(var) + r'\s*(?:\[[^\]]*\])?\s*=\s*\{.*?\}\s*;)'
        if re.search(pattern, content, flags=re.DOTALL):
            content = re.sub(pattern, decl, content, flags=re.DOTALL)
        else:
            # Если объявления нет, просто добавляем его в конец файла
            content += "\n" + decl + "\n"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)

def main():
    parser = argparse.ArgumentParser(description="Обработка нескольких объявлений инициализации структур с обновлением выходного файла")
    parser.add_argument('--header', required=True, help="Путь к файлу с объявлением полных структур")
    parser.add_argument('--view-file', required=True, help="Путь к файлу с описанием view-структур")
    parser.add_argument('--init-file', required=True, help="Путь к файлу с инициализацией структур")
    parser.add_argument('--struct', required=True, help="Имя основной структуры (например, unit)")
    parser.add_argument('--target-view', required=True, help="Имя view-структуры, которая должна быть использована")
    parser.add_argument('--mapping-file', required=False, help="Путь к файлу с маппингом вложенных полей")
    parser.add_argument('--specifier', required=False, default="", help="Опциональный спецификатор (например, PROGMEM)")
    parser.add_argument('--output', required=True, help="Путь к итоговому .h-файлу")
    args = parser.parse_args()

    # Читаем весь текст инициализации из init-файла
    with open(args.init_file, "r", encoding="utf-8") as f:
        init_text = f.read()

    # Извлекаем все объявления для заданной структуры
    decls = extract_init_declarations_from_text(init_text, args.struct)
    if not decls:
        print("Не найдено объявлений инициализации для структуры", args.struct)
        return

    new_declarations = {}
    # Для каждого объявления создаем экземпляр класса и обрабатываем его
    for spec, var_name, array_size, init_block in decls:
        processor = C_deStructor(args.header, args.view_file, init_text, args.struct, args.target_view, args.mapping_file, args.specifier)
        # Передаем конкретный блок инициализации в метод run()
        processed_block = processor.process_structure(init_block)
        if not processed_block:
            logging.warning("Объявление %s не соответствует ожидаемой структуре.", var_name)
            continue
        # Формируем полное объявление, сохраняя исходные спецификаторы, имя переменной и размер массива
        # Формирование объявления:
        # Если array_size задан, то используем его, иначе одиночная структура
        if array_size is not None:
            if array_size == "[]":
                full_decl = f"{spec} const {args.struct} {var_name}[]{' ' + args.specifier if args.specifier else ''} = {processed_block};"
            else:
                full_decl = f"{spec} const {args.struct} {var_name}[{array_size}]{' ' + args.specifier if args.specifier else ''} = {processed_block};"
        else:
            full_decl = f"{spec} const {args.struct} {var_name}{' ' + args.specifier if args.specifier else ''} = {processed_block};"
        new_declarations[var_name] = full_decl.strip()

    # Обновляем или создаем выходной файл с новыми объявлениями
    update_output_file(new_declarations, args.output)
    print("Выходной файл обновлен.")

if __name__ == "__main__":
    main()
