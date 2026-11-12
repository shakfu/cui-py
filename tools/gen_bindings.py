#!/usr/bin/env python3
"""Generate the Cython layer for CUI from its public headers.

Writes:
    src/cui/_cui.pxd      every declaration libclang can express in Cython
    src/cui/_gen.pxi      Context methods, scope classes, converters, constants
    src/cui/_core.pyi     type stubs for the extension
    docs/dev/coverage.md  what was wrapped, and why the rest was not

Usage:
    uv run --no-project --with libclang python tools/gen_bindings.py

The output is committed, so building the package does not need libclang.
"""

from __future__ import annotations

import keyword
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from clang import cindex as ci

ROOT = Path(__file__).resolve().parents[1]
INC = ROOT / "thirdparty" / "cui" / "include"
OUT = ROOT / "src" / "cui"
HEADERS = ["cui/cui.h", "cui/cui_render.h", "cui/cui_app.h"]
TK = ci.TypeKind
CK = ci.CursorKind

# ---------------------------------------------------------------------------
# Policy tables. Everything here is a fact about CUI's API that the header
# states only in comments.
# ---------------------------------------------------------------------------

# begin/end pairs without a CUI__SCOPE macro: name -> (begin, end, end_only_if_begin_true)
EXTRA_SCOPES = {
    "kanban": ("cui_kanban_begin", "cui_kanban_end", False),
    "kanban_column": ("cui_kanban_column_begin_ex", "cui_kanban_column_end", False),
    "kanban_card": ("cui_kanban_card_begin", "cui_kanban_card_end", False),
    "data_grid": ("cui_data_grid_begin_ex", "cui_data_grid_end", True),
    "node_editor": ("cui_node_editor_begin_ex", "cui_node_editor_end", True),
    "node": ("cui_node_begin_ex", "cui_node_end", False),
    "path_bar_menu": ("cui_path_bar_menu_begin", "cui_path_bar_menu_end", True),
    "reorder": ("cui_reorder_begin", "cui_reorder_end", False),
    "swipe_item": ("cui_swipe_item_begin", "cui_swipe_item_end", False),
    "card_stack": ("cui_card_stack_begin", "cui_card_stack_end", False),
    "tree_table": ("cui_tree_table_begin_ex", "cui_tree_table_end", False),
}

# Pointer parameters that are written but never read.
OUT_ONLY = {
    ("cui_virtual_list_begin", "first"),
    ("cui_virtual_list_begin", "last"),
    ("cui_data_grid_begin_ex", "first"),
    ("cui_data_grid_begin_ex", "last"),
    ("cui_node_link_created", "from_pin"),
    ("cui_node_link_created", "to_pin"),
    ("cui_node_link_removed", "link_id"),
    ("cui_node_deleted", "node_id"),
    ("cui_image_load", "w"),
    ("cui_image_load", "h"),
    ("cui_cron_next", "next"),
}

# Scalar pointers that are arrays: (function, param) -> name of the length param.
INOUT_ARRAYS = {
    ("cui_toggle_group_ex", "values"): "count",
    ("cui_multi_select_ex", "selected"): "count",
    ("cui_reorder_begin", "order"): "count",
    ("cui_prop_vec_ex", "value"): "components",
    ("cui_filter_bar", "selected"): "count",  # selected[i] is the mask of fields[i]
}

# Scalar pointers followed by a count that are still one value.
SCALAR_PTRS = {("cui_pagination", "page")}

# Wrapped by hand in _core.pyx (validation or callbacks the generator cannot express).
MANUAL = {
    "cui_create",
    "cui_destroy",
    "cui_set_platform",
    "cui_begin_frame",
    "cui_end_frame",
    "cui_get_draw_data",
    "cui_canvas",
    "cui_image_create",
    "cui_font_load_memory",
    "cui_emoji_font_load_memory",
    "cui_app_create",
    "cui_app_destroy",
    "cui_app_frame",
    "cui_app_ui",
    "cui_app_run",
    "cui_app_quit",
    "cui_app_set_title",
    "cui_app_set_size",
    "cui_app_size",
    "cui_app_is_software",
    "cui_app_backend",
    "cui_app_file_dialog",
    "cui_app_open_url",
    "cui_app_screenshot",
    "cui_sw_create",
    "cui_sw_destroy",
    "cui_sw_iface",
    "cui_sw_render",
    "cui_write_png",
}

# Not exposed: function -> reason.
EXCLUDED = {
    "cui_set_renderer": "Context owns its renderer",
    "cui_app_native_window": "a raw native handle has no safe Python use",
    "cui_sw_set_threads": "the software renderer is internal to Context",
    "cui_sw_set_incremental": "the software renderer is internal to Context",
    "cui_sw_last_damage": "the software renderer is internal to Context",
    "cui_gl_create": "OpenGL integration needs a GL loader from the host",
    "cui_gl_destroy": "OpenGL integration needs a GL loader from the host",
    "cui_gl_iface": "OpenGL integration needs a GL loader from the host",
    "cui_gl_render": "OpenGL integration needs a GL loader from the host",
    "cui_gl_read_pixels": "OpenGL integration needs a GL loader from the host",
    "cui_gl_is_software": "OpenGL integration needs a GL loader from the host",
    "cui_state": "raw per-id memory for C components",
    "cui_state_on_free": "raw per-id memory for C components",
}

# Context methods that need no open frame.
ANYTIME_PREFIXES = (
    "cui_input_",
    "cui_set_",
    "cui_get_",
    "cui_font_",
    "cui_emoji_font_",
    "cui_request_",
    "cui_image_load",
    "cui_image_destroy",
)
ANYTIME = {
    "cui_needs_redraw",
    "cui_next_wakeup",
    "cui_time",
    "cui_delta_time",
    "cui_frame_count",
    "cui_viewport_size",
    "cui_dpi_scale",
    "cui_measure_text",
    "cui_color_of",
    "cui_token_color",
    "cui_theme_get",
    "cui_wants_keyboard",
    "cui_wants_mouse",
    "cui_popover_open",
    "cui_popover_close",
    "cui_popover_toggle",
}
# Only valid inside a canvas paint callback.
PAINT_PREFIXES = ("cui_draw_", "cui_push_clip", "cui_pop_clip")

# Value structs with a hand-written Python type in _core.pyx.
SPECIAL_VALUES = {
    "cui_color",
    "cui_rect",
    "cui_vec2",
    "cui_size",
    "cui_date",
    "cui_corners",
}
SPECIAL_PYTYPE = {
    "cui_color": ("ColorLike", "Color"),
    "cui_rect": ("RectLike", "Rect"),
    "cui_vec2": ("Vec2Like", "Vec2"),
    "cui_size": ("SizeLike", "Size"),
    "cui_date": ("DateLike", "datetime.date | None"),
    "cui_corners": ("CornersLike", "Corners"),
}

COUNT_RE = re.compile(r"^(count|n|\w+_count|channels|days|components)$")
LEN_RE = re.compile(r"^(len|\w+_len)$")
STDINT = {
    "uint8_t",
    "uint16_t",
    "uint32_t",
    "uint64_t",
    "int8_t",
    "int16_t",
    "int32_t",
    "int64_t",
    "uintptr_t",
    "intptr_t",
}
SCALAR_KINDS = {
    TK.BOOL,
    TK.INT,
    TK.UINT,
    TK.SHORT,
    TK.USHORT,
    TK.LONG,
    TK.ULONG,
    TK.LONGLONG,
    TK.ULONGLONG,
    TK.UCHAR,
    TK.SCHAR,
    TK.FLOAT,
    TK.DOUBLE,
    TK.ENUM,
}


class Unsupported(Exception):
    pass


def pyname(name: str) -> str:
    return name + "_" if keyword.iskeyword(name) or name in {"self", "print"} else name


def camel(s: str) -> str:
    s = s.removeprefix("cui_")
    return "".join(p[:1].upper() + p[1:] for p in s.split("_"))


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse() -> ci.TranslationUnit:
    args = ["-x", "c", "-std=c99", "-fparse-all-comments", f"-I{INC}"]
    try:
        rd = subprocess.check_output(
            ["clang", "-print-resource-dir"], text=True
        ).strip()
        args += ["-isystem", rd + "/include"]
    except (OSError, subprocess.CalledProcessError):
        pass
    if sys.platform == "darwin":
        sdk = subprocess.check_output(["xcrun", "--show-sdk-path"], text=True).strip()
        args += ["-isysroot", sdk]
    src = "".join(f'#include "{h}"\n' for h in HEADERS)
    tu = ci.Index.create().parse("bind.c", args=args, unsaved_files=[("bind.c", src)])
    errors = [d for d in tu.diagnostics if d.severity >= ci.Diagnostic.Error]
    if errors:
        sys.exit("\n".join(str(d) for d in errors))
    return tu


def header_of(c: ci.Cursor) -> str | None:
    f = c.location.file
    if not f:
        return None
    p = Path(f.name).resolve()
    try:
        return p.relative_to(INC.resolve()).as_posix()
    except ValueError:
        return None


def comment(c: ci.Cursor) -> str:
    raw = c.raw_comment or ""
    lines = []
    for ln in raw.splitlines():
        ln = ln.strip()
        ln = re.sub(r"^/\*+|\*+/$", "", ln).strip()
        ln = re.sub(r"^\* ?", "", ln)
        lines.append(ln.rstrip())
    text = "\n".join(lines).strip()
    return text.replace("\\", "\\\\").replace('"""', "'''")


# ---------------------------------------------------------------------------
# Cython spelling of C types
# ---------------------------------------------------------------------------


def base_name(t: ci.Type) -> str:
    """The name Cython knows a non-pointer type by."""
    if t.kind == TK.ELABORATED:
        t = t.get_named_type()
    if t.kind == TK.TYPEDEF:
        name = t.get_typedef_name()
        if (
            name == "va_list"
            or name == "__builtin_va_list"
            or name.startswith("__darwin_va")
        ):
            raise Unsupported("va_list")
        return name
    if t.kind == TK.BOOL:
        return "cbool"
    if t.kind in (TK.RECORD, TK.ENUM):
        s = t.spelling.replace("const ", "").replace("struct ", "").replace("enum ", "")
        if "unnamed" in s or "anonymous" in s:
            raise Unsupported("anonymous type")
        return s
    if t.kind == TK.VOID:
        return "void"
    if t.kind == TK.FUNCTIONPROTO:
        raise Unsupported("function type")
    if t.kind == TK.CONSTANTARRAY or t.kind == TK.INCOMPLETEARRAY:
        raise Unsupported("array")
    return t.get_canonical().spelling.replace("const ", "")


def cy(t: ci.Type) -> str:
    if t.kind == TK.POINTER:
        p = t.get_pointee()
        if p.kind == TK.FUNCTIONPROTO:
            raise Unsupported("inline function pointer")
        s = cy(p) + " *"
        if t.is_const_qualified():
            s += " const"
        return s
    s = base_name(t)
    return ("const " + s) if t.is_const_qualified() else s


def fnptr_decl(name: str, t: ci.Type) -> str:
    """`ret (*name)(args)` for a pointer-to-function type."""
    p = t.get_pointee()
    if p.kind != TK.FUNCTIONPROTO:
        p = p.get_canonical()
    args = ", ".join(cy(a) for a in p.argument_types())
    return f"{cy(p.get_result())} (*{name})({args})"


def is_fnptr(t: ci.Type) -> bool:
    return t.kind == TK.POINTER and t.get_pointee().kind == TK.FUNCTIONPROTO


def field_decl(fc: ci.Cursor) -> str:
    t = fc.type
    n = fc.spelling
    cname = n
    pn = pyname(n) if keyword.iskeyword(n) else n
    suffix = f' "{cname}"' if pn != cname else ""
    if t.kind == TK.CONSTANTARRAY:
        return f"{cy(t.element_type)} {pn}{suffix}[{t.element_count}]"
    if is_fnptr(t):
        return fnptr_decl(pn, t) + suffix
    return f"{cy(t)} {pn}{suffix}"


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


@dataclass
class Struct:
    name: str
    header: str
    fields: list[ci.Cursor]
    opaque: bool
    cursor: ci.Cursor | None = None


@dataclass
class Model:
    decls: list[tuple[str, str, str]] = field(
        default_factory=list
    )  # (header, kind, text)
    structs: dict[str, Struct] = field(default_factory=dict)
    enums: list[tuple[str, int]] = field(default_factory=list)
    enum_types: set[str] = field(default_factory=set)
    functions: list[ci.Cursor] = field(default_factory=list)
    typedef_scalars: set[str] = field(default_factory=set)
    skipped_decls: list[tuple[str, str]] = field(default_factory=list)


def build_model(tu: ci.TranslationUnit) -> Model:
    m = Model()
    declared_structs: set[str] = set()
    typedef_of_struct: dict[str, str] = {}
    cursors = [c for c in tu.cursor.get_children() if header_of(c)]
    # typedef struct X X; and typedef struct X {...} X;
    for c in cursors:
        if c.kind == CK.TYPEDEF_DECL:
            u = c.underlying_typedef_type
            if u.kind == TK.ELABORATED:
                u = u.get_named_type()
            if u.kind == TK.RECORD:
                typedef_of_struct[u.get_declaration().spelling] = c.spelling
    for c in cursors:
        h = header_of(c)
        if c.kind == CK.STRUCT_DECL:
            name = c.spelling
            if not name:
                continue
            if c.is_definition():
                m.structs[name] = Struct(
                    name,
                    h,
                    [f for f in c.get_children() if f.kind == CK.FIELD_DECL],
                    False,
                    c,
                )
                lines = []
                for f in m.structs[name].fields:
                    try:
                        lines.append("        " + field_decl(f))
                    except Unsupported as e:
                        m.skipped_decls.append((f"{name}.{f.spelling}", str(e)))
                body = "\n".join(lines) or "        pass"
                kw = "ctypedef struct" if name in typedef_of_struct else "cdef struct"
                m.decls.append((h, "struct", f"    {kw} {name}:\n{body}"))
                declared_structs.add(name)
            elif name not in declared_structs:
                m.structs.setdefault(name, Struct(name, h, [], True, c))
                kw = "ctypedef struct" if name in typedef_of_struct else "cdef struct"
                m.decls.append((h, "fwd", f"    {kw} {name}"))
                declared_structs.add(name)
        elif c.kind == CK.ENUM_DECL:
            consts = [
                (e.spelling, e.enum_value)
                for e in c.get_children()
                if e.kind == CK.ENUM_CONSTANT_DECL
            ]
            m.enums += consts
            names = "\n".join(f"        {n}" for n, _ in consts)
            if c.spelling and "unnamed" not in c.type.spelling:
                m.enum_types.add(c.spelling)
                m.decls.append((h, "enum", f"    ctypedef enum {c.spelling}:\n{names}"))
            else:
                m.decls.append((h, "enum", f"    enum:\n{names}"))
        elif c.kind == CK.TYPEDEF_DECL:
            u = c.underlying_typedef_type
            if u.kind == TK.ELABORATED:
                u = u.get_named_type()
            if u.kind in (TK.RECORD, TK.ENUM):
                continue
            if is_fnptr(u):
                try:
                    m.decls.append(
                        (h, "typedef", f"    ctypedef {fnptr_decl(c.spelling, u)}")
                    )
                except Unsupported as e:
                    m.skipped_decls.append((c.spelling, str(e)))
                continue
            try:
                m.decls.append((h, "typedef", f"    ctypedef {cy(u)} {c.spelling}"))
                if u.get_canonical().kind in SCALAR_KINDS:
                    m.typedef_scalars.add(c.spelling)
            except Unsupported as e:
                m.skipped_decls.append((c.spelling, str(e)))
        elif c.kind == CK.FUNCTION_DECL:
            if c.type.is_function_variadic():
                m.skipped_decls.append((c.spelling, "variadic"))
                continue
            try:
                args = ", ".join(
                    f"{cy(a.type)} {pyname(a.spelling) or 'arg'}"
                    for a in c.get_arguments()
                )
                m.decls.append(
                    (h, "func", f"    {cy(c.result_type)} {c.spelling}({args})")
                )
                m.functions.append(c)
            except Unsupported as e:
                m.skipped_decls.append((c.spelling, str(e)))
    return m


# ---------------------------------------------------------------------------
# Type classification for wrapping
# ---------------------------------------------------------------------------


def is_scalar(t: ci.Type) -> bool:
    return t.get_canonical().kind in SCALAR_KINDS


def py_scalar(t: ci.Type) -> str:
    k = t.get_canonical().kind
    return "bool" if k == TK.BOOL else "float" if k in (TK.FLOAT, TK.DOUBLE) else "int"


def record_name(t: ci.Type) -> str | None:
    c = t.get_canonical()
    if c.kind == TK.RECORD:
        return c.get_declaration().spelling
    return None


def is_char_ptr(t: ci.Type, const: bool) -> bool:
    if t.kind != TK.POINTER:
        return False
    p = t.get_pointee()
    return (
        p.get_canonical().kind in (TK.CHAR_S, TK.CHAR_U)
        and p.is_const_qualified() == const
    )


def is_strlist(t: ci.Type) -> bool:
    """`const char *const *`"""
    if t.kind != TK.POINTER:
        return False
    p = t.get_pointee()
    return p.is_const_qualified() and is_char_ptr(p.get_canonical(), True)


def cast_in(t: ci.Type, expr: str) -> str:
    k = t.get_canonical().kind
    if k == TK.BOOL:
        return f"bool({expr})"
    if k == TK.ENUM:
        return f"<int>{expr}"
    return expr


@dataclass
class F:
    """A struct field as Python sees it."""

    name: str  # C name
    kind: str  # scalar value str chararray strarr floatarr valarr count
    t: ci.Type
    count: str | None = None  # array kinds: the C name of the length field
    elem: str | None = None  # valarr: element struct

    @property
    def py(self) -> str:
        return pyname(self.name)

    @property
    def c(self) -> str:
        return pyname(self.name) if keyword.iskeyword(self.name) else self.name


class Types:
    """Which structs convert to Python, and how."""

    def __init__(self, m: Model) -> None:
        self.m = m
        self._fields: dict[tuple[str, bool], list[F] | None] = {}
        self.need_fill: set[str] = set()  # _fill_X / _to_X
        self.need_from: set[str] = set()  # _from_X
        self.need_arr: set[str] = set()  # _arr_X / _list_X

    def fields(self, name: str | None, strict: bool) -> list[F] | None:
        """Fields of a struct. Strict: every field converts from Python, or None.
        Lenient: the fields that convert to Python."""
        if not name or name not in self.m.structs:
            return None
        key = (name, strict)
        if key in self._fields:
            return self._fields[key]
        self._fields[key] = None  # recursion guard
        s = self.m.structs[name]
        if s.opaque or not s.fields:
            return None
        out: list[F] = []
        cfields = s.fields
        for i, f in enumerate(cfields):
            t, n = f.type, f.spelling
            later = [
                g
                for g in cfields[i + 1 :]
                if COUNT_RE.match(g.spelling) and is_scalar(g.type)
            ]
            arr = None
            if t.kind == TK.CONSTANTARRAY:
                if (
                    t.element_type.get_canonical().kind in (TK.CHAR_S, TK.CHAR_U)
                    and not strict
                ):
                    out.append(F(n, "chararray", t))
                    continue
                if strict:
                    return None
                continue
            if is_scalar(t):
                out.append(F(n, "scalar", t))
            elif is_char_ptr(t, True):
                out.append(F(n, "str", t))
            elif self.is_value(record_name(t)):
                out.append(F(n, "value", t))
            elif is_strlist(t):
                arr = "strarr"
            elif (
                t.kind == TK.POINTER
                and t.get_pointee().is_const_qualified()
                and t.get_pointee().get_canonical().kind == TK.FLOAT
            ):
                arr = "floatarr"
            elif (
                t.kind == TK.POINTER
                and t.get_pointee().is_const_qualified()
                and self.is_value(record_name(t.get_pointee()))
            ):
                arr = "valarr"
            else:
                if strict:
                    return None
                continue
            if arr:
                if not later:
                    if strict:
                        return None
                    continue
                elem = record_name(t.get_pointee()) if arr == "valarr" else None
                out.append(F(n, arr, t, count=later[0].spelling, elem=elem))
        counted = {f.count for f in out if f.count}
        for f in out:
            if f.name in counted:
                f.kind = "count"
        self._fields[key] = out
        return out

    def is_value(self, name: str | None) -> bool:
        """Every field is a scalar or a value struct."""
        if not name or name not in self.m.structs:
            return False
        if name in SPECIAL_VALUES:
            return True
        s = self.m.structs[name]
        if s.opaque or not s.fields:
            return False
        return all(
            f.type.kind != TK.CONSTANTARRAY
            and (
                is_scalar(f.type)
                or (record_name(f.type) != name and self.is_value(record_name(f.type)))
            )
            for f in s.fields
        )

    def is_record(self, name: str | None) -> bool:
        return self.fields(name, True) is not None

    def is_result(self, name: str | None) -> bool:
        fs = self.fields(name, False)
        return bool(fs)

    def py_fields(self, name: str) -> list[F]:
        return [f for f in (self.fields(name, False) or []) if f.kind != "count"]

    # names of generated helpers; asking for one records that it is needed
    def fill(self, name: str) -> str:
        if name not in SPECIAL_VALUES:
            self.need_fill.add(name)
            for f in self.fields(name, True) or []:
                if f.kind == "value":
                    self.fill(record_name(f.t))
                elif f.kind == "valarr":
                    self.fill(f.elem)
        return f"_fill_{name}"

    def to(self, name: str) -> str:
        self.fill(name)
        return f"_to_{name}"

    def frm(self, name: str) -> str:
        if name not in SPECIAL_VALUES:
            self.need_from.add(name)
            for f in self.fields(name, False) or []:
                if f.kind == "value":
                    self.frm(record_name(f.t))
                elif f.kind == "valarr":
                    self.frm(f.elem)
        return f"_from_{name}"

    def arr(self, name: str, out: bool) -> str:
        self.need_arr.add(name)
        self.fill(name)
        if out:
            self.frm(name)
        return f"_arr_{name}"

    def pytype_in(self, t: ci.Type) -> str:
        if is_scalar(t):
            return py_scalar(t)
        n = record_name(t)
        if n in SPECIAL_PYTYPE:
            return SPECIAL_PYTYPE[n][0]
        return f"{camel(n)} | Collection[Any]"

    def pytype_out(self, t: ci.Type) -> str:
        if is_scalar(t):
            return py_scalar(t)
        n = record_name(t)
        if n in SPECIAL_PYTYPE:
            return SPECIAL_PYTYPE[n][1]
        return camel(n)


# ---------------------------------------------------------------------------
# Parameter plans
# ---------------------------------------------------------------------------


@dataclass
class P:
    """How one C parameter maps to Python."""

    kind: str
    name: str
    ctype: str = ""
    t: ci.Type | None = None
    count: str | None = None  # array kinds: the C name of their length param
    arrays: list[str] = field(
        default_factory=list
    )  # count params: the arrays sharing it
    elem: str = ""  # inout_array: element C type
    rec: str | None = None  # struct name
    opts: list[tuple[str, str, str]] = field(
        default_factory=list
    )  # (cfield, pyname, kind)
    of: str | None = None  # strlen params: the string they measure

    @property
    def v(self) -> str:
        return "c_" + self.name

    @property
    def py(self) -> str:
        return pyname(self.name)


ARRAY_KINDS = ("strlist", "floatlist", "inout_array", "recarray", "recarray_inout")


class Planner:
    def __init__(self, types: Types) -> None:
        self.ty = types

    def opts_fields(self, rec: str) -> tuple[list[tuple[str, str, str]], list[str]]:
        out, skipped = [], []
        for f in self.ty.m.structs[rec].fields:
            n, t = f.spelling, f.type
            if n == "_":
                continue
            if t.kind == TK.CONSTANTARRAY:
                skipped.append(n)
            elif is_scalar(t):
                out.append((n, pyname(n), "scalar"))
            elif is_char_ptr(t, True):
                out.append((n, pyname(n), "str"))
            elif self.ty.is_value(record_name(t)):
                out.append((n, pyname(n), "value"))
            else:
                skipped.append(n)
        return out, skipped

    def plan(self, fn: ci.Cursor) -> tuple[list[P], list[str]]:
        """Plans for every parameter, and the opts fields left out."""
        args = list(fn.get_arguments())
        plans: list[P | None] = [None] * len(args)
        skipped_opts: list[str] = []
        names = [a.spelling for a in args]
        fname = fn.spelling

        def take_count(i: int, n: str, cnt: str | None = None) -> str:
            if cnt is None:
                cnt = next(
                    (
                        names[j]
                        for j in range(i + 1, len(args))
                        if COUNT_RE.match(names[j]) and is_scalar(args[j].type)
                    ),
                    None,
                )
            if cnt is None:
                raise Unsupported(f"array {n} without a count parameter")
            j = names.index(cnt)
            if plans[j] is None:
                plans[j] = P("count", cnt, cy(args[j].type))
            if plans[j].kind != "count":
                raise Unsupported(f"count {cnt} is also something else")
            plans[j].arrays.append(n)
            return cnt

        for i, a in enumerate(args):
            t, n = a.type, a.spelling
            if not n:
                raise Unsupported("unnamed parameter")
            if plans[i] is not None:
                continue
            if i == 0 and cy(t) == "cui_ctx *":
                plans[i] = P("ui", n)
                continue
            pointee = t.get_pointee() if t.kind == TK.POINTER else None
            rec_p = record_name(pointee) if pointee else None
            if pointee and n == "opts" and pointee.is_const_qualified() and rec_p:
                fields, sk = self.opts_fields(rec_p)
                skipped_opts += sk
                plans[i] = P("opts", n, rec_p, rec=rec_p, opts=fields)
                continue
            if is_char_ptr(t, True):
                plans[i] = P("str", n, "const char *")
                if (
                    i + 1 < len(args)
                    and LEN_RE.match(names[i + 1])
                    and is_scalar(args[i + 1].type)
                ):
                    plans[i + 1] = P("strlen", names[i + 1], cy(args[i + 1].type), of=n)
                continue
            if is_char_ptr(t, False):
                if (
                    i + 1 < len(args)
                    and args[i + 1].type.get_canonical().spelling
                    in ("unsigned long", "unsigned long long", "unsigned int")
                    and "cap" in names[i + 1]
                ):
                    plans[i] = P("buf", n)
                    plans[i + 1] = P("cap", names[i + 1], cy(args[i + 1].type))
                    continue
                raise Unsupported(f"char *{n} without a size_t capacity")
            if pointee and (fname, n) in INOUT_ARRAYS:
                if not is_scalar(pointee):
                    raise Unsupported(f"array {n}")
                cnt = take_count(i, n, INOUT_ARRAYS[(fname, n)])
                plans[i] = P(
                    "inout_array",
                    n,
                    elem=cy(pointee).replace("const ", ""),
                    count=cnt,
                    t=pointee,
                )
                continue
            if pointee:
                const = pointee.is_const_qualified()
                nxt = args[i + 1] if i + 1 < len(args) else None
                elem_ok = is_scalar(pointee) or self.ty.is_record(rec_p)
                if is_strlist(t):
                    plans[i] = P("strlist", n, count=take_count(i, n))
                    continue
                if const and pointee.get_canonical().kind == TK.FLOAT:
                    plans[i] = P("floatlist", n, count=take_count(i, n))
                    continue
                # T *items, int *count, int capacity: an array the component may grow
                if (
                    not const
                    and nxt
                    and nxt.type.kind == TK.POINTER
                    and is_scalar(nxt.type.get_pointee())
                    and COUNT_RE.match(nxt.spelling)
                    and i + 2 < len(args)
                    and names[i + 2] in ("capacity", "cap")
                    and is_scalar(args[i + 2].type)
                ):
                    if not elem_ok:
                        raise Unsupported(f"growable array {n} of unsupported elements")
                    plans[i] = P(
                        "grow",
                        n,
                        cy(pointee).replace("const ", ""),
                        rec=rec_p,
                        t=pointee,
                        count=names[i + 2],
                    )
                    if rec_p in SPECIAL_VALUES:
                        raise Unsupported(f"growable array {n} of {rec_p}")
                    plans[i + 1] = P("growcount", nxt.spelling, "int", of=n)
                    plans[i + 2] = P(
                        "scalar", names[i + 2], cy(args[i + 2].type), t=args[i + 2].type
                    )
                    continue
                # Output arrays sized by the caller (`cap`) need a buffer API, not a list.
                if (
                    not const
                    and not is_scalar(pointee)
                    and any(
                        nm in ("cap", "capacity") and is_scalar(a.type)
                        for nm, a in zip(names, args)
                    )
                ):
                    raise Unsupported(f"output array {n} with a caller capacity")
                followed_by_count = (
                    nxt is not None
                    and COUNT_RE.match(nxt.spelling)
                    and is_scalar(nxt.type)
                )
                if (
                    not is_scalar(pointee)
                    and followed_by_count
                    and self.ty.is_record(rec_p)
                ):
                    kind = "recarray" if const else "recarray_inout"
                    plans[i] = P(kind, n, rec=rec_p, count=take_count(i, n), t=pointee)
                    continue
                if not const and is_scalar(pointee):
                    if followed_by_count and (fname, n) not in SCALAR_PTRS:
                        raise Unsupported(
                            f"{n} may be an array; list it in INOUT_ARRAYS or OUT_ONLY"
                        )
                    plans[i] = P(
                        "out" if (fname, n) in OUT_ONLY else "inout",
                        n,
                        cy(pointee),
                        t=pointee,
                    )
                    continue
                if not const and self.ty.is_value(rec_p):
                    out = (fname, n) in OUT_ONLY or fname.endswith("_end")
                    plans[i] = P(
                        "out_value" if out else "inout_value",
                        n,
                        rec_p,
                        rec=rec_p,
                        t=pointee,
                    )
                    continue
                if self.ty.is_record(rec_p):
                    plans[i] = P(
                        "record" if const else "record_inout", n, rec=rec_p, t=pointee
                    )
                    continue
                raise Unsupported(f"pointer parameter {cy(t)} {n}")
            if is_scalar(t):
                plans[i] = P("scalar", n, cy(t), t=t)
                continue
            if self.ty.is_value(record_name(t)):
                r = record_name(t)
                plans[i] = P("value", n, r, rec=r, t=t)
                continue
            raise Unsupported(f"parameter {cy(t)} {n}")
        return [p for p in plans if p is not None], skipped_opts


# ---------------------------------------------------------------------------
# Code generation
# ---------------------------------------------------------------------------


STORAGE = {
    "str": "const char *",
    "strlist": "_StrArray",
    "floatlist": "_FloatArray",
    "growcount": "int",
    "inout_array": "_ScalarArray",
    "recarray": "_Mem",
    "recarray_inout": "_Mem",
    "record": "_Mem",
    "record_inout": "_Mem",
}


class Gen:
    def __init__(self, m: Model) -> None:
        self.m = m
        self.ty = Types(m)
        self.pl = Planner(self.ty)
        self.methods: list[str] = []
        self.funcs: list[str] = []
        self.scopes: list[str] = []
        self.stub_methods: list[str] = []
        self.stub_funcs: list[str] = []
        self.stub_scopes: list[str] = []
        self.wrapped: list[tuple[str, str]] = []
        self.skipped: list[tuple[str, str]] = []
        self.opt_gaps: dict[str, list[str]] = {}

    def ftype(self, rec: str, cf: str) -> ci.Type:
        return next(f.type for f in self.m.structs[rec].fields if f.spelling == cf)

    def result(self, fn: ci.Cursor) -> tuple[str, str, str] | None:
        """(C type of `r`, Python conversion of `r`, stub type), or None for void."""
        t = fn.result_type
        if t.kind == TK.VOID:
            return None
        if is_scalar(t):
            return cy(t), "r", py_scalar(t)
        if is_char_ptr(t, True):
            return "const char *", "_str_or_none(r)", "str | None"
        r = record_name(t)
        if self.ty.is_value(r) or self.ty.is_result(r):
            return r, f"{self.ty.frm(r)}(r)", self.ty.pytype_out(t)
        raise Unsupported(f"return type {cy(t)}")

    @staticmethod
    def guard(fname: str) -> str:
        if fname.startswith(PAINT_PREFIXES):
            return "self._need_paint()"
        if fname in ANYTIME or fname.startswith(ANYTIME_PREFIXES):
            return "self._need_alive()"
        return "self._need_frame()"

    def sig(self, plans: list[P]) -> tuple[list[str], list[str]]:
        """(Cython signature parts, stub signature parts)."""
        pos, kw, spos, skw = [], [], [], []
        for p in plans:
            pn = p.py
            if p.kind == "str":
                pos.append(f"str {pn} not None")
                spos.append(f"{pn}: str")
            elif p.kind in ("scalar", "inout"):
                pos.append(pn)
                spos.append(f"{pn}: {py_scalar(p.t)}")
            elif p.kind in ("value", "inout_value"):
                pos.append(pn)
                spos.append(f"{pn}: {self.ty.pytype_in(p.t)}")
            elif p.kind == "buf":
                pos.append(f"TextBuffer {pn} not None")
                spos.append(f"{pn}: TextBuffer")
            elif p.kind == "strlist":
                pos.append(pn)
                spos.append(f"{pn}: Sequence[str]")
            elif p.kind == "floatlist":
                pos.append(pn)
                spos.append(f"{pn}: Sequence[float]")
            elif p.kind == "inout_array":
                pos.append(pn)
                spos.append(f"{pn}: Sequence[{py_scalar(p.t)}]")
            elif p.kind in ("recarray", "recarray_inout", "grow"):
                pos.append(pn)
                spos.append(f"{pn}: Sequence[{self.ty.pytype_in(p.t)}]")
            elif p.kind in ("record", "record_inout"):
                pos.append(pn)
                spos.append(f"{pn}: {self.ty.pytype_in(p.t)}")
            elif p.kind == "opts":
                taken = {q.py for q in plans}
                fixed = []
                for cf, pf, k in p.opts:
                    if pf in taken:
                        pf = pf + "_"
                    fixed.append((cf, pf, k))
                    ft = self.ftype(p.rec, cf)
                    ann = (
                        "str"
                        if k == "str"
                        else (self.ty.pytype_in(ft) if k == "value" else py_scalar(ft))
                    )
                    kw.append(f"{pf}=None")
                    skw.append(f"{pf}: {ann} | None = None")
                p.opts = fixed
        parts = pos + (["*"] + kw if kw else [])
        sparts = spos + (["*"] + skw if skw else [])
        return parts, sparts

    def decls(self, plans: list[P]) -> list[tuple[str, str]]:
        """(C type, storage name) for every parameter that needs storage."""
        out = []
        for p in plans:
            if p.kind in ("ui", "cap"):
                continue
            if p.kind == "buf":
                out.append(("TextBuffer", "b_" + p.name))
            elif p.kind == "grow":
                out.append(("_Mem" if p.rec else "_ScalarArray", p.v))
            elif p.kind in STORAGE:
                out.append((STORAGE[p.kind], p.v))
            elif p.kind in ("value", "inout_value", "out_value", "opts"):
                out.append((p.rec, p.v))
            else:
                out.append((p.ctype, p.v))
        return out

    def prep(self, plans: list[P], T: str, keep: str) -> list[str]:
        """Lines that convert Python arguments into storage `T + name`."""
        out = []
        for p in plans:
            pn, v = p.py, T + p.v
            if p.kind == "str":
                out.append(f"{v} = _cstr({keep}, {pn})")
            elif p.kind == "strlen":
                out.append(f"{v} = <{p.ctype}>_cstr_len({keep}, {pyname(p.of)})")
            elif p.kind in ("scalar", "inout"):
                out.append(f"{v} = <{p.ctype}>{cast_in(p.t, pn)}")
            elif p.kind == "out":
                out.append(f"{v} = 0")
            elif p.kind in ("value", "inout_value"):
                out.append(f"{v} = {self.ty.to(p.rec)}({pn})")
            elif p.kind == "out_value":
                out.append(f"memset(&{v}, 0, sizeof({v}))")
            elif p.kind == "buf":
                out.append(f"{T}b_{p.name} = {pn}")
                out.append(f"{keep}.append({pn})")
            elif p.kind == "strlist":
                out += [f"{v} = _StrArray({pn})", f"{keep}.append({v})"]
            elif p.kind == "floatlist":
                out += [f"{v} = _FloatArray({pn})", f"{keep}.append({v})"]
            elif p.kind == "inout_array":
                out += [
                    f'{v} = _ScalarArray({pn}, "{self.array_code(p.t)}")',
                    f"{keep}.append({v})",
                ]
            elif p.kind in ("recarray", "recarray_inout"):
                out.append(
                    f"{v} = {self.ty.arr(p.rec, p.kind == 'recarray_inout')}({pn}, {keep})"
                )
            elif p.kind in ("record", "record_inout"):
                out.append(
                    f"{v} = {self.ty.arr(p.rec, p.kind == 'record_inout')}(({pn},), {keep})"
                )
            elif p.kind == "grow":
                cap = pyname(p.count)
                out.append(
                    f'if len({pn}) > {cap}: raise ValueError("{p.name} has more than {p.count} items")'
                )
                if p.rec:
                    out.append(
                        f"{v} = {self.ty.arr(p.rec, True)}(list({pn}) + [{{}}] * ({cap} - len({pn})), {keep})"
                    )
                else:
                    out.append(
                        f'{v} = _ScalarArray(list({pn}) + [0] * ({cap} - len({pn})), "{self.array_code(p.t)}")'
                    )
                    out.append(f"{keep}.append({v})")
            elif p.kind == "growcount":
                out.append(f"{v} = <int>len({pyname(p.of)})")
            elif p.kind == "opts":
                out.append(f"memset(&{v}, 0, sizeof({v}))")
                for cf, pf, k in p.opts:
                    ft = self.ftype(p.rec, cf)
                    cfa = pyname(cf) if keyword.iskeyword(cf) else cf
                    if k == "str":
                        conv = f"_cstr({keep}, {pf})"
                    elif k == "value":
                        conv = f"{self.ty.to(record_name(ft))}({pf})"
                    else:
                        conv = f"<{cy(ft)}>{cast_in(ft, pf)}"
                    out.append(f"if {pf} is not None: {v}.{cfa} = {conv}")
        for p in plans:  # counts last: they read the arrays
            if p.kind == "count":
                arrs = [q for q in plans if q.name in p.arrays]
                first = T + arrs[0].v
                out.append(f"{T}{p.v} = <{p.ctype}>{first}.n")
                for q in arrs[1:]:
                    out.append(
                        f"if {T}{q.v}.n != {first}.n: raise ValueError("
                        f'"{q.name} and {arrs[0].name} must have the same length")'
                    )
        return out

    @staticmethod
    def array_code(t: ci.Type) -> str:
        return {TK.BOOL: "?", TK.INT: "i", TK.UINT: "I", TK.FLOAT: "f", TK.DOUBLE: "d"}[
            t.get_canonical().kind
        ]

    def call_args(self, plans: list[P], T: str) -> str:
        out = []
        for p in plans:
            v = T + p.v
            if p.kind == "ui":
                out.append("self.ctx.ui" if T else "self.ui")
            elif p.kind in ("str", "strlen", "scalar", "value", "count"):
                out.append(v)
            elif p.kind in (
                "inout",
                "out",
                "inout_value",
                "out_value",
                "opts",
                "growcount",
            ):
                out.append(f"&{v}")
            elif p.kind == "grow":
                out.append(f"<{p.rec or p.ctype} *>{v}.ptr")
            elif p.kind == "buf":
                out.append(f"{T}b_{p.name}.data")
            elif p.kind == "cap":
                buf = next(q for q in plans if q.kind == "buf")
                out.append(f"{T}b_{buf.name}.cap")
            elif p.kind in ("strlist", "floatlist"):
                out.append(f"{v}.ptr")
            elif p.kind == "inout_array":
                out.append(f"<{p.elem} *>{v}.ptr")
            elif p.kind in ("recarray", "record", "recarray_inout", "record_inout"):
                out.append(f"<{p.rec} *>{v}.ptr")
        return ", ".join(out)

    def outputs(self, plans: list[P], T: str) -> list[tuple[str, str, str]]:
        """(name, Python expression, stub type) of every output parameter."""
        out = []
        for p in plans:
            v = T + p.v
            if p.kind in ("inout", "out"):
                out.append((p.name, v, py_scalar(p.t)))
            elif p.kind in ("inout_value", "out_value"):
                out.append(
                    (p.name, f"{self.ty.frm(p.rec)}({v})", self.ty.pytype_out(p.t))
                )
            elif p.kind == "inout_array":
                out.append((p.name, f"{v}.tolist()", f"list[{py_scalar(p.t)}]"))
            elif p.kind == "recarray_inout":
                out.append(
                    (p.name, f"_list_{p.rec}({v})", f"list[{self.ty.pytype_out(p.t)}]")
                )
            elif p.kind == "record_inout":
                out.append((p.name, f"_list_{p.rec}({v})[0]", self.ty.pytype_out(p.t)))
            elif p.kind == "grow":
                cnt = T + next(q for q in plans if q.kind == "growcount").v
                lst = f"_list_{p.rec}({v})" if p.rec else f"{v}.tolist()"
                out.append(
                    (
                        p.name,
                        f"{lst}[:_clamp_count({cnt}, {v}.n)]",
                        f"list[{self.ty.pytype_out(p.t)}]",
                    )
                )
        return out

    @staticmethod
    def method_name(fname: str) -> str:
        n = fname[4:]
        return n.removesuffix("_ex")

    @staticmethod
    def stub(name: str, parts: list[str], ret: str, doc: str, ind: str) -> str:
        first = doc.split("\n\n")[0].replace("\n", " ").strip() if doc else ""
        d = f'\n{ind}    """{first}"""' if first else ""
        return f"{ind}def {name}({', '.join(parts)}) -> {ret}:{d if d else ' ...'}"

    # -- methods and functions --------------------------------------------------

    def emit_function(self, fn: ci.Cursor, scope_parts: set[str]) -> None:
        fname = fn.spelling
        if fname in MANUAL or fname in EXCLUDED or fname in scope_parts:
            return
        try:
            plans, gaps = self.pl.plan(fn)
            res = self.result(fn)
        except Unsupported as e:
            self.skipped.append((fname, str(e)))
            return
        if gaps:
            self.opt_gaps[fname] = gaps
        is_method = bool(plans) and plans[0].kind == "ui"
        name = self.method_name(fname)
        parts, sparts = self.sig(plans[1:] if is_method else plans)
        doc = comment(fn)
        keep = "self._keep" if is_method else "keep"
        body = [self.guard(fname)] if is_method else ["cdef list keep = []"]
        body += [f"cdef {ty} {nm}" for ty, nm in self.decls(plans)]
        body += self.prep(plans, "", keep)
        call = f"{fname}({self.call_args(plans, '')})"
        outs = self.outputs(plans, "")
        rets, stypes = [], []
        if res:
            body.append(f"cdef {res[0]} r = {call}")
            rets.append(res[1])
            stypes.append(res[2])
        else:
            body.append(call)
        rets += [o[1] for o in outs]
        stypes += [o[2] for o in outs]
        if rets:
            body.append(
                "return " + (rets[0] if len(rets) == 1 else "(" + ", ".join(rets) + ")")
            )
        stype = (
            "None"
            if not stypes
            else stypes[0]
            if len(stypes) == 1
            else f"tuple[{', '.join(stypes)}]"
        )
        ind = "    " if is_method else ""
        lines = [
            f"{ind}def {name}({', '.join((['self'] if is_method else []) + parts)}):"
        ]
        if doc:
            lines.append(f'{ind}    """{doc}"""')
        lines += [f"{ind}    {b}" for b in body]
        if is_method:
            self.methods.append("\n".join(lines))
            self.stub_methods.append(
                self.stub(name, ["self"] + sparts, stype, doc, "    ")
            )
        else:
            self.funcs.append("\n".join(lines))
            self.stub_funcs.append(self.stub(name, sparts, stype, doc, ""))
        self.wrapped.append((fname, ("Context." if is_method else "cui.") + name))

    # -- scopes -------------------------------------------------------------------

    def emit_scope(
        self, name: str, begin: ci.Cursor, end: ci.Cursor, only_if: bool
    ) -> None:
        try:
            bplans, gaps = self.pl.plan(begin)
            eplans, _ = self.pl.plan(end)
            bres = self.result(begin)
            eres = self.result(end)
            for p in eplans[1:]:
                if p.kind not in ("out", "out_value"):
                    raise Unsupported(f"{end.spelling} takes {p.name}")
        except Unsupported as e:
            self.skipped.append((f"{begin.spelling} / {end.spelling}", str(e)))
            return
        if gaps:
            self.opt_gaps[begin.spelling] = gaps
        cls = f"{camel(name)}Scope"
        parts, sparts = self.sig(bplans[1:])
        attrs = [
            "    cdef _ContextBase ctx",
            "    cdef bint entered",
            "    cdef bint began",
            "    cdef readonly object value",
            "    cdef readonly object result",
        ]
        attrs += [f"    cdef {ty} {nm}" for ty, nm in self.decls(bplans + eplans[1:])]
        doc = comment(begin)
        # CUI may hold pointers into the scope's storage until the frame is painted.
        fbody = [
            "self._need_frame()",
            f"cdef {cls} s = {cls}.__new__({cls})",
            "s.ctx = self",
            "self._keep.append(s)",
        ]
        fbody += self.prep(bplans, "s.", "self._keep")
        fbody += self.prep(eplans[1:], "s.", "self._keep")
        fbody.append("return s")
        m = [f"    def {name}({', '.join(['self'] + parts)}):"]
        if doc:
            m.append(f'        """{doc}"""')
        m += ["        " + b for b in fbody]
        self.methods.append("\n".join(m))
        self.stub_methods.append(self.stub(name, ["self"] + sparts, cls, doc, "    "))
        bcall = f"{begin.spelling}({self.call_args(bplans, 'self.')})"
        ecall = f"{end.spelling}({self.call_args(eplans, 'self.')})"
        c = [
            f"cdef class {cls}:",
            f'    """Scope for `{begin.spelling}` ... `{end.spelling}`."""',
        ] + attrs
        c += [
            "    def __enter__(self):",
            '        if self.entered: raise RuntimeError("a scope can be entered once")',
            "        self.ctx._need_frame()",
            "        self.entered = True",
        ]
        if bres:
            c += [
                f"        cdef {bres[0]} r = {bcall}",
                f"        self.value = {bres[1]}",
                f"        self.began = {'<bint>r' if only_if else 'True'}",
            ]
        else:
            c += [f"        {bcall}", "        self.began = True"]
        c += [
            "        if self.began: self.ctx._open_scopes += 1",
            "        return self",
            "    def __exit__(self, *exc):",
            "        if not self.began: return False",
            "        self.began = False",
            "        self.ctx._open_scopes -= 1",
        ]
        if eres:
            c += [
                f"        cdef {eres[0]} r = {ecall}",
                f"        self.result = {eres[1]}",
            ]
        else:
            c.append(f"        {ecall}")
        c += [
            "        return False",
            "    def __bool__(self):",
            "        return bool(self.value)" if bres else "        return True",
        ]
        sprops = []
        for on, expr, st in self.outputs(bplans + eplans[1:], "self."):
            c += [
                "    @property",
                f"    def {pyname(on)}(self):",
                f"        return {expr}",
            ]
            sprops.append(f"    @property\n    def {pyname(on)}(self) -> {st}: ...")
        self.scopes.append("\n".join(c))
        st = [f"class {cls}:"]
        st.append(f"    value: {bres[2] if bres else 'None'}")
        st.append(f"    result: {eres[2] + ' | None' if eres else 'None'}")
        st += [
            "    def __enter__(self) -> Self: ...",
            "    def __exit__(self, *exc: object) -> bool: ...",
            "    def __bool__(self) -> bool: ...",
        ] + sprops
        self.stub_scopes.append("\n".join(st))
        self.wrapped.append(
            (f"{begin.spelling} / {end.spelling}", f"with Context.{name}(...)")
        )

    # -- struct converters -----------------------------------------------------

    def fill_code(self, name: str) -> str:
        fs = self.ty.fields(name, True)
        pys = self.ty.py_fields(name)
        names = tuple(f.py for f in pys)
        locals_ = []
        body = []
        for i, f in enumerate(pys):
            x = f"t[{i}]"
            if f.kind == "scalar":
                body.append(
                    f"    if {x} is not None: v.{f.c} = <{cy(f.t)}>{cast_in(f.t, x)}"
                )
            elif f.kind == "str":
                body.append(f"    if {x} is not None: v.{f.c} = _cstr(keep, {x})")
            elif f.kind == "value":
                body.append(
                    f"    if {x} is not None: v.{f.c} = {self.ty.to(record_name(f.t))}({x})"
                )
            elif f.kind in ("strarr", "floatarr", "valarr"):
                a = f"a{i}"
                cnt = next(g for g in fs if g.name == f.count)
                if f.kind == "strarr":
                    locals_.append(f"    cdef _StrArray {a}")
                    mk, ptr = f"_StrArray({x})", f"{a}.ptr"
                elif f.kind == "floatarr":
                    locals_.append(f"    cdef _FloatArray {a}")
                    mk, ptr = f"_FloatArray({x})", f"{a}.ptr"
                else:
                    locals_.append(f"    cdef _Mem {a}")
                    mk, ptr = (
                        f"{self.ty.arr(f.elem, False)}({x}, keep)",
                        f"<const {f.elem} *>{a}.ptr",
                    )
                body += [
                    f"    if {x} is not None:",
                    f"        {a} = {mk}",
                    f"        keep.append({a})"
                    if f.kind != "valarr"
                    else "        pass",
                    f"        if v.{cnt.c} and v.{cnt.c} != {a}.n:",
                    f'            raise ValueError("{name}.{f.name} and the other arrays need the same length")',
                    f"        v.{f.c} = {ptr}",
                    f"        v.{cnt.c} = <{cy(cnt.t)}>{a}.n",
                ]
        head = [
            f"cdef int _fill_{name}({name} *v, object o, list keep) except -1:"
        ] + locals_
        head.append(f'    t = _record_tuple(o, {names!r}, "{camel(name)}")')
        return "\n".join(head + body + ["    return 0"])

    def to_code(self, name: str) -> str:
        return (
            f"cdef {name} _to_{name}(object o) except *:\n"
            f"    cdef {name} v\n"
            f"    memset(&v, 0, sizeof(v))\n"
            f"    _fill_{name}(&v, o, None)\n"
            f"    return v"
        )

    def from_code(self, name: str) -> str:
        lines = [f"cdef object _from_{name}({name} v):", f"    return {camel(name)}("]
        fs = self.ty.fields(name, False)
        for f in self.ty.py_fields(name):
            if f.kind == "scalar":
                e = f"v.{f.c}"
            elif f.kind in ("str", "chararray"):
                e = f"_str_or_none(v.{f.c})"
            elif f.kind == "value":
                e = f"{self.ty.frm(record_name(f.t))}(v.{f.c})"
            else:
                cnt = next(g for g in fs if g.name == f.count)
                if f.kind == "strarr":
                    item = f"_str_or_none(v.{f.c}[i])"
                elif f.kind == "floatarr":
                    item = f"v.{f.c}[i]"
                else:
                    item = f"{self.ty.frm(f.elem)}(v.{f.c}[i])"
                e = f"([{item} for i in range(v.{cnt.c})] if v.{f.c} != NULL else None)"
            lines.append(f"        {e},")
        lines.append("    )")
        return "\n".join(lines)

    def arr_code(self, name: str) -> str:
        if name in SPECIAL_VALUES:
            fill = f"        a[i] = _to_{name}(seq[i])"
        else:
            fill = f"        _fill_{name}(&a[i], seq[i], keep)"
        code = [
            f"cdef _Mem _arr_{name}(object seq, list keep):",
            "    seq = list(seq)",
            f"    cdef _Mem m = _Mem(len(seq), sizeof({name}))",
            "    keep.append(m)",
            f"    cdef {name} *a = <{name} *>m.ptr",
            "    cdef Py_ssize_t i",
            "    for i in range(m.n):",
            fill,
            "    return m",
        ]
        if name in self.ty.need_from or name in SPECIAL_VALUES:
            code += [
                "",
                f"cdef list _list_{name}(_Mem m):",
                f"    cdef {name} *a = <{name} *>m.ptr",
                f"    return [{'_from_' + name}(a[i]) for i in range(m.n)]",
            ]
        return "\n".join(code)

    def converters(self) -> tuple[list[str], list[str], list[str]]:
        """(code, namedtuple definitions, stubs) for every struct helper used."""
        # asking for helpers can add more; settle the sets first
        while True:
            before = (
                len(self.ty.need_fill),
                len(self.ty.need_from),
                len(self.ty.need_arr),
            )
            for n in list(self.ty.need_fill):
                self.ty.fill(n)
            for n in list(self.ty.need_from):
                self.ty.frm(n)
            for n in list(self.ty.need_arr):
                self.ty.arr(n, False)
            if (
                len(self.ty.need_fill),
                len(self.ty.need_from),
                len(self.ty.need_arr),
            ) == before:
                break
        code = []
        for n in sorted(self.ty.need_fill):
            code.append(self.fill_code(n))
            if self.ty.is_value(n):
                code.append(self.to_code(n))
        for n in sorted(self.ty.need_from):
            code.append(self.from_code(n))
        for n in sorted(self.ty.need_arr):
            code.append(self.arr_code(n))
        tuples, stubs = [], []
        for n in sorted((self.ty.need_fill | self.ty.need_from) - SPECIAL_VALUES):
            pys = self.ty.py_fields(n)
            names = [f.py for f in pys]
            tuples.append(f'{camel(n)} = _record("{camel(n)}", {names!r})')
            st = [f"class {camel(n)}(NamedTuple):"]
            for f in pys:
                if f.kind in ("str", "chararray"):
                    ann = "str | None"
                elif f.kind == "scalar":
                    ann = py_scalar(f.t)
                elif f.kind == "value":
                    ann = self.ty.pytype_out(f.t)
                elif f.kind == "strarr":
                    ann = "Sequence[str] | None"
                elif f.kind == "floatarr":
                    ann = "Sequence[float] | None"
                else:
                    ann = f"Sequence[{SPECIAL_PYTYPE.get(f.elem, (camel(f.elem),))[0]}] | None"
                clash = (
                    "  # type: ignore[assignment]" if f.py in ("count", "index") else ""
                )
                st.append(f"    {f.py}: {ann} = ...{clash}")
            if not pys:
                st.append("    pass")
            stubs.append("\n".join(st))
        return code, tuples, stubs

    # -- constants --------------------------------------------------------------

    def constants(self) -> tuple[list[str], list[str]]:
        code, stubs = [], []
        seen = set()
        for n, v in self.m.enums:
            if n.startswith("CUI_") and not n.startswith("CUI__"):
                pn = n[4:]
                if pn in seen:
                    continue
                seen.add(pn)
                code.append(f"{pn} = {v}")
                stubs.append(f"{pn}: int")
        hdr = (INC / "cui" / "cui.h").read_text()
        enums = dict(self.m.enums)
        for mm in re.finditer(
            r"^#define CUI_COLOR_(\w+)\s+CUI_TOKEN_COLOR\((CUI_TOKEN_\w+)\)",
            hdr,
            re.MULTILINE,
        ):
            code.append(
                f"COLOR_{mm.group(1)} = Color({enums[mm.group(2)]}, 0xC5, 0x1D, 0)"
            )
            stubs.append(f"COLOR_{mm.group(1)}: Color")
        for mm in re.finditer(
            r"^#define CUI_(VERSION_\w+|REGEX_GROUPS|FLAG_ENVS)\s+(\d+)",
            hdr,
            re.MULTILINE,
        ):
            code.append(f"{mm.group(1)} = {mm.group(2)}")
            stubs.append(f"{mm.group(1)}: int")
        icons = (INC / "cui" / "cui_icons.h").read_text()
        for mm in re.finditer(
            r'^#define CUI_(ICON_\w+)\s+"((?:\\x[0-9a-fA-F]{2})+)"', icons, re.MULTILINE
        ):
            raw = bytes(
                int(h, 16) for h in re.findall(r"\\x([0-9a-fA-F]{2})", mm.group(2))
            )
            code.append(f"{mm.group(1)} = {raw.decode('utf-8')!r}")
            stubs.append(f"{mm.group(1)}: str")
        return code, stubs


def scope_table(m: Model) -> dict[str, tuple[str, str, bool]]:
    hdr = (INC / "cui" / "cui.h").read_text()
    table = {}
    pat = re.compile(
        r"^#define cui_(\w+)\(([^)]*)\)\s+CUI__SCOPE(_IF)?\((cui_\w+)\(.*,\s*(cui_\w+)\(ui\)\)\s*$",
        re.MULTILINE,
    )
    for mm in pat.finditer(hdr):
        table[mm.group(1)] = (mm.group(4), mm.group(5), bool(mm.group(3)))
    table.update(EXTRA_SCOPES)
    return table


PXD_HEAD = """# Generated by tools/gen_bindings.py from thirdparty/cui/include. Do not edit.
from libc.stdint cimport uint8_t, uint16_t, uint32_t, uint64_t, int8_t, int16_t, int32_t, int64_t, uintptr_t, intptr_t

cdef extern from "<stdbool.h>":
    # C99 bool. Cython's bint is a C int, which differs in size behind a pointer.
    ctypedef bint cbool "bool"
"""


def main() -> None:
    tu = parse()
    m = build_model(tu)
    g = Gen(m)
    fns = {f.spelling: f for f in m.functions}

    # pxd
    pxd = [PXD_HEAD]
    for h in HEADERS:
        block = [t for hh, _, t in m.decls if hh == h]
        if block:
            pxd.append(f'\ncdef extern from "{h}" nogil:\n' + "\n".join(block) + "\n")
    (OUT / "_cui.pxd").write_text("".join(pxd))

    scopes = scope_table(m)
    parts: set[str] = set()
    for name, (b, e, only_if) in sorted(scopes.items()):
        parts |= {b, e}
        if b not in fns or e not in fns:
            g.skipped.append((f"{b} / {e}", "not declared"))
            continue
        g.emit_scope(name, fns[b], fns[e], only_if)
    for f in m.functions:
        g.emit_function(f, parts)

    # names must be unique on Context
    names = [w[1] for w in g.wrapped]
    dup = {n for n in names if names.count(n) > 1}
    if dup:
        sys.exit(f"duplicate Python names: {sorted(dup)}")

    consts, cstubs = g.constants()
    conv, rcode, rstubs = g.converters()

    pxi = [
        "# Generated by tools/gen_bindings.py from thirdparty/cui/include. Do not edit.\n",
        "\n".join(consts),
        "\n",
        "\n".join(rcode),
        "\n",
        "\n\n".join(conv),
        "\n\n",
        "\n\n".join(g.scopes),
        "\n\n",
        "cdef class _GenContext(_ContextBase):\n",
        "\n\n".join(g.methods),
        "\n\n",
        "\n\n".join(g.funcs),
        "\n",
    ]
    (OUT / "_gen.pxi").write_text("\n".join(pxi))

    stub_head = (OUT.parent.parent / "tools" / "core_stub_head.pyi.in").read_text()
    stub = [
        stub_head,
        "\n".join(cstubs),
        "\n",
        "\n\n".join(rstubs),
        "\n",
        "\n\n".join(g.stub_scopes),
        "\n",
        "class _GenContext:",
        "\n".join(g.stub_methods),
        "\n",
        (OUT.parent.parent / "tools" / "core_stub_tail.pyi.in").read_text(),
        "\n\n".join(g.stub_funcs),
        "",
    ]
    (OUT / "_core.pyi").write_text("\n".join(stub))

    # coverage report
    total = len(m.functions) + len([1 for n, r in m.skipped_decls if r == "variadic"])
    rep = [
        "# Binding coverage",
        "",
        "Generated by `tools/gen_bindings.py`. Do not edit.",
        "",
        f"- CUI functions declared: {total}",
        f"- Wrapped by the generator: {len(g.wrapped)} entries (scopes count once per begin/end pair)",
        f"- Wrapped by hand in `_core.pyx`: {len(MANUAL & set(fns))}",
        f"- Not exposed on purpose: {len(EXCLUDED)}",
        f"- Not wrapped yet: {len(g.skipped) + len([1 for n, r in m.skipped_decls if r == 'variadic'])}",
        "",
        "## Not wrapped yet",
        "",
        "| C function | Reason |",
        "|-|-|",
    ]
    for n, r in sorted(g.skipped):
        rep.append(f"| `{n}` | {r} |")
    for n, r in m.skipped_decls:
        if r == "variadic":
            rep.append(f"| `{n}` | variadic; format the string in Python |")
    rep += ["", "## Not exposed on purpose", "", "| C function | Reason |", "|-|-|"]
    rep += [f"| `{n}` | {r} |" for n, r in sorted(EXCLUDED.items())]
    rep += [
        "",
        "## Options without a keyword argument",
        "",
        "These fields are pointers, arrays or callbacks. The C default applies.",
        "",
        "| C function | Fields |",
        "|-|-|",
    ]
    for n, gaps in sorted(g.opt_gaps.items()):
        rep.append(f"| `{n}` | {', '.join(f'`{x}`' for x in gaps)} |")
    rep += ["", "## Wrapped", "", "| C function | Python |", "|-|-|"]
    for n, p in sorted(g.wrapped):
        rep.append(f"| `{n}` | `{p}` |")
    (ROOT / "docs" / "dev").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "dev" / "coverage.md").write_text("\n".join(rep) + "\n")
    print(
        f"wrapped {len(g.wrapped)}, skipped {len(g.skipped)}, "
        f"methods {len(g.methods)}, functions {len(g.funcs)}, scopes {len(g.scopes)}"
    )


if __name__ == "__main__":
    main()
