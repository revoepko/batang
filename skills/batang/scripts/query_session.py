"""JSON-lines query session for the existing read-only query helpers."""
import json
import os
import sys
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from file_ops import FileScope
from query_ops import (QueryContext, QueryLimits, search, relations,
                       read_spans, prepare_review_context)


MAX_REQUEST = 1024 * 1024
MAX_RESPONSE = 1024 * 1024


def pairs(values):
    result = {}
    for key, value in values:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      allow_nan=False, separators=(",", ":")).encode("utf-8")


def build(config, context_id):
    if not isinstance(config, dict):
        raise ValueError("configuration")
    paths = config["selected_paths"]
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
        raise ValueError("selection")
    active = config["active_path"]
    notes = FileScope(config["root"], [active, *paths])
    graph = config.get("graph")
    graph_scope = None if graph is None else FileScope(graph["root"], [graph["path"]])
    context = QueryContext(notes, active, paths, graph_scope=graph_scope,
                           graph_path=None if graph is None else graph["path"],
                           context_id=context_id)
    source = config.get("source")
    source_scope = None if source is None else FileScope(source["root"], source["paths"])
    return context, source_scope


def delivered_refs(result):
    # 포괄 item.ref는 실제 전송되지 않은 구간을 포함할 수 있다.
    refs = []
    for item in result.get("items", []):
        if isinstance(item.get("record_ref"), dict):
            refs.append(item["record_ref"])
        for span in item.get("spans", []):
            if isinstance(span, dict) and isinstance(span.get("ref"), dict):
                refs.append(span["ref"])
    return refs


def main():
    if sys.stdin.isatty():
        import termios
        settings = termios.tcgetattr(sys.stdin.fileno())
        settings[3] &= ~(termios.ECHO | termios.ICANON)
        settings[6][termios.VMIN] = 1
        settings[6][termios.VTIME] = 0
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, settings)

    ctx = source_scope = None
    configuration = None
    pending = None
    sequence = 0

    print('{"status":"ready"}', flush=True)
    while True:
        raw = sys.stdin.buffer.readline(MAX_REQUEST + 1)
        if not raw:
            break
        if len(raw) > MAX_REQUEST or not raw.endswith(b"\n"):
            print('{"status":"error","code":"request_size_or_frame"}', flush=True)
            break
        try:
            request = json.loads(raw, object_pairs_hook=pairs,
                                 parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            if not isinstance(request, dict):
                raise ValueError("request")
            op = request["op"]
            if op == "close":
                print('{"status":"closed"}', flush=True)
                break
            if op == "open":
                ctx = source_scope = configuration = pending = None
                new_config = request["config"]
                new_context, new_source = build(new_config, str(uuid.uuid4()))
                ctx, source_scope, configuration = new_context, new_source, new_config
                pending = None
                print('{"status":"opened"}', flush=True)
                continue
            if ctx is None:
                raise ValueError("not_open")
            if op == "reset_context":
                ctx, source_scope = build(configuration, str(uuid.uuid4()))
                pending = None
                print('{"status":"context_reset"}', flush=True)
                continue
            if op == "ack":
                if (pending is None or type(request.get("response_id")) is not int
                        or request["response_id"] != pending[0]):
                    raise ValueError("confirmation")
                ctx.confirm_seen(pending[1])
                pending = None
                print('{"status":"acknowledged"}', flush=True)
                continue
            args = request.get("args", {})
            values = request.get("limits", {})
            if not isinstance(args, dict) or not isinstance(values, dict):
                raise ValueError("arguments")
            response_limit = values.get("max_bytes", 16384)
            if type(response_limit) is not int or not 1024 <= response_limit <= MAX_RESPONSE:
                raise ValueError("response_limit")
            values = dict(values, max_bytes=response_limit - 256)
            limits = QueryLimits(**values)
            if op == "search":
                result = search(ctx, limits=limits, **args)
            elif op == "relations":
                result = relations(ctx, limits=limits, **args)
            elif op == "read_spans":
                result = read_spans(ctx, limits=limits, **args)
            elif op == "prepare_review_context":
                if args.get("stage") == "pre_registration":
                    result = prepare_review_context(ctx, source_scope=source_scope,
                                                    limits=limits, **args)
                else:
                    result = prepare_review_context(ctx, limits=limits, **args)
            else:
                raise ValueError("operation")
            sequence += 1
            reply = {"response_id": sequence, "result": result}
            data = encode(reply)
            pending = None
            if len(data) > response_limit:
                raise ValueError("response_size")
            print(data.decode("utf-8"), flush=True)
            pending = (sequence, delivered_refs(result))
        except (ValueError, TypeError, KeyError, OSError):
            pending = None
            print('{"status":"error","code":"invalid_or_unavailable"}', flush=True)


if __name__ == "__main__":
    main()
