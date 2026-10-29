"""명시된 파일 표 안에서만 링크를 계산한다. 파일 탐색이나 읽기를 하지 않는다."""
import posixpath
import re
from urllib.parse import quote, unquote


def canonical(path):
    if not isinstance(path, str) or path.startswith("/") or "\\" in path or "\x00" in path:
        raise ValueError("link_path")
    if any(part in ("", ".", "..") for part in path.split("/")):
        raise ValueError("link_path")
    return path


def _escaped(text, position):
    backslashes = 0
    position -= 1
    while position >= 0 and text[position] == "\\":
        backslashes += 1
        position -= 1
    return bool(backslashes % 2)


def markdown_content(text, *, inline_code=True, uncertain_ranges=None, html_ranges=None):
    """명확한 코드/HTML block은 가리고 모호한 HTML 구간은 별도 보존한다."""
    masked = list(text)
    fence = None
    offset = 0
    covered_until = 0
    paragraph_open = False
    container_open = False

    def hide(start, end):
        masked[start:end] = [char if char in "\r\n" else " " for char in text[start:end]]

    def end_of_line(position):
        newline = text.find("\n", position)
        return len(text) if newline < 0 else newline + 1

    for line in text.splitlines(keepends=True):
        plain = line.rstrip("\r\n")
        line_end = offset + len(line)
        if fence is not None:
            hide(offset, line_end)
            if re.fullmatch(r" {0,3}" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*", plain):
                fence = None
            paragraph_open = False
            offset = line_end
            continue
        if covered_until >= line_end:
            offset = line_end
            continue
        start_index = max(0, covered_until - offset)
        indented = bool(re.match(r"^[ \t]", plain))
        if start_index == 0:
            marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", plain)
            if (marker and not (container_open and indented)
                    and not (marker.group(1)[0] == "`" and "`" in marker.group(2))):
                fence = marker.group(1)
                hide(offset, line_end)
                paragraph_open = False
                offset = line_end
                continue
            if re.match(r"^(?: {4}|\t)", line):
                if not paragraph_open and not container_open:
                    hide(offset, line_end)
                    offset = line_end
                    continue
                if uncertain_ranges is not None:
                    uncertain_ranges.append((offset, line_end))
            elif plain.strip() and ((container_open and indented) or re.match(r"^ {0,3}>", plain)):
                if uncertain_ranges is not None:
                    uncertain_ranges.append((offset, line_end))
        index = start_index
        line_literal = False
        while index < len(line):
            absolute = offset + index
            if line[index] == "`" and not _escaped(text, absolute):
                run = re.match(r"`+", text[absolute:]).group()
                after = absolute + len(run)
                close = re.search(r"(?<!`)" + re.escape(run) + r"(?!`)", text[after:])
                if close:
                    stop = after + close.end()
                    between = text[after:after + close.start()]
                    # 다른 block을 가로지르는 인용은 inline code로 단정하지 않는다.
                    if not re.search(r"\n[ \t\r]*\n|\n {0,3}(?:#{1,6}[ \t]|`{3,}|~{3,})", between):
                        if inline_code:
                            hide(absolute, stop)
                        covered_until = max(covered_until, stop)
                        index = stop - offset
                        paragraph_open = True
                        continue
                index += len(run)
                continue
            if line[index] == "<" and not _escaped(text, absolute):
                remaining = text[absolute:]
                prefix = line[:index]
                link_angle = re.search(r"\]\([ \t]*$", prefix)
                definition_angle = re.fullmatch(r" {0,3}\[[^]\r\n]+\]:[ \t]*", prefix)
                if ((link_angle and not _escaped(line, link_angle.start())) or definition_angle):
                    index += 1
                    continue
                block_start = index <= 3 and not line[:index].strip() and not (container_open and indented)
                raw_tag = re.match(r"<(script|pre|style|textarea)(?=[ \t>\r\n]|$)", remaining, re.I)
                token = None
                if raw_tag:
                    closing = re.search(r"</" + raw_tag.group(1) + r"[ \t]*>", text[absolute + raw_tag.end():], re.I)
                    stop = len(text) if not closing else absolute + raw_tag.end() + closing.end()
                    token = (stop, "html_raw")
                else:
                    for opening, closing in (("<!--", "-->"), ("<![CDATA[", "]]>"), ("<?", "?>")):
                        if remaining.startswith(opening):
                            close = text.find(closing, absolute + len(opening))
                            token = (len(text) if close < 0 else close + len(closing), "html_literal")
                            break
                    if token is None and re.match(r"<![A-Z]", remaining):
                        close = text.find(">", absolute + 2)
                        token = (len(text) if close < 0 else close + 1, "html_declaration")
                if token is not None:
                    stop, _ = token
                    if block_start:
                        stop = end_of_line(stop)
                    elif html_ranges is not None:
                        html_ranges.append((absolute, stop))
                    hide(absolute, stop)
                    covered_until = max(covered_until, stop)
                    index = stop - offset
                    line_literal = True
                    continue
                tag = re.match(r"<(/?)([A-Za-z][A-Za-z0-9-]*)\b[^>\r\n]*>", remaining)
                if tag:
                    stop = absolute + tag.end()
                    name = tag.group(2)
                    is_void = name.lower() in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
                    autolink = bool(re.match(r"<[A-Za-z][A-Za-z0-9+.-]*:", tag.group()))
                    if not tag.group(1) and not is_void and not autolink and not tag.group().rstrip().endswith("/>"):
                        depth = 1
                        pattern = r"<(/?)" + re.escape(name) + r"\b[^>\r\n]*>"
                        found = False
                        for item in re.finditer(pattern, text[stop:], re.I):
                            if item.group(1):
                                depth -= 1
                            elif not item.group().rstrip().endswith("/>"):
                                depth += 1
                            if depth == 0:
                                stop += item.end()
                                found = True
                                break
                        if not found:
                            stop = len(text)
                    if html_ranges is not None:
                        html_ranges.append((absolute, stop))
                    hide(absolute, stop)
                    covered_until = max(covered_until, stop)
                    index = stop - offset
                    line_literal = True
                    continue
            index += 1
        visible_line = "".join(masked[offset:line_end]).strip()
        if not plain.strip() or (line_literal and not visible_line):
            paragraph_open = False
        elif start_index == 0:
            if re.match(r"^ {0,3}(?:>|[-+*][ \t]|[0-9]+[.)][ \t])", plain):
                container_open = True
                paragraph_open = True
            elif not indented:
                container_open = False
                paragraph_open = not bool(re.match(r"^(?:#{1,6}(?:[ \t]|$)|(?:---+|___+|\*\*\*+)[ \t]*$)", plain))
        offset = line_end
    return "".join(masked)


def _label_key(value):
    value = re.sub(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\]^_`{|}~])", r"\1", value)
    return " ".join(value.split()).casefold()


def _bracket_pairs(text):
    stack, pairs, nested = [], {}, set()
    blank_starts = {match.start() for match in re.finditer(r"\n[ \t\r]*\n", text)}
    for index, char in enumerate(text):
        if index in blank_starts:
            stack.clear()
        if char == "[" and not _escaped(text, index):
            if stack:
                nested.add(stack[-1])
            stack.append(index)
        elif char == "]" and not _escaped(text, index) and stack:
            pairs[stack.pop()] = index
    return pairs, nested


def _paren_end(text, opening):
    depth = 1
    quote = None
    angle = False
    for index in range(opening + 1, len(text)):
        if text[index] == "\n" and re.match(r"[ \t\r]*\n", text[index + 1:]):
            return None
        if _escaped(text, index):
            continue
        if quote is not None:
            if text[index] == quote:
                quote = None
            continue
        if angle:
            if text[index] == ">":
                angle = False
            continue
        if text[index] == "<" and not text[opening + 1:index].strip():
            angle = True
            continue
        if text[index] in "\"'" and index > opening + 1 and text[index - 1].isspace():
            quote = text[index]
            continue
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _markdown_candidates(scan, pairs, nested):
    """바깥 괄호 범위를 먼저 확정한다. 복합 구문은 재작성하지 않는 후보만 반환한다."""
    definitions, definition_ranges, candidates = {}, [], []

    def open_title(value):
        marker = re.search(r"(?:^|[ \t])([\"'(])", value)
        if marker is None:
            return None
        closing = ")" if marker.group(1) == "(" else marker.group(1)
        return None if any(char == closing and not _escaped(value, index)
                           for index, char in enumerate(value[marker.end():], marker.end())) else closing

    for match in re.finditer(r"(?m)^ {0,3}\[([^]\r\n]+)\]:([^\r\n]*)", scan):
        opening = match.start() + len(match.group()) - len(match.group().lstrip(" "))
        if _escaped(scan, opening):
            continue
        definitions[_label_key(match.group(1))] = True
        stop = match.end()
        destination_pending = not match.group(2).strip()
        title_closing = open_title(match.group(2))
        cursor = scan.find("\n", stop)
        cursor = len(scan) if cursor < 0 else cursor + 1
        while cursor < len(scan):
            next_end = scan.find("\n", cursor)
            next_end = len(scan) if next_end < 0 else next_end
            continuation = scan[cursor:next_end].rstrip("\r")
            # reference destination/title continuation은 재작성 대상이 아니다.
            if continuation.strip() and (continuation.startswith((" ", "\t", "\"", "'", "("))
                                         or destination_pending or title_closing):
                stop = next_end
                cursor = next_end + 1
                destination_pending = False
                if title_closing:
                    if any(char == title_closing and not _escaped(continuation, index)
                           for index, char in enumerate(continuation)):
                        title_closing = None
                else:
                    title_closing = open_title(continuation)
            else:
                break
        definition_ranges.append((match.start(), stop))
        candidates.append((match.start(), match.start(), stop, "reference", scan[match.start():stop],
                           "reference_definition", match.start(), stop))
    position = 0
    while position < len(scan):
        if scan[position] != "[" or _escaped(scan, position):
            position += 1
            continue
        closing = pairs.get(position)
        if closing is None:
            position += 1
            continue
        if any(start <= position < end for start, end in definition_ranges):
            position = closing + 1
            continue
        # 이중 대괄호는 별도의 위키 후보가 담당한다.
        if position + 1 < len(scan) and scan[position + 1] == "[":
            position = closing + 1
            continue
        span_start = position - 1 if position and scan[position - 1] == "!" and not _escaped(scan, position - 1) else position
        label = scan[position + 1:closing]
        following = closing + 1
        if following < len(scan) and scan[following] == "(":
            end = _paren_end(scan, following)
            if end is None:
                blank = re.search(r"\n[ \t\r]*\n", scan[following:])
                stop = len(scan) if blank is None else following + blank.start()
                candidates.append((span_start, following + 1, stop, "markdown", scan[following + 1:stop],
                                   "markdown_unclosed", span_start, stop))
                position = stop
                continue
            raw = scan[following + 1:end]
            reason = None
            if position in nested or "\n" in label or any(char in raw for char in "()\r\n"):
                reason = "markdown_nested_or_complex"
            elif raw.lstrip().startswith("<") or re.search(r"\s+[\"']", raw):
                reason = "markdown_title_or_angle"
            candidates.append((span_start, following + 1, end, "markdown", raw, reason, span_start, end + 1))
            position = end + 1
            continue
        if following < len(scan) and scan[following] == "[" and following in pairs:
            end = pairs[following]
            candidates.append((span_start, position, end + 1, "reference", scan[position:end + 1],
                               "reference_full_or_collapsed", span_start, end + 1))
            position = end + 1
            continue
        if _label_key(label) in definitions:
            candidates.append((span_start, position, closing + 1, "reference", scan[position:closing + 1],
                               "reference_shortcut", span_start, closing + 1))
        position = closing + 1
    return candidates


def inventory(body, source_path, selected, *, vault_prefix=""):
    text = body.decode("utf-8")
    uncertain_ranges = []
    html_ranges = []
    scan = markdown_content(text, uncertain_ranges=uncertain_ranges, html_ranges=html_ranges)
    selected = tuple(canonical(path) for path in selected)
    vault_paths = {posixpath.join(vault_prefix, path): path for path in selected}
    matches = _markdown_candidates(scan, *_bracket_pairs(scan))
    for match in re.finditer(r"!?\[\[([^]\n]+)\]\]", scan):
        opening = match.start() + int(scan[match.start()] == "!")
        uncertainty = "escaped_wikilink" if _escaped(scan, opening) else None
        matches.append((match.start(), match.start(1), match.end(1), "wiki", match.group(1), uncertainty,
                        match.start(), match.end()))
    for start, stop in html_ranges:
        matches.append((start, start, stop, "html", text[start:stop], "html_context", start, stop))
    protected = [(item[6], item[7]) for item in matches if item[5]]
    refs = []
    for _, start, end, kind, raw, uncertainty, span_start, span_end in sorted(matches, key=lambda item: (item[0], -item[7])):
        location, separator, display = raw.partition("|") if kind == "wiki" else (raw, "", "")
        path, anchor_mark, anchor = location.partition("#")
        ref = {"reference": raw, "status": "unverified", "kind": kind,
               "start": start, "end": end, "candidates": [],
               "span_start": span_start, "span_end": span_end,
               "anchor": anchor_mark + anchor, "display": separator + display}
        if uncertainty is None and any(span_start < stop and span_end > begin for begin, stop in protected):
            uncertainty = "overlapping_unsupported_span"
        if uncertainty is None and any(other is not None and other[6] < span_end and other[7] > span_start
                                       and (other[6], other[7], other[3]) != (span_start, span_end, kind)
                                       for other in matches):
            uncertainty = "overlapping_link_syntax"
        if uncertainty:
            ref["uncertainty"] = uncertainty
            refs.append(ref)
            continue
        if any(start < stop and end > begin for begin, stop in uncertain_ranges):
            ref["uncertainty"] = "markdown_container_or_continuation"
            refs.append(ref)
            continue
        if not path:
            ref.update(status="same_document", source_path=source_path)
            refs.append(ref)
            continue
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", path):
            refs.append(ref)
            continue
        if kind == "markdown":
            # Markdown link의 optional title·angle destination은 모호하게 재작성하지 않는다.
            if path.startswith("<") or re.search(r'\s+[\"\']', path):
                refs.append(ref)
                continue
            path = unquote(path, errors="strict")
        if path.startswith("/") or "\\" in path or "\x00" in path:
            refs.append(ref)
            continue
        explicit_relative = path.startswith(("./", "../"))
        if kind == "wiki" and not explicit_relative:
            candidate = posixpath.normpath(path)
        else:
            candidate = posixpath.normpath(posixpath.join(vault_prefix, posixpath.dirname(source_path), path))
        if candidate == ".." or candidate.startswith("../"):
            refs.append(ref)
            continue
        candidates = []
        possible_paths = [candidate]
        if ((kind == "wiki" and not candidate.endswith(".md"))
                or (kind == "markdown" and not posixpath.splitext(candidate)[1])):
            possible_paths.append(candidate + ".md")
        for possible in possible_paths:
            if possible in vault_paths:
                candidates.append(vault_paths[possible])
        # Obsidian의 짧은 이름: 허용된 표 안에서 유일한 이름만 확정한다.
        if kind == "wiki" and "/" not in path:
            names = {path} if path.endswith(".md") else {path, path + ".md"}
            candidates = [value for key, value in vault_paths.items() if posixpath.basename(key) in names]
        candidates = list(dict.fromkeys(candidates))
        ref["candidates"] = candidates
        if len(candidates) == 1:
            ref.update(status="selected", source_path=candidates[0])
        elif candidates:
            ref["status"] = "ambiguous"
        refs.append(ref)
    return tuple(refs)


def rewrite(body, references, target_path, mapping, *, target_vault_prefix=""):
    """확정된 원본→복제본 대응만 적용한다. 원문·미확인 링크는 수정하지 않는다."""
    text = body.decode("utf-8")
    references = tuple(references)
    replacements = []
    output_refs = []
    protected = [(ref.get("span_start", ref["start"]), ref.get("span_end", ref["end"]))
                 for ref in references if ref["status"] == "unverified"]
    mapping = {canonical(key): canonical(value) for key, value in mapping.items()}
    for original in references:
        ref = dict(original)
        if ref["status"] not in ("selected", "same_document"):
            ref["destination_status"] = "unverified"
        elif ref["status"] == "same_document":
            ref["destination_status"] = "same_document"
        elif ref["source_path"] not in mapping:
            ref["destination_status"] = "not_copied"
        else:
            if (type(ref.get("start")) is not int or type(ref.get("end")) is not int
                    or not 0 <= ref["start"] <= ref["end"] <= len(text)
                    or text[ref["start"]:ref["end"]] != ref["reference"]):
                raise ValueError("link_reference_span")
            if any(ref["start"] < stop and ref["end"] > begin for begin, stop in protected):
                ref.update(destination_status="unverified", uncertainty="overlapping_unsupported_span")
                output_refs.append(ref)
                continue
            target = mapping[ref["source_path"]]
            if ref["kind"] == "wiki":
                destination = posixpath.join(target_vault_prefix, target)
                if destination.endswith(".md"):
                    destination = destination[:-3]
                replacement = destination + ref["anchor"] + ref["display"]
            else:
                destination = posixpath.relpath(target, posixpath.dirname(target_path) or ".")
                replacement = quote(destination, safe="/-._~") + ref["anchor"]
            replacements.append((ref["start"], ref["end"], replacement))
            ref.update(destination_path=target, destination_reference=replacement,
                       destination_status="mapped")
        output_refs.append(ref)
    ordered = sorted(replacements)
    if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
        raise ValueError("link_overlapping_rewrite")
    for start, end, replacement in reversed(ordered):
        text = text[:start] + replacement + text[end:]
    return text.encode("utf-8"), tuple(output_refs)
