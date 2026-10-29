"""Obsidian 속성용 제한 데이터 YAML. 객체 생성·태그·참조를 실행하지 않는다."""
import json
import math
import re


class DataError(ValueError):
    def __init__(self, code, line=None, key=None):
        self.code, self.line, self.key = code, line, key
        super().__init__(code)


def _comment(text):
    quote = None
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if quote == '"':
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif quote == "'":
            if char == "'":
                if index + 1 < len(text) and text[index + 1] == "'":
                    index += 1
                else:
                    quote = None
        elif char in "\"'" and (index == 0 or text[index - 1] in " [{,:-"):
            quote = char
        elif char == "#" and (index == 0 or text[index - 1].isspace()):
            return text[:index].rstrip()
        index += 1
    return text.rstrip()


def _split(text, delimiter, *, mapping=False):
    quote, depth, start, escaped = None, 0, 0, False
    parts = []
    index = 0
    while index < len(text):
        char = text[index]
        if quote == '"':
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif quote == "'":
            if char == quote:
                if index + 1 < len(text) and text[index + 1] == quote:
                    index += 1
                else:
                    quote = None
        elif char in "\"'" and (index == start or text[index - 1] in " [{,:"):
            quote = char
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
        elif char == delimiter and depth == 0:
            if mapping and index + 1 < len(text) and not text[index + 1].isspace():
                index += 1
                continue
            parts.append(text[start:index])
            start = index + 1
            if delimiter == ":":
                parts.append(text[start:])
                return parts
        index += 1
    if quote or depth:
        raise DataError("yaml_syntax")
    parts.append(text[start:])
    return parts


def scalar(text, line=None, key=None, depth=0):
    text = text.strip()
    if depth > 12:
        raise DataError("yaml_depth", line, key)
    if not text:
        return None
    if text[0] in "&*!|>%@`" or text.startswith(("? ", "- ")):
        raise DataError("yaml_feature_unsupported", line, key)
    if text.startswith('"'):
        try:
            value = json.loads(text)
        except ValueError:
            raise DataError("yaml_string", line, key) from None
        if not isinstance(value, str):
            raise DataError("yaml_string", line, key)
        return value
    if text.startswith("'"):
        if not text.endswith("'") or "'" in text[1:-1].replace("''", ""):
            raise DataError("yaml_string", line, key)
        return text[1:-1].replace("''", "'")
    if text.startswith(("[", "{")):
        closing = "]" if text[0] == "[" else "}"
        if not text.endswith(closing):
            raise DataError("yaml_flow", line, key)
        inner = text[1:-1].strip()
        if not inner:
            return [] if closing == "]" else {}
        parts = _split(inner, ",")
        if not parts[-1].strip():
            parts.pop()
        if any(not item.strip() for item in parts):
            raise DataError("yaml_flow", line, key)
        if closing == "]":
            return [scalar(item, line, key, depth + 1) for item in parts]
        result = {}
        for item in parts:
            pair = _split(item, ":")
            if len(pair) != 2:
                raise DataError("yaml_mapping", line, key)
            name = _key(pair[0], line)
            if name in result:
                raise DataError("frontmatter_duplicate", line, name)
            result[name] = scalar(pair[1], line, name, depth + 1)
        return result
    lowered = text.lower()
    if lowered in ("null", "~"):
        return None
    if lowered in ("true", "false"):
        return lowered == "true"
    if lowered in (".nan", ".inf", "+.inf", "-.inf"):
        raise DataError("yaml_nonfinite", line, key)
    if re.fullmatch(r"[-+]?[0-9]+", text):
        return int(text)
    if re.fullmatch(r"[-+]?(?:(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?|[0-9]+[eE][-+]?[0-9]+)", text):
        value = float(text)
        if not math.isfinite(value):
            raise DataError("yaml_nonfinite", line, key)
        return value
    if re.match(r"[-+]?0[xob][0-9A-Fa-f]|[-+]?[0-9][0-9_]*_", text):
        raise DataError("yaml_number_unsupported", line, key)
    # 날짜는 문자열로 보존한다. YAML 1.1의 yes/no/on/off 암시적 변환은 하지 않는다.
    if re.search(r":\s|\s#", text) or text.startswith(("{", "[")):
        raise DataError("yaml_plain_string", line, key)
    return text


def _key(text, line):
    text = text.strip()
    if not text or text == "<<" or text.startswith(("?", "&", "*", "!", "[", "{")):
        raise DataError("yaml_key", line)
    if text[0] in "\"'":
        text = scalar(text, line)
    if not isinstance(text, str) or not text or any(c in text for c in "\x00\r\n"):
        raise DataError("yaml_key", line)
    return text


def load(header):
    if not isinstance(header, bytes) or len(header) > 1024 * 1024:
        raise DataError("yaml_size")
    try:
        text = header.decode("utf-8")
    except UnicodeError:
        raise DataError("frontmatter_encoding") from None
    if text.strip().startswith("{"):
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise DataError("frontmatter_duplicate", key=key)
                result[key] = value
            return result
        try:
            result = json.loads(text, object_pairs_hook=pairs,
                                parse_constant=lambda value: (_ for _ in ()).throw(DataError("yaml_nonfinite")))
        except DataError:
            raise
        except (ValueError, RecursionError):
            raise DataError("yaml_json") from None
        return result
    lines = []
    for number, raw in enumerate(text.split("\n"), 1):
        raw = raw.removesuffix("\r")
        indent = len(raw) - len(raw.lstrip(" "))
        if "\t" in raw[:indent + 1]:
            raise DataError("yaml_indent", number)
        value = _comment(raw[indent:])
        if value:
            lines.append((indent, value, number))
    if len(lines) > 10000:
        raise DataError("yaml_size")
    position = 0

    def entry(result, value, number, indent, depth):
        nonlocal position
        pair = _split(value, ":", mapping=True)
        if len(pair) != 2:
            raise DataError("yaml_mapping", number)
        name = _key(pair[0], number)
        if name in result:
            raise DataError("frontmatter_duplicate", number, name)
        rest = pair[1].strip()
        if rest:
            result[name] = scalar(rest, number, name, depth)
        elif position < len(lines) and (lines[position][0] > indent
                or (lines[position][0] == indent and lines[position][1].startswith("- "))):
            result[name] = block(lines[position][0], depth + 1)
        else:
            result[name] = None

    def block(indent, depth):
        nonlocal position
        if depth > 12:
            raise DataError("yaml_depth", lines[position][2])
        is_list = lines[position][1] == "-" or lines[position][1].startswith("- ")
        result = [] if is_list else {}
        while position < len(lines) and lines[position][0] == indent:
            _, value, number = lines[position]
            current_list = value == "-" or value.startswith("- ")
            if current_list != is_list:
                break
            position += 1
            if not is_list:
                entry(result, value, number, indent, depth)
                continue
            rest = value[1:].strip()
            if not rest:
                result.append(block(lines[position][0], depth + 1)
                              if position < len(lines) and lines[position][0] > indent else None)
            elif len(_split(rest, ":", mapping=True)) == 2:
                item = {}
                entry(item, rest, number, indent + 2, depth + 1)
                while position < len(lines) and lines[position][0] > indent:
                    child_indent, child, child_number = lines[position]
                    if child_indent != indent + 2 or child.startswith("- "):
                        raise DataError("yaml_indent", child_number)
                    position += 1
                    entry(item, child, child_number, child_indent, depth + 1)
                result.append(item)
            else:
                result.append(scalar(rest, number, depth=depth + 1))
        return result

    if not lines:
        return {}
    if lines[0][0] != 0:
        raise DataError("yaml_indent", lines[0][2])
    result = block(0, 0)
    if position != len(lines) or not isinstance(result, dict):
        raise DataError("yaml_structure", lines[min(position, len(lines) - 1)][2])
    return result
