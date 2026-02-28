"""Font glyph remapping utilities for Stage 4 (true font remap, not overlay)."""

from __future__ import annotations

import hashlib
import io
import logging
import os
import secrets
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

log = logging.getLogger(__name__)

try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import (
        ArrayObject,
        ByteStringObject,
        ContentStream,
        DictionaryObject,
        NameObject,
        NumberObject,
        StreamObject,
        TextStringObject,
    )
    from fontTools.ttLib import TTFont
    from pdfminer.encodingdb import EncodingDB

    _DEPS_AVAILABLE = True
    _DEPS_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - optional dependency handling
    _DEPS_AVAILABLE = False
    _DEPS_ERROR = exc


class FontRemapUnavailable(RuntimeError):
    """Raised when font remap dependencies are missing."""


class FontRemapFailure(RuntimeError):
    """Raised when a font remap attempt fails."""


@dataclass
class FontRemapAttempt:
    success: bool
    output_pdf: Path
    replaced: int = 0
    used_padding: bool = False
    padded_old: str | None = None
    padded_new: str | None = None
    error: str | None = None


@dataclass
class FontRemapBatchResult:
    output_pdf: Path
    applied: list
    failed: list
    padded: list[dict]
    errors: dict[str, str]


# Default cache dir (can be overridden per call)
_CACHE_DIR = str(Path(__file__).resolve().parent / "font_cache")

TEXT_SHOW_OPS = {b"Tj", b"TJ", b"'", b'"'}
BOUNDARY_OPS = {
    b"BT",
    b"ET",
    b"Td",
    b"TD",
    b"T*",
    b"Tm",
    b"cm",
    b"q",
    b"Q",
}

SYSTEM_FONT_DIRS = [
    "/System/Library/Fonts/Supplemental",
    "/Library/Fonts",
]

SYSTEM_FONT_MAP = {
    "ArialMT": "/System/Library/Fonts/Supplemental/Arial.ttf",
    "Arial-BoldMT": "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "TimesNewRomanPSMT": "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "TimesNewRomanPS-BoldMT": "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
    "TimesNewRomanPS-BoldItalicMT": "/System/Library/Fonts/Supplemental/Times New Roman Bold Italic.ttf",
    "TimesNewRomanPS-ItalicMT": "/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf",
}


def _ensure_deps() -> None:
    if _DEPS_AVAILABLE:
        return
    raise FontRemapUnavailable(
        f"Font remap dependencies missing: {_DEPS_ERROR}"
    )


def _set_cache_dir(cache_dir: str | Path | None) -> None:
    global _CACHE_DIR
    if cache_dir is None:
        return
    _CACHE_DIR = str(Path(cache_dir))


def _ensure_cache_dir() -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)


def _random_tag() -> str:
    return "".join([secrets.choice(string.ascii_uppercase) for _ in range(6)])


def _normalize_font_name(name: str) -> str:
    name = os.path.splitext(name)[0]
    return "".join([c.lower() for c in name if c.isalnum()])


def _font_name_variants(name: str) -> list[str]:
    n = _normalize_font_name(name)
    variants = {n}
    for suf in ("psmt", "mt", "ps"):
        if n.endswith(suf):
            variants.add(n[: -len(suf)])
    return list(variants)


def _resolve_system_font(base_name: str) -> str | None:
    if base_name in SYSTEM_FONT_MAP:
        path = SYSTEM_FONT_MAP[base_name]
        if os.path.exists(path):
            return path

    targets = _font_name_variants(base_name)
    for root in SYSTEM_FONT_DIRS:
        if not os.path.isdir(root):
            continue
        for fname in os.listdir(root):
            if not fname.lower().endswith((".ttf", ".otf")):
                continue
            norm = _normalize_font_name(fname)
            if any(t in norm for t in targets):
                return os.path.join(root, fname)
    return None


def _text_from_tokens(tokens: List) -> str:
    out = []
    for t in tokens:
        if isinstance(t, str):
            out.append(t)
        elif isinstance(t, (bytes, ByteStringObject)):
            out.append(bytes(t).decode("latin-1"))
    return "".join(out)


def _tokens_from_segments(segments: List[Tuple[str, List[NumberObject], str]]) -> list:
    tokens = []
    for text, nums, kind in segments:
        if text:
            if kind == "bytes":
                tokens.append(ByteStringObject(text.encode("latin-1")))
            else:
                tokens.append(TextStringObject(text))
        for n in nums:
            tokens.append(n)
    return tokens


def _segments_from_tokens(tokens: List):
    segments = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if isinstance(tok, str):
            nums = []
            j = i + 1
            while j < len(tokens) and isinstance(tokens[j], NumberObject):
                nums.append(tokens[j])
                j += 1
            segments.append((tok, nums, "str"))
            i = j
        elif isinstance(tok, (bytes, ByteStringObject)):
            nums = []
            j = i + 1
            while j < len(tokens) and isinstance(tokens[j], NumberObject):
                nums.append(tokens[j])
                j += 1
            segments.append((bytes(tok).decode("latin-1"), nums, "bytes"))
            i = j
        else:
            segments.append(("", [tok], "str"))
            i += 1
    return segments


def _slice_segments(
    segments: List[Tuple[str, List[NumberObject], str]], start: int, end: int
):
    before: List[Tuple[str, List[NumberObject], str]] = []
    mid: List[Tuple[str, List[NumberObject], str]] = []
    after: List[Tuple[str, List[NumberObject], str]] = []
    pos = 0
    for text, nums, kind in segments:
        seg_len = len(text)
        seg_start = pos
        seg_end = pos + seg_len
        if seg_end <= start:
            before.append((text, nums, kind))
        elif seg_start >= end:
            after.append((text, nums, kind))
        else:
            before_text = ""
            mid_text = ""
            after_text = ""
            if start > seg_start:
                before_text = text[: start - seg_start]
            if end < seg_end:
                after_text = text[end - seg_start :]
            mid_start = max(start, seg_start) - seg_start
            mid_end = min(end, seg_end) - seg_start
            mid_text = text[mid_start:mid_end]

            parts = []
            if before_text:
                parts.append(("before", before_text))
            if mid_text:
                parts.append(("mid", mid_text))
            if after_text:
                parts.append(("after", after_text))

            for idx, (kind_label, part_text) in enumerate(parts):
                part_nums = nums if idx == len(parts) - 1 else []
                if kind_label == "before":
                    before.append((part_text, part_nums, kind))
                elif kind_label == "mid":
                    mid.append((part_text, part_nums, kind))
                else:
                    after.append((part_text, part_nums, kind))
        pos += seg_len
    return before, mid, after


def _replace_segments_text(
    segments: List[Tuple[str, List[NumberObject], str]], new_text: str
):
    out = []
    idx = 0
    for text, nums, kind in segments:
        seg_len = len(text)
        seg_new = new_text[idx : idx + seg_len]
        out.append((seg_new, nums, kind))
        idx += seg_len
    return out


def _find_occurrences(text: str, target: str):
    starts = []
    idx = 0
    while True:
        idx = text.find(target, idx)
        if idx == -1:
            break
        starts.append(idx)
        idx += len(target)
    return starts


def _decode_text_operand(obj):
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (bytes, ByteStringObject)):
        return bytes(obj).decode("latin-1")
    return ""


def _operation_text(operands, operator):
    if operator == b"Tj":
        return _decode_text_operand(operands[0])
    if operator == b"TJ":
        return _text_from_tokens(operands[0])
    if operator == b"'":
        return _decode_text_operand(operands[0])
    if operator == b'"':
        return _decode_text_operand(operands[2])
    return ""


def _tokens_from_operation(operands, operator):
    if operator == b"Tj":
        return [operands[0]]
    if operator == b"TJ":
        return operands[0]
    if operator == b"'":
        return [operands[0]]
    if operator == b'"':
        return [operands[2]]
    return []


def _operation_from_tokens(tokens):
    if len(tokens) == 1:
        return ([tokens[0]], b"Tj")
    return ([ArrayObject(tokens)], b"TJ")


def _build_cache_key(font_bytes: bytes, mapping: Dict[int, int], name: str):
    h = hashlib.sha256()
    h.update(font_bytes)
    h.update(str(sorted(mapping.items())).encode("utf-8"))
    h.update(name.encode("utf-8"))
    return h.hexdigest()[:16]


def _build_malicious_font(font_bytes: bytes, mapping: Dict[int, int], new_name: str):
    font = TTFont(io.BytesIO(font_bytes))
    cmap = font["cmap"]
    for table in cmap.tables:
        if table.isUnicode():
            for new_cp, old_cp in mapping.items():
                if old_cp in table.cmap:
                    table.cmap[new_cp] = table.cmap[old_cp]
    name_table = font["name"]
    for record in name_table.names:
        if record.nameID == 1:
            record.string = new_name.encode("utf-16-be")
    out = io.BytesIO()
    font.save(out)
    return out.getvalue()


def _new_font_stream(writer: PdfWriter, font_bytes: bytes):
    font_stream = StreamObject()
    font_stream._data = font_bytes
    font_stream[NameObject("/Length")] = NumberObject(len(font_bytes))
    return writer._add_object(font_stream)


def _build_to_unicode_cmap(mapping: Dict[int, int]) -> bytes:
    lines = [
        "/CIDInit /ProcSet findresource begin",
        "12 dict begin",
        "begincmap",
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def",
        "/CMapName /Adobe-Identity-UCS def",
        "/CMapType 2 def",
        "1 begincodespacerange",
        "<00> <FF>",
        "endcodespacerange",
    ]

    entries = []
    for new_cp in sorted(mapping.keys()):
        if not (0 <= new_cp <= 0xFF):
            continue
        try:
            uni = chr(new_cp)
        except ValueError:
            continue
        utf16 = uni.encode("utf-16-be").hex().upper()
        entries.append((new_cp, utf16))

    if entries:
        lines.append(f"{len(entries)} beginbfchar")
        for code, uni_hex in entries:
            lines.append(f"<{code:02X}> <{uni_hex}>")
        lines.append("endbfchar")

    lines.extend(
        [
            "endcmap",
            "CMapName currentdict /CMap defineresource pop",
            "end",
            "end",
        ]
    )
    return ("\n".join(lines) + "\n").encode("ascii")


def _attach_to_unicode(writer: PdfWriter, new_font: DictionaryObject, mapping: Dict[int, int]) -> None:
    cmap_bytes = _build_to_unicode_cmap(mapping)
    stream = StreamObject()
    stream._data = cmap_bytes
    stream[NameObject("/Length")] = NumberObject(len(cmap_bytes))
    new_font[NameObject("/ToUnicode")] = writer._add_object(stream)


def _clone_font_dict(obj):
    new = DictionaryObject()
    for k, v in obj.items():
        new[k] = v
    return new


def _get_font_file_bytes(font_obj: DictionaryObject):
    if "/FontDescriptor" not in font_obj:
        raise ValueError("FontDescriptor missing")
    fd = font_obj["/FontDescriptor"].get_object()
    for key in ("/FontFile2", "/FontFile3", "/FontFile"):
        if key in fd:
            stream = fd[key].get_object()
            return stream.get_data(), key
    raise ValueError("No embedded font file found")


def _base_encoding_list(name: str):
    if name in EncodingDB.encodings:
        enc = EncodingDB.encodings[name]
        return [c for c in enc]
    return [None] * 256


def _build_differences(diff_map):
    diffs = ArrayObject()
    for code, name in sorted(diff_map.items()):
        diffs.append(NumberObject(code))
        diffs.append(NameObject(f"/{name}"))
    return diffs


def _parse_encoding(encoding_obj):
    base_name = "StandardEncoding"
    diff_map = {}
    if encoding_obj is None:
        return base_name, diff_map
    if hasattr(encoding_obj, "get_object"):
        encoding_obj = encoding_obj.get_object()
    if isinstance(encoding_obj, NameObject):
        base_name = str(encoding_obj).lstrip("/")
        return base_name, diff_map
    if isinstance(encoding_obj, DictionaryObject):
        base = encoding_obj.get("/BaseEncoding")
        if base is not None:
            base_name = str(base).lstrip("/")
        diffs = encoding_obj.get("/Differences", [])
        if hasattr(diffs, "get_object"):
            diffs = diffs.get_object()
        current = None
        for item in diffs:
            if isinstance(item, NumberObject):
                current = int(item)
            elif isinstance(item, NameObject):
                if current is not None:
                    diff_map[current] = str(item).lstrip("/")
                    current += 1
        return base_name, diff_map
    return base_name, diff_map


def _make_new_type1_font(
    writer: PdfWriter, font_obj: DictionaryObject, mapping: Dict[int, int]
):
    new_font = _clone_font_dict(font_obj)
    base_name = str(font_obj.get("/BaseFont", "/Font")).lstrip("/")
    new_tag = _random_tag()
    new_base_name = f"{new_tag}+{base_name.split('+')[-1]}"
    new_font[NameObject("/BaseFont")] = NameObject(f"/{new_base_name}")

    base_enc_name, diff_map = _parse_encoding(font_obj.get("/Encoding"))
    base_list = _base_encoding_list(base_enc_name)
    for new_cp, old_cp in mapping.items():
        old_name = None
        if old_cp < len(base_list):
            old_name = base_list[old_cp]
        if old_cp in diff_map:
            old_name = diff_map[old_cp]
        if old_name:
            diff_map[new_cp] = old_name

    new_encoding = DictionaryObject()
    if base_enc_name:
        new_encoding[NameObject("/BaseEncoding")] = NameObject(f"/{base_enc_name}")
    new_encoding[NameObject("/Differences")] = _build_differences(diff_map)
    new_font[NameObject("/Encoding")] = writer._add_object(new_encoding)

    first_char = int(font_obj.get("/FirstChar", 0))
    widths_obj = font_obj.get("/Widths", [])
    if hasattr(widths_obj, "get_object"):
        widths_obj = widths_obj.get_object()
    widths = list(widths_obj)
    for new_cp, old_cp in mapping.items():
        idx_new = new_cp - first_char
        idx_old = old_cp - first_char
        if 0 <= idx_new < len(widths) and 0 <= idx_old < len(widths):
            widths[idx_new] = widths[idx_old]
    new_font[NameObject("/Widths")] = ArrayObject([NumberObject(w) for w in widths])
    _attach_to_unicode(writer, new_font, mapping)

    new_font_ref = writer._add_object(new_font)
    return new_font_ref, new_base_name


def _make_new_font(writer: PdfWriter, font_obj: DictionaryObject, mapping: Dict[int, int]):
    subtype = str(font_obj.get("/Subtype", "")).lstrip("/")
    if subtype in ("Type1", "MMType1"):
        return _make_new_type1_font(writer, font_obj, mapping)

    try:
        font_bytes, font_file_key = _get_font_file_bytes(font_obj)
    except ValueError:
        base_name = str(font_obj.get("/BaseFont", "/Font")).lstrip("/")
        sys_font = _resolve_system_font(base_name)
        if not sys_font:
            raise
        with open(sys_font, "rb") as f:
            font_bytes = f.read()
        font_file_key = "/FontFile2"
    base_name = str(font_obj.get("/BaseFont", "/Font"))
    base_name = base_name.lstrip("/")
    new_tag = _random_tag()
    new_base_name = f"{new_tag}+{base_name.split('+')[-1]}"

    cache_key = _build_cache_key(font_bytes, mapping, new_base_name)
    cache_path = os.path.join(_CACHE_DIR, f"{new_base_name}_{cache_key}.ttf")
    if os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            new_font_bytes = f.read()
    else:
        new_font_bytes = _build_malicious_font(font_bytes, mapping, new_base_name)
        _ensure_cache_dir()
        with open(cache_path, "wb") as f:
            f.write(new_font_bytes)

    new_font_file = _new_font_stream(writer, new_font_bytes)

    new_font = _clone_font_dict(font_obj)
    new_font[NameObject("/BaseFont")] = NameObject(f"/{new_base_name}")

    fd = font_obj.get("/FontDescriptor").get_object()
    new_fd = _clone_font_dict(fd)
    new_fd[NameObject("/FontName")] = NameObject(f"/{new_base_name}")
    new_fd[NameObject(font_file_key)] = new_font_file
    new_fd_ref = writer._add_object(new_fd)
    new_font[NameObject("/FontDescriptor")] = new_fd_ref

    first_char = int(font_obj.get("/FirstChar", 0))
    widths_obj = font_obj.get("/Widths", [])
    if hasattr(widths_obj, "get_object"):
        widths_obj = widths_obj.get_object()
    widths = list(widths_obj)
    for new_cp, old_cp in mapping.items():
        idx_new = new_cp - first_char
        idx_old = old_cp - first_char
        if 0 <= idx_new < len(widths) and 0 <= idx_old < len(widths):
            widths[idx_new] = widths[idx_old]
    new_font[NameObject("/Widths")] = ArrayObject([NumberObject(w) for w in widths])
    _attach_to_unicode(writer, new_font, mapping)

    new_font_ref = writer._add_object(new_font)
    return new_font_ref, new_base_name


def _unique_font_name(font_dict: DictionaryObject, prefix: str = "/FMSWAP"):
    idx = 0
    while True:
        name = NameObject(f"{prefix}{idx}")
        if name not in font_dict:
            return name
        idx += 1


def _build_mapping(old_word: str, new_word: str):
    if len(old_word) != len(new_word):
        raise ValueError("Old and new words must have the same length for layout safety")
    mapping: Dict[int, int] = {}
    conflict = False
    for new_ch, old_ch in zip(new_word, old_word):
        if ord(new_ch) in mapping and mapping[ord(new_ch)] != ord(old_ch):
            conflict = True
        mapping[ord(new_ch)] = ord(old_ch)
    return mapping, conflict


def _mapping_key(mapping: Dict[int, int]):
    return tuple(sorted(mapping.items()))


def _get_or_create_font(
    writer: PdfWriter,
    page,
    font_key: NameObject,
    mapping: Dict[int, int],
    font_cache: Dict,
):
    key = (font_key, _mapping_key(mapping))
    if key in font_cache:
        return font_cache[key]
    font_obj = page["/Resources"]["/Font"][font_key].get_object()
    new_font_ref, _ = _make_new_font(writer, font_obj, mapping)
    new_font_name = _unique_font_name(page["/Resources"]["/Font"])
    page["/Resources"]["/Font"][new_font_name] = new_font_ref
    font_cache[key] = new_font_name
    return new_font_name


def _replace_in_text_op(
    operands,
    operator,
    ranges,
    mapping,
    conflict,
    font_key,
    current_font,
    current_size,
    page,
    writer,
    font_cache,
):
    tokens = _tokens_from_operation(operands, operator)
    segments = _segments_from_tokens(tokens)
    out_ops = []

    if operator == b"'":
        out_ops.append(([], b"T*"))
    elif operator == b'"':
        if len(operands) >= 2:
            out_ops.append(([operands[0]], b"Tw"))
            out_ops.append(([operands[1]], b"Tc"))
        out_ops.append(([], b"T*"))

    remaining_segments = segments
    offset = 0
    for range_start, range_end, old_slice, new_slice in ranges:
        before, mid, after = _slice_segments(
            remaining_segments, range_start - offset, range_end - offset
        )
        if before:
            b_tokens = _tokens_from_segments(before)
            out_ops.append(_operation_from_tokens(b_tokens))
        if mid:
            mid = _replace_segments_text(mid, new_slice)
            if conflict:
                pos = 0
                for text, nums, kind in mid:
                    for idx_ch, ch in enumerate(text):
                        old_ch = old_slice[pos]
                        new_ch = new_slice[pos]
                        pos += 1
                        char_map = {ord(new_ch): ord(old_ch)}
                        swap_font_name = _get_or_create_font(
                            writer, page, font_key, char_map, font_cache
                        )
                        out_ops.append(
                            ([swap_font_name, NumberObject(current_size)], b"Tf")
                        )
                        if kind == "bytes":
                            tok = ByteStringObject(ch.encode("latin-1"))
                        else:
                            tok = TextStringObject(ch)
                        token_list = [tok]
                        if idx_ch == len(text) - 1 and nums:
                            token_list.extend(nums)
                        out_ops.append(_operation_from_tokens(token_list))
                out_ops.append(([current_font, NumberObject(current_size)], b"Tf"))
            else:
                swap_font_name = _get_or_create_font(
                    writer, page, font_key, mapping, font_cache
                )
                out_ops.append(([swap_font_name, NumberObject(current_size)], b"Tf"))
                mid_tokens = _tokens_from_segments(mid)
                out_ops.append(_operation_from_tokens(mid_tokens))
                out_ops.append(([current_font, NumberObject(current_size)], b"Tf"))
        remaining_segments = after
        offset = range_end

    if remaining_segments:
        a_tokens = _tokens_from_segments(remaining_segments)
        out_ops.append(_operation_from_tokens(a_tokens))

    return out_ops


def _process_chunk(
    chunk_ops,
    current_font,
    current_size,
    page,
    writer,
    font_cache,
    old_word,
    new_word,
):
    chunk_text = ""
    op_offsets: Dict[int, int] = {}
    text_op_indices = []
    for idx, (operands, operator) in enumerate(chunk_ops):
        if operator in TEXT_SHOW_OPS:
            text = _operation_text(operands, operator)
            op_offsets[idx] = len(chunk_text)
            chunk_text += text
            text_op_indices.append(idx)

    if not chunk_text or old_word not in chunk_text:
        return chunk_ops, 0

    if current_font is None or current_size is None:
        return chunk_ops, 0

    starts = _find_occurrences(chunk_text, old_word)
    if not starts:
        return chunk_ops, 0

    replacement_chars = [None] * len(chunk_text)
    for start in starts:
        for j, ch in enumerate(new_word):
            replacement_chars[start + j] = ch

    ranges_by_op: Dict[int, List[Tuple[int, int, str, str]]] = {}
    for idx in text_op_indices:
        operands, operator = chunk_ops[idx]
        text = _operation_text(operands, operator)
        start_offset = op_offsets[idx]
        rep_slice = replacement_chars[start_offset : start_offset + len(text)]
        ranges = []
        i = 0
        while i < len(text):
            if rep_slice[i] is None:
                i += 1
                continue
            j = i
            new_chars = []
            while j < len(text) and rep_slice[j] is not None:
                new_chars.append(rep_slice[j])
                j += 1
            old_slice = text[i:j]
            new_slice = "".join(new_chars)
            ranges.append((i, j, old_slice, new_slice))
            i = j
        if ranges:
            ranges_by_op[idx] = ranges

    mapping, conflict = _build_mapping(old_word, new_word)
    new_chunk = []
    for idx, (operands, operator) in enumerate(chunk_ops):
        if operator in TEXT_SHOW_OPS and idx in ranges_by_op:
            if current_font is None or current_size is None:
                new_chunk.append((operands, operator))
                continue
            new_chunk.extend(
                _replace_in_text_op(
                    operands,
                    operator,
                    ranges_by_op[idx],
                    mapping,
                    conflict,
                    current_font,
                    current_font,
                    current_size,
                    page,
                    writer,
                    font_cache,
                )
            )
        else:
            new_chunk.append((operands, operator))

    return new_chunk, len(starts)


def replace_word_in_pdf(
    input_pdf: str | Path,
    output_pdf: str | Path,
    old_word: str,
    new_word: str,
    *,
    cache_dir: str | Path | None = None,
) -> int:
    _ensure_deps()
    _set_cache_dir(cache_dir)

    input_pdf = str(input_pdf)
    output_pdf = str(output_pdf)

    reader = PdfReader(input_pdf)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)

    replaced = 0

    for page_index, page in enumerate(writer.pages):
        content = ContentStream(page["/Contents"], writer)
        ops = content.operations
        new_ops = []
        current_font = None
        current_size = None
        font_cache = {}
        chunk_ops = []

        def flush_chunk():
            nonlocal replaced
            if not chunk_ops:
                return
            chunk_out, count = _process_chunk(
                chunk_ops,
                current_font,
                current_size,
                page,
                writer,
                font_cache,
                old_word,
                new_word,
            )
            new_ops.extend(chunk_out)
            replaced += count
            chunk_ops.clear()

        for operands, operator in ops:
            if operator == b"Tf":
                flush_chunk()
                new_ops.append((operands, operator))
                current_font = operands[0]
                current_size = float(operands[1])
                continue

            if operator in BOUNDARY_OPS:
                flush_chunk()
                new_ops.append((operands, operator))
                continue

            if operator in (b"'", b'"'):
                flush_chunk()
                chunk_ops.append((operands, operator))
                flush_chunk()
                continue

            chunk_ops.append((operands, operator))

        flush_chunk()

        content.operations = new_ops
        page[NameObject("/Contents")] = writer._add_object(content)

    if replaced == 0:
        raise FontRemapFailure(f"No occurrences of '{old_word}' found")

    with open(output_pdf, "wb") as f:
        writer.write(f)

    return replaced


def _pad_to_equal_length(old_word: str, new_word: str) -> tuple[str, str]:
    if len(old_word) == len(new_word):
        return old_word, new_word
    if len(old_word) < len(new_word):
        old_word = old_word + (" " * (len(new_word) - len(old_word)))
    else:
        new_word = new_word + (" " * (len(old_word) - len(new_word)))
    return old_word, new_word


def attempt_font_remap(
    input_pdf: str | Path,
    output_pdf: str | Path,
    old_word: str,
    new_word: str,
    *,
    cache_dir: str | Path | None = None,
    allow_space_pad: bool = True,
) -> FontRemapAttempt:
    input_pdf = Path(input_pdf)
    output_pdf = Path(output_pdf)
    try:
        replaced = replace_word_in_pdf(
            input_pdf,
            output_pdf,
            old_word,
            new_word,
            cache_dir=cache_dir,
        )
        return FontRemapAttempt(
            success=True,
            output_pdf=output_pdf,
            replaced=replaced,
            used_padding=False,
        )
    except Exception as exc:
        error = str(exc)
        if allow_space_pad and len(old_word) != len(new_word):
            padded_old, padded_new = _pad_to_equal_length(old_word, new_word)
            try:
                replaced = replace_word_in_pdf(
                    input_pdf,
                    output_pdf,
                    padded_old,
                    padded_new,
                    cache_dir=cache_dir,
                )
                return FontRemapAttempt(
                    success=True,
                    output_pdf=output_pdf,
                    replaced=replaced,
                    used_padding=True,
                    padded_old=padded_old,
                    padded_new=padded_new,
                )
            except Exception as exc2:
                error = f"{error}; padding_retry_failed: {exc2}"
        return FontRemapAttempt(
            success=False,
            output_pdf=output_pdf,
            error=error,
        )


def apply_font_remap_replacements(
    input_pdf: str | Path,
    output_pdf: str | Path,
    replacements: list,
    *,
    cache_dir: str | Path | None = None,
    allow_space_pad: bool = True,
) -> FontRemapBatchResult:
    _ensure_deps()
    input_pdf = Path(input_pdf)
    output_pdf = Path(output_pdf)

    applied: list = []
    failed: list = []
    padded: list[dict] = []
    errors: dict[str, str] = {}

    if not replacements:
        if input_pdf != output_pdf:
            output_pdf.write_bytes(input_pdf.read_bytes())
        return FontRemapBatchResult(
            output_pdf=output_pdf,
            applied=applied,
            failed=failed,
            padded=padded,
            errors=errors,
        )

    work_dir = output_pdf.parent
    work_dir.mkdir(parents=True, exist_ok=True)
    temp_path = work_dir / f"{output_pdf.stem}.font_remap_work{output_pdf.suffix}"

    current_path = input_pdf
    next_path = output_pdf if current_path != output_pdf else temp_path

    for item in replacements:
        old_word = (getattr(item, "search_key", None) or "").strip()
        new_word = (getattr(item, "replacement", None) or "").strip()
        if not old_word or not new_word:
            failed.append(item)
            errors[getattr(item, "search_key", "<missing>")] = "Missing search_key or replacement"
            continue

        attempt = attempt_font_remap(
            current_path,
            next_path,
            old_word,
            new_word,
            cache_dir=cache_dir,
            allow_space_pad=allow_space_pad,
        )
        if attempt.success:
            applied.append(item)
            if attempt.used_padding:
                padded.append(
                    {
                        "search_key": old_word,
                        "replacement": new_word,
                        "padded_old": attempt.padded_old,
                        "padded_new": attempt.padded_new,
                    }
                )
            current_path = next_path
            next_path = temp_path if current_path == output_pdf else output_pdf
        else:
            failed.append(item)
            errors[old_word] = attempt.error or "Unknown font remap error"

    if current_path != output_pdf:
        if output_pdf.exists():
            output_pdf.unlink()
        output_pdf.write_bytes(current_path.read_bytes())

    return FontRemapBatchResult(
        output_pdf=output_pdf,
        applied=applied,
        failed=failed,
        padded=padded,
        errors=errors,
    )
