# cython: language_level=3, embedsignature=True
"""CUI bindings.

The generated part (`_gen.pxi`) holds one Context method per CUI component
and one scope class per begin/end pair. This file holds what the generator
cannot write: value types, buffers, lifetimes, frames, callbacks and the app.

Lifetimes: strings and arrays passed to a component stay alive until the
frame ends, because CUI may read them while it lays out and paints. CUI copies
what it keeps across frames, so nothing passed in needs to live longer.
"""

from libc.stdlib cimport calloc, free, malloc
from libc.string cimport memchr, memcpy, memset
from cpython.ref cimport PyObject

import datetime as _datetime
import sys as _sys
from collections import deque as _deque
from collections import namedtuple as _namedtuple
from time import monotonic as _monotonic
from collections.abc import Mapping as _Mapping

from cui._cui cimport *

# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------

Color = _namedtuple("Color", "r g b a", defaults=(255,))
Rect = _namedtuple("Rect", "x y w h")
Vec2 = _namedtuple("Vec2", "x y")
Size = _namedtuple("Size", "kind value")
Corners = _namedtuple("Corners", "tl tr br bl")
CanvasResult = _namedtuple("CanvasResult", "rect hovered pressed clicked mouse")

FIT = Size(CUI_SIZE_FIT, 0.0)
FILL = Size(CUI_SIZE_GROW, 1.0)
MOD_PRIMARY = CUI_MOD_SUPER if _sys.platform == "darwin" else CUI_MOD_CTRL


def px(v):
    """A fixed size in points."""
    return Size(CUI_SIZE_FIXED, float(v))


def pct(p):
    """A size in percent of the parent, 0..100."""
    return Size(CUI_SIZE_PERCENT, float(p))


def grow(w=1):
    """A share of the space left, weighted by `w`."""
    return Size(CUI_SIZE_GROW, float(w))


def rgb(long long hex):
    """Color from 0xRRGGBB."""
    if not 0 <= hex <= 0xFFFFFF:
        raise ValueError(f"rgb takes 0x000000..0xFFFFFF, got {hex:#x}")
    return Color((hex >> 16) & 0xFF, (hex >> 8) & 0xFF, hex & 0xFF, 255)


def rgba(long long hex):
    """Color from 0xRRGGBBAA."""
    if not 0 <= hex <= 0xFFFFFFFF:
        raise ValueError(f"rgba takes 0x00000000..0xFFFFFFFF, got {hex:#x}")
    return Color((hex >> 24) & 0xFF, (hex >> 16) & 0xFF, (hex >> 8) & 0xFF, hex & 0xFF)


cdef uint8_t _channel(object v, str name) except? 0:
    cdef long x = v
    if not 0 <= x <= 255:
        raise ValueError(f"color channel {name} must be 0..255, got {x}")
    return <uint8_t>x


cdef cui_color _to_cui_color(object o) except *:
    cdef cui_color c
    if isinstance(o, int):
        o = rgb(o)
    t = tuple(o)
    if len(t) not in (3, 4):
        raise ValueError(f"a color takes 3 or 4 channels, got {len(t)}")
    c.r = _channel(t[0], "r")
    c.g = _channel(t[1], "g")
    c.b = _channel(t[2], "b")
    c.a = _channel(t[3], "a") if len(t) == 4 else 255
    return c


cdef object _from_cui_color(cui_color c):
    return Color(c.r, c.g, c.b, c.a)


cdef cui_rect _to_cui_rect(object o) except *:
    cdef cui_rect r
    r.x, r.y, r.w, r.h = o
    return r


cdef object _from_cui_rect(cui_rect r):
    return Rect(r.x, r.y, r.w, r.h)


cdef cui_vec2 _to_cui_vec2(object o) except *:
    cdef cui_vec2 v
    v.x, v.y = o
    return v


cdef object _from_cui_vec2(cui_vec2 v):
    return Vec2(v.x, v.y)


cdef cui_size _to_cui_size(object o) except *:
    cdef cui_size s
    if isinstance(o, (int, float)):
        s.kind = CUI_SIZE_FIXED
        s.value = o
        return s
    kind, value = o
    s.kind = <cui_size_kind><int>kind
    s.value = value
    return s


cdef object _from_cui_size(cui_size s):
    return Size(<int>s.kind, s.value)


cdef cui_corners _to_cui_corners(object o) except *:
    cdef cui_corners c
    if isinstance(o, (int, float)):
        c.tl = c.tr = c.br = c.bl = o
        return c
    c.tl, c.tr, c.br, c.bl = o
    return c


cdef object _from_cui_corners(cui_corners c):
    return Corners(c.tl, c.tr, c.br, c.bl)


cdef cui_date _to_cui_date(object o) except *:
    cdef cui_date d
    memset(&d, 0, sizeof(d))
    if o is None:
        return d
    if isinstance(o, _datetime.date):
        d.year, d.month, d.day = o.year, o.month, o.day
    else:
        d.year, d.month, d.day = o
    return d


cdef object _from_cui_date(cui_date d):
    if d.year == 0:
        return None
    return _datetime.date(d.year, d.month, d.day)


def _record(name, fields):
    """A namedtuple whose fields default to None, which CUI reads as zero."""
    return _namedtuple(name, fields, defaults=(None,) * len(fields))


cdef tuple _record_tuple(object o, tuple names, str typename):
    """Fields of a struct given as a mapping, a namedtuple or a sequence."""
    cdef Py_ssize_t n = len(names)
    if isinstance(o, _Mapping):
        extra = set(o) - set(names)
        if extra:
            raise TypeError(f"{typename} has no field {sorted(extra)[0]!r}")
        return tuple([o.get(k) for k in names])
    if isinstance(o, (str, bytes)) or o is None:
        raise TypeError(f"{typename} must be a {typename}, tuple or dict, not {type(o).__name__}")
    t = tuple(o)
    if len(t) > n:
        raise TypeError(f"{typename} takes at most {n} values, got {len(t)}")
    return t + (None,) * (n - len(t))


# ---------------------------------------------------------------------------
# Strings and arrays
# ---------------------------------------------------------------------------


cdef bytes _encode(object s):
    cdef bytes b
    if isinstance(s, str):
        b = (<str>s).encode("utf-8")
    elif isinstance(s, bytes):
        b = <bytes>s
    else:
        raise TypeError(f"expected str, got {type(s).__name__}")
    if b"\0" in b:
        raise ValueError("strings passed to CUI cannot contain NUL characters")
    return b


cdef const char *_cstr(list keep, object s) except NULL:
    """A C string that lives as long as `keep`."""
    if keep is None:
        raise RuntimeError("internal: string without an owner")
    cdef bytes b = _encode(s)
    keep.append(b)
    return <const char *>b


cdef Py_ssize_t _cstr_len(list keep, object s) except -1:
    return len(_encode(s))


cdef inline Py_ssize_t _clamp_count(Py_ssize_t count, Py_ssize_t n):
    """`count` as CUI reported it, kept within the `n` items allocated.

    Generated code calls this, not min/max: C parameters named min and max
    shadow the builtins there.
    """
    return 0 if count < 0 else n if count > n else count


cdef object _str_or_none(const char *s):
    if s == NULL:
        return None
    return (<bytes>s).decode("utf-8", "replace")


cdef class _StrArray:
    """`const char *const *` with its strings."""
    cdef const char **ptr
    cdef readonly Py_ssize_t n
    cdef list _bytes

    def __cinit__(self, object seq):
        self._bytes = [_encode(s) for s in seq]
        self.n = len(self._bytes)
        self.ptr = <const char **>malloc((self.n or 1) * sizeof(char *))
        if self.ptr == NULL:
            raise MemoryError()
        cdef Py_ssize_t i
        for i in range(self.n):
            self.ptr[i] = <const char *>(<bytes>self._bytes[i])

    def __dealloc__(self):
        free(self.ptr)


cdef class _FloatArray:
    cdef float *ptr
    cdef readonly Py_ssize_t n

    def __cinit__(self, object seq):
        items = list(seq)
        self.n = len(items)
        self.ptr = <float *>malloc((self.n or 1) * sizeof(float))
        if self.ptr == NULL:
            raise MemoryError()
        cdef Py_ssize_t i
        for i in range(self.n):
            self.ptr[i] = items[i]

    def __dealloc__(self):
        free(self.ptr)


cdef class _ScalarArray:
    """A mutable array of bool ("?"), int ("i"), uint32 ("I"), float ("f") or double ("d")."""
    cdef void *ptr
    cdef readonly Py_ssize_t n
    cdef str code

    def __cinit__(self, object seq, str code):
        items = list(seq)
        self.n = len(items)
        self.code = code
        cdef size_t size
        if code == "?":
            size = sizeof(cbool)
        elif code == "i":
            size = sizeof(int)
        elif code == "I":
            size = sizeof(uint32_t)
        elif code == "f":
            size = sizeof(float)
        elif code == "d":
            size = sizeof(double)
        else:
            raise ValueError(code)
        self.ptr = calloc(self.n or 1, size)
        if self.ptr == NULL:
            raise MemoryError()
        cdef Py_ssize_t i
        for i in range(self.n):
            if code == "?":
                (<cbool *>self.ptr)[i] = bool(items[i])
            elif code == "i":
                (<int *>self.ptr)[i] = items[i]
            elif code == "I":
                (<uint32_t *>self.ptr)[i] = items[i]
            elif code == "f":
                (<float *>self.ptr)[i] = items[i]
            else:
                (<double *>self.ptr)[i] = items[i]

    def __dealloc__(self):
        free(self.ptr)

    def tolist(self):
        cdef Py_ssize_t i
        if self.code == "?":
            return [bool((<cbool *>self.ptr)[i]) for i in range(self.n)]
        if self.code == "i":
            return [(<int *>self.ptr)[i] for i in range(self.n)]
        if self.code == "I":
            return [(<uint32_t *>self.ptr)[i] for i in range(self.n)]
        if self.code == "f":
            return [(<float *>self.ptr)[i] for i in range(self.n)]
        return [(<double *>self.ptr)[i] for i in range(self.n)]


cdef class _Mem:
    """Zeroed memory for `n` structs of `size` bytes."""
    cdef void *ptr
    cdef readonly Py_ssize_t n

    def __cinit__(self, Py_ssize_t n, size_t size):
        self.n = n
        self.ptr = calloc(n or 1, size)
        if self.ptr == NULL:
            raise MemoryError()

    def __dealloc__(self):
        free(self.ptr)


cdef class TextBuffer:
    """Fixed-capacity UTF-8 buffer that text components edit in place.

    `capacity` counts bytes including the terminating NUL, as in C.
    """
    cdef char *data
    cdef size_t cap

    def __cinit__(self, Py_ssize_t capacity=256, value=""):
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.cap = capacity
        self.data = <char *>calloc(self.cap, 1)
        if self.data == NULL:
            raise MemoryError()
        self.value = value

    def __dealloc__(self):
        free(self.data)

    @property
    def capacity(self):
        return self.cap

    @property
    def value(self):
        cdef const char *end = <const char *>memchr(self.data, 0, self.cap)
        cdef Py_ssize_t n = (end - self.data) if end != NULL else <Py_ssize_t>self.cap
        return self.data[:n].decode("utf-8", "replace")

    @value.setter
    def value(self, v):
        cdef bytes b = _encode(v)
        cdef size_t n = len(b)
        if n >= self.cap:
            raise ValueError(f"{n} bytes do not fit in a TextBuffer of capacity {self.cap}")
        memcpy(self.data, <const char *>b, n)
        memset(self.data + n, 0, self.cap - n)

    def __str__(self):
        return self.value

    def __repr__(self):
        return f"TextBuffer({self.cap}, {self.value!r})"


# ---------------------------------------------------------------------------
# Ring buffers a view reads: log and terminal
# ---------------------------------------------------------------------------

LogLine = _namedtuple("LogLine", "level time text")


cdef class _Pinned:
    """A buffer that a view reads until its frame is painted.

    The view pins it. Writes made while it is pinned, by another thread while
    `App.frame()` paints or later in the same build, are queued and applied
    when the frame ends, so the paint never reads text that changed under it.
    """
    cdef int _pins
    cdef object _pending        # deque of (encoded write, bytes)
    cdef Py_ssize_t _pending_bytes
    cdef bint _pending_clear
    cdef Py_ssize_t _max_items

    def __cinit__(self, *args, **kwargs):
        self._pending = _deque()

    cdef void _apply(self, object op) noexcept:
        pass

    cdef void _reset(self) noexcept:
        pass

    cdef Py_ssize_t _max_bytes(self) noexcept:
        return 0

    cdef int _write(self, object op, Py_ssize_t nbytes) except -1:
        if not self._pins:
            self._apply(op)
            return 0
        self._pending.append((op, nbytes))
        self._pending_bytes += nbytes
        # the ring would drop the oldest anyway, so the queue stays bounded too
        while len(self._pending) > self._max_items or self._pending_bytes > self._max_bytes():
            self._pending_bytes -= self._pending.popleft()[1]
        return 0

    cdef int _clear(self) except -1:
        if not self._pins:
            self._reset()
            return 0
        self._pending.clear()
        self._pending_bytes = 0
        self._pending_clear = True
        return 0

    cdef void _pin(self) noexcept:
        self._pins += 1

    cdef void _unpin(self) noexcept:
        self._pins -= 1
        if self._pins:
            return
        if self._pending_clear:
            self._pending_clear = False
            self._reset()
        while self._pending:
            self._apply(self._pending.popleft()[0])
        self._pending_bytes = 0


cdef class LogBuffer(_Pinned):
    """Lines for `ui.log_view`: a ring of `lines` records over `text_bytes` of text.

    When either is full the oldest lines go. Safe to append from any thread;
    a write made while a view uses the buffer shows from the next frame.
    """
    cdef cui_log_buffer buf
    cdef cui_log_line *lines
    cdef char *text
    cdef double t0

    def __cinit__(self, int lines=4096, Py_ssize_t text_bytes=256 * 1024):
        if lines < 1:
            raise ValueError("lines must be at least 1")
        if text_bytes < 2 or text_bytes > 0x7FFFFFFF:
            raise ValueError("text_bytes must be between 2 and 2**31 - 1")
        self.lines = <cui_log_line *>calloc(lines, sizeof(cui_log_line))
        self.text = <char *>malloc(text_bytes)
        if self.lines == NULL or self.text == NULL:
            raise MemoryError()
        cui_log_init(&self.buf, self.lines, lines, self.text, text_bytes)
        self._max_items = lines
        self.t0 = _monotonic()

    def __dealloc__(self):
        free(self.lines)
        free(self.text)

    cdef Py_ssize_t _max_bytes(self) noexcept:
        return self.buf.text_cap

    cdef void _apply(self, object op) noexcept:
        cdef int level
        cdef double t
        cdef bytes b
        level, t, b = op
        cui_log_append_text(&self.buf, <cui_log_level>level, t, <const char *>b, <int>len(b))

    cdef void _reset(self) noexcept:
        cui_log_clear(&self.buf)

    def append(self, text, int level=CUI_LOG_INFO, time=None):
        """Appends one line at `level`. `time` is in seconds, by default since the buffer was made."""
        if not 0 <= level < CUI_LOG_LEVEL_COUNT:
            raise ValueError(f"level must be a LOG_* constant, got {level}")
        cdef bytes b = _encode(text)
        if len(b) > 0x7FFFFFFF:
            raise ValueError("line too long")
        cdef double t = _monotonic() - self.t0 if time is None else float(time)
        self._write((level, t, b), len(b))

    def clear(self):
        self._clear()

    def __len__(self):
        return self.buf.count

    def __getitem__(self, Py_ssize_t i):
        """Line `i`, 0 the oldest, as `LogLine(level, time, text)`."""
        if i < 0:
            i += self.buf.count
        cdef const char *s = NULL
        cdef const cui_log_line *ln = NULL
        if 0 <= i < self.buf.count:
            ln = cui_log_get(&self.buf, <int>i, &s)
        if ln == NULL:
            raise IndexError("log line out of range")
        return LogLine(ln.level, ln.time, s[:ln.len].decode("utf-8", "replace"))

    @property
    def total(self):
        """Lines ever appended, dropped ones included."""
        return self.buf.total

    @property
    def level_counts(self):
        """Lines of each level now held, indexed by LOG_*."""
        return tuple([self.buf.level_count[k] for k in range(<int>CUI_LOG_LEVEL_COUNT)])


cdef class TerminalBuffer(_Pinned):
    """Output for `ui.terminal`: ANSI text in a ring of `lines` over `text_bytes`.

    Safe to write from any thread; a write made while a view uses the buffer
    shows from the next frame.
    """
    cdef cui_terminal_buffer buf
    cdef cui_terminal_line *lines
    cdef char *text

    def __cinit__(self, int lines=8192, Py_ssize_t text_bytes=512 * 1024):
        if lines < 2:
            raise ValueError("lines must be at least 2")
        if text_bytes < 64 or text_bytes > 0x7FFFFFFF:
            raise ValueError("text_bytes must be between 64 and 2**31 - 1")
        self.lines = <cui_terminal_line *>calloc(lines, sizeof(cui_terminal_line))
        self.text = <char *>malloc(text_bytes)
        if self.lines == NULL or self.text == NULL:
            raise MemoryError()
        cui_terminal_init(&self.buf, self.text, text_bytes, self.lines, lines)
        self._max_items = 1 << 30   # writes are chunks, not lines: bounded by bytes

    def __dealloc__(self):
        free(self.lines)
        free(self.text)

    cdef Py_ssize_t _max_bytes(self) noexcept:
        return self.buf.text_cap

    cdef void _apply(self, object op) noexcept:
        cdef bytes b = op
        cui_terminal_write(&self.buf, <const char *>b, <int>len(b))

    cdef void _reset(self) noexcept:
        cui_terminal_clear(&self.buf)

    def write(self, data):
        """Appends output, `str` or bytes; `\\n`, `\\r`, `\\b` and ANSI color codes apply."""
        cdef bytes b = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        if len(b) > 0x7FFFFFFF:
            raise ValueError("write too long; split it")
        if b:
            self._write(b, len(b))

    def clear(self):
        self._clear()

    def __len__(self):
        return self.buf.count

    @property
    def total(self):
        """Lines ever started, dropped ones included."""
        return self.buf.total


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


cdef class _ContextBase:
    cdef cui_ctx *ui
    cdef list _keep
    cdef list _pinned       # ring buffers views read this frame
    cdef bint _in_frame
    cdef bint _painting
    cdef int _open_scopes
    cdef object _paint_error

    def __cinit__(self):
        self._keep = []
        self._pinned = []

    cdef void _frame_done(self) noexcept:
        """Drops what the frame's paint needed and applies queued buffer writes."""
        self._keep = []
        pinned, self._pinned = self._pinned, []
        for b in pinned:
            (<_Pinned>b)._unpin()

    cdef int _need_alive(self) except -1:
        if self.ui == NULL:
            raise RuntimeError("the context is closed")
        return 0

    cdef int _need_frame(self) except -1:
        self._need_alive()
        if self._painting:
            raise RuntimeError("components cannot be built inside a paint callback")
        if not self._in_frame:
            raise RuntimeError("components can only be built inside a frame")
        return 0

    cdef int _need_paint(self) except -1:
        self._need_alive()
        if not self._painting:
            raise RuntimeError("drawing functions work only inside a canvas paint callback")
        return 0

    cdef int _raise_paint_error(self) except -1:
        e = self._paint_error
        self._paint_error = None
        if e is not None:
            raise e
        return 0


include "_gen.pxi"


cdef void _paint_trampoline(cui_ctx *ui, cui_rect rect, void *user) noexcept with gil:
    cdef tuple holder = <tuple>(<PyObject **>user)[0]
    cdef _ContextBase ctx = <_ContextBase>holder[0]
    if ctx._paint_error is not None:
        return
    ctx._painting = True
    try:
        holder[1](_from_cui_rect(rect))
    except BaseException as e:
        ctx._paint_error = e
    finally:
        ctx._painting = False


cdef void _clip_set(void *user, const char *utf8) noexcept with gil:
    (<Context>user)._clipboard = <bytes>utf8


cdef const char *_clip_get(void *user) noexcept with gil:
    return <const char *>(<Context>user)._clipboard


cdef class _Frame:
    cdef Context ctx
    cdef float dt

    def __enter__(self):
        self.ctx.begin_frame(self.dt)
        return self.ctx

    def __exit__(self, *exc):
        if self.ctx._in_frame:
            self.ctx.end_frame()
        return False


cdef class Context(_GenContext):
    """A CUI context.

    Built directly, it has no window: it renders with the software renderer,
    and input comes from the `input_*` methods. `App.ui` is a context owned by
    a window.
    """
    cdef cui_sw_renderer *_sw
    cdef bint _owned
    cdef bint _have_draw
    cdef bytes _clipboard

    def __init__(self, float width=800, float height=600, float scale=1.0, *, int theme=0,
                 int accent=0, bint reduced_motion=False, bint default_fonts=True):
        if self.ui != NULL:
            raise RuntimeError("Context.__init__ called twice")
        cdef cui_ctx_desc d
        memset(&d, 0, sizeof(d))
        self._sw = cui_sw_create()
        if self._sw == NULL:
            raise MemoryError()
        d.renderer = cui_sw_iface(self._sw)
        d.theme = <cui_theme_mode>theme
        d.accent = <cui_accent>accent
        d.no_default_fonts = not default_fonts
        self.ui = cui_create(&d)
        if self.ui == NULL:
            cui_sw_destroy(self._sw)
            self._sw = NULL
            raise MemoryError()
        self._owned = True
        self._clipboard = b""
        cdef cui_platform_iface p
        memset(&p, 0, sizeof(p))
        p.user = <void *>self
        p.set_clipboard = _clip_set
        p.get_clipboard = _clip_get
        cui_set_platform(self.ui, &p)
        cui_set_viewport(self.ui, width, height, scale)
        cui_set_reduced_motion(self.ui, reduced_motion)

    def __dealloc__(self):
        self._destroy()

    cdef void _destroy(self) noexcept:
        if self._owned and self.ui != NULL:
            cui_destroy(self.ui)
        if self._sw != NULL:
            cui_sw_destroy(self._sw)
        self.ui = NULL
        self._sw = NULL
        self._in_frame = False
        self._frame_done()

    def close(self):
        """Frees the context. Later calls raise RuntimeError."""
        if not self._owned:
            raise RuntimeError("this context belongs to an App; close the App")
        self._destroy()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self._owned:
            self._destroy()
        return False

    @property
    def in_frame(self):
        return self._in_frame

    @property
    def clipboard(self):
        """Text that copy and paste use when there is no window."""
        return self._clipboard.decode("utf-8", "replace")

    @clipboard.setter
    def clipboard(self, value):
        self._clipboard = _encode(value)

    def begin_frame(self, float dt=1.0 / 60.0):
        if not self._owned:
            raise RuntimeError("App.frame() begins and ends the frames of an App")
        self._need_alive()
        if self._in_frame:
            raise RuntimeError("begin_frame called twice without end_frame")
        cui_begin_frame(self.ui, dt)
        self._in_frame = True
        self._have_draw = False

    def end_frame(self):
        """Lays out and paints the frame. Re-raises an error from a paint callback."""
        self._need_frame()
        if self._open_scopes:
            raise RuntimeError(f"{self._open_scopes} scope(s) are still open")
        self._in_frame = False
        self._paint_error = None
        cui_end_frame(self.ui)
        self._frame_done()
        self._have_draw = True
        self._raise_paint_error()

    def frame(self, float dt=1.0 / 60.0):
        """`with ctx.frame(): ...` builds one frame."""
        cdef _Frame f = _Frame.__new__(_Frame)
        f.ctx = self
        f.dt = dt
        return f

    def canvas(self, str id not None, width, height, paint=None):
        """A box you paint yourself. `paint(rect)` runs after layout and may call `draw_*`."""
        self._need_frame()
        cdef const char *c_id = _cstr(self._keep, id)
        cdef cui_size w = _to_cui_size(width)
        cdef cui_size h = _to_cui_size(height)
        cdef cui_canvas_result r
        cdef PyObject *p
        if paint is None:
            r = cui_canvas(self.ui, c_id, w, h, NULL, NULL, 0)
        else:
            if not callable(paint):
                raise TypeError("paint must be callable")
            holder = (self, paint)
            self._keep.append(holder)
            p = <PyObject *>holder
            r = cui_canvas(self.ui, c_id, w, h, _paint_trampoline, &p, sizeof(PyObject *))
        return CanvasResult(_from_cui_rect(r.rect), r.hovered, r.pressed, r.clicked,
                            _from_cui_vec2(r.mouse))

    def image_create(self, int width, int height, bytes rgba not None):
        """A texture from RGBA pixels, `width * height * 4` bytes."""
        self._need_alive()
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive")
        if len(rgba) != <Py_ssize_t>width * height * 4:
            raise ValueError(f"expected {width * height * 4} bytes of RGBA, got {len(rgba)}")
        return cui_image_create(self.ui, width, height, <const char *>rgba)

    def font_load_memory(self, bytes data not None):
        """Loads a TrueType or OpenType font. Returns its handle, or -1."""
        self._need_alive()
        return cui_font_load_memory(self.ui, <const char *>data, len(data), True)

    def emoji_font_load_memory(self, bytes data not None):
        self._need_alive()
        return cui_emoji_font_load_memory(self.ui, <const char *>data, len(data), True)

    def draw_counts(self):
        """(vertices, indices, commands) of the last frame."""
        self._need_alive()
        if not self._have_draw:
            raise RuntimeError("no finished frame to inspect")
        cdef const cui_draw_data *dd = cui_get_draw_data(self.ui)
        return dd.vertex_count, dd.index_count, dd.command_count

    def render_size(self):
        """(width_px, height_px) of the last frame."""
        self._need_alive()
        if not self._have_draw:
            raise RuntimeError("no finished frame")
        cdef const cui_draw_data *dd = cui_get_draw_data(self.ui)
        return dd.width_px, dd.height_px

    def render(self):
        """RGBA pixels of the last frame, `width_px * height_px * 4` bytes."""
        self._need_alive()
        if self._sw == NULL:
            raise RuntimeError("an App renders to its window; use App.screenshot")
        if not self._have_draw:
            raise RuntimeError("no finished frame to render")
        cdef const cui_draw_data *dd = cui_get_draw_data(self.ui)
        cdef int w = dd.width_px
        cdef int h = dd.height_px
        out = bytearray(<Py_ssize_t>w * h * 4)
        cdef char *buf = out
        cui_sw_render(self._sw, dd, buf, w, h, w * 4, CUI_SW_RGBA)
        return bytes(out)

    def save_png(self, path):
        """Writes the last frame to a PNG file."""
        pixels = self.render()
        w, h = self.render_size()
        write_png(path, pixels, w, h)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


cdef class App:
    """A native window with an event loop.

        app = cui.App("Hello")
        for ui in app.frames():
            ui.button("Click")
    """
    cdef cui_app *app
    cdef Context _ui
    cdef list _strings

    def __init__(self, str title not None="CUI", int width=1080, int height=720, *,
                 int min_width=0, int min_height=0, bint fixed_size=False, bint continuous=False,
                 bint no_vsync=False, bint hidden=False, int renderer=0, int theme=0,
                 int accent=0, bint follow_system_theme=False, app_id=None):
        if self.app != NULL:
            raise RuntimeError("App.__init__ called twice")
        self._strings = []
        cdef cui_app_desc d
        memset(&d, 0, sizeof(d))
        d.title = _cstr(self._strings, title)
        d.width = width
        d.height = height
        d.min_width = min_width
        d.min_height = min_height
        d.fixed_size = fixed_size
        d.continuous = continuous
        d.no_vsync = no_vsync
        d.hidden = hidden
        d.renderer = <cui_renderer_kind>renderer
        d.theme = <cui_theme_mode>theme
        d.accent = <cui_accent>accent
        d.follow_system_theme = follow_system_theme
        if app_id is not None:
            d.app_id = _cstr(self._strings, app_id)
        self.app = cui_app_create(&d)
        if self.app == NULL:
            raise RuntimeError("could not create the window")
        self._ui = Context.__new__(Context)
        self._ui.ui = cui_app_ui(self.app)
        self._ui._owned = False

    def __dealloc__(self):
        self._close()

    cdef void _close(self) noexcept:
        if self.app != NULL:
            if self._ui is not None:
                self._ui.ui = NULL
                self._ui._in_frame = False
                self._ui._frame_done()
            cui_app_destroy(self.app)
            self.app = NULL

    cdef int _need_app(self) except -1:
        if self.app == NULL:
            raise RuntimeError("the app is closed")
        return 0

    def close(self):
        """Destroys the window."""
        self._close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._close()
        return False

    @property
    def ui(self):
        return self._ui

    def frame(self):
        """Presents the last frame, waits for input, and begins the next.

        Returns False once the window is closed.
        """
        self._need_app()
        cdef Context ctx = self._ui
        if ctx._open_scopes:
            raise RuntimeError(f"{ctx._open_scopes} scope(s) are still open")
        ctx._in_frame = False
        ctx._paint_error = None
        cdef cbool ok
        with nogil:
            ok = cui_app_frame(self.app)
        ctx._frame_done()
        ctx._in_frame = ok
        ctx._raise_paint_error()
        return ok

    def frames(self):
        """Yields the context once per frame until the window closes."""
        while self.frame():
            yield self._ui

    def run(self, fn):
        """Calls `fn(ui)` once per frame until the window closes."""
        for ui in self.frames():
            fn(ui)

    def quit(self):
        """Ends the loop after this frame."""
        self._need_app()
        cui_app_quit(self.app)

    def set_title(self, str title not None):
        self._need_app()
        cui_app_set_title(self.app, _encode(title))

    def set_size(self, int width, int height):
        self._need_app()
        cui_app_set_size(self.app, width, height)

    def size(self):
        self._need_app()
        return _from_cui_vec2(cui_app_size(self.app))

    def is_software(self):
        self._need_app()
        return cui_app_is_software(self.app)

    def backend(self):
        self._need_app()
        return _str_or_none(cui_app_backend(self.app))

    def screenshot(self):
        """(width_px, height_px, RGBA pixels) of the current UI, at the framebuffer's size."""
        self._need_app()
        cdef const cui_draw_data *dd = cui_get_draw_data(cui_app_ui(self.app))
        cdef int w = dd.width_px
        cdef int h = dd.height_px
        if w <= 0 or h <= 0:
            raise RuntimeError("no frame has been drawn yet")
        out = bytearray(<Py_ssize_t>w * h * 4)
        cdef char *buf = out
        if not cui_app_screenshot(self.app, buf, w, h):
            raise RuntimeError("the screenshot failed")
        return w, h, bytes(out)

    def file_dialog(self, int kind=0, title=None, filter_name=None, filter=None,
                    default_name=None):
        """A native open, save or folder dialog. Blocks; returns the path or None."""
        self._need_app()
        cdef list keep = []
        cdef cui_file_dialog_opts o
        memset(&o, 0, sizeof(o))
        o.kind = <cui_file_dialog_kind>kind
        if title is not None:
            o.title = _cstr(keep, title)
        if filter_name is not None:
            o.filter_name = _cstr(keep, filter_name)
        if filter is not None:
            o.filter = _cstr(keep, filter)
        if default_name is not None:
            o.default_name = _cstr(keep, default_name)
        cdef char out[4096]
        out[0] = 0
        if not cui_app_file_dialog(self.app, &o, out, sizeof(out)):
            return None
        return out.decode("utf-8", "replace")


def open_url(str url not None):
    """Opens a URL or file with the system's default handler."""
    return cui_app_open_url(_encode(url))


def write_png(path, bytes rgba not None, int width, int height):
    """Writes RGBA pixels to a PNG file."""
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    if len(rgba) != <Py_ssize_t>width * height * 4:
        raise ValueError(f"expected {width * height * 4} bytes of RGBA, got {len(rgba)}")
    cdef bytes p = _encode(str(path))
    if not cui_write_png(p, <const char *>rgba, width, height, width * 4):
        raise OSError(f"could not write {path}")
