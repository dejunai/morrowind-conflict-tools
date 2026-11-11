"""mwdialog_lua.py - a Lua 5.1 / LuaJIT tokenizer and parser in pure Python, for mwdialog_luafix.py.

Works on text decoded as latin-1, so every character is one byte of the file: spans are byte offsets and an edit
never changes the encoding or line endings of anything it does not touch. The parser builds a full syntax
tree (every statement and expression of Lua 5.1 plus LuaJIT's goto/labels and number suffixes); a file it can't
parse is reported and never edited.
"""

KEYWORDS = {"and", "break", "do", "else", "elseif", "end", "false", "for", "function", "goto", "if", "in",
            "local", "nil", "not", "or", "repeat", "return", "then", "true", "until", "while"}
OPS3 = ("...",)
OPS2 = ("==", "~=", "<=", ">=", "..", "::")
OPS1 = set("+-*/%^#<>=(){}[];:,.")


class LuaSyntaxError(Exception):
    def __init__(self, msg, pos, line):
        super().__init__(f"line {line}: {msg}")
        self.pos, self.line = pos, line


class Tok:
    __slots__ = ("t", "v", "s", "e", "line")

    def __init__(self, t, v, s, e, line):
        self.t, self.v, self.s, self.e, self.line = t, v, s, e, line

    def __repr__(self):
        return f"Tok({self.t},{self.v!r},{self.s})"


def _long_bracket(src, i):
    """At src[i] == '[': the level of a long bracket opening here ([[ = 0, [==[ = 2), or -1."""
    j = i + 1
    while j < len(src) and src[j] == "=":
        j += 1
    if j < len(src) and src[j] == "[":
        return j - i - 1
    return -1


def tokenize(src):
    """The tokens of src (comments and blanks dropped; each token keeps its byte span and line). The first
    line is skipped when it starts with '#' (a shebang), as Lua does."""
    toks, i, n, line = [], 0, len(src), 1
    if src.startswith("\xef\xbb\xbf"):
        i = 3
    if src.startswith("#", i):
        while i < n and src[i] not in "\r\n":
            i += 1
    while True:
        while i < n:                                   # blanks and comments
            c = src[i]
            if c == "\n":
                line += 1
                i += 1
            elif c in " \t\r\f\v":
                i += 1
            elif c == "-" and src.startswith("--", i):
                s0 = i
                i += 2
                if i < n and src[i] == "[":
                    lvl = _long_bracket(src, i)
                    if lvl >= 0:
                        close = "]" + "=" * lvl + "]"
                        j = src.find(close, i + lvl + 2)
                        if j < 0:
                            raise LuaSyntaxError("unfinished long comment", s0, line)
                        line += src.count("\n", i, j)
                        i = j + len(close)
                        continue
                while i < n and src[i] != "\n":
                    i += 1
            else:
                break
        if i >= n:
            toks.append(Tok("eof", "", n, n, line))
            return toks
        c, s = src[i], i
        if c.isalpha() or c == "_" or ord(c) >= 0x80 and False:
            j = i + 1
            while j < n and (src[j].isalnum() or src[j] == "_") and ord(src[j]) < 0x80:
                j += 1
            w = src[i:j]
            toks.append(Tok("kw" if w in KEYWORDS else "name", w, s, j, line))
            i = j
        elif c.isdigit() or c == "." and i + 1 < n and src[i + 1].isdigit():
            j = i
            if src.startswith(("0x", "0X"), i):
                j += 2
                while j < n and (src[j] in "0123456789abcdefABCDEF."):
                    j += 1
                if j < n and src[j] in "pP":
                    j += 1
                    if j < n and src[j] in "+-":
                        j += 1
                    while j < n and src[j].isdigit():
                        j += 1
            else:
                while j < n and (src[j].isdigit() or src[j] == "."):
                    j += 1
                if j < n and src[j] in "eE":
                    j += 1
                    if j < n and src[j] in "+-":
                        j += 1
                    while j < n and src[j].isdigit():
                        j += 1
            while j < n and src[j] in "uUlLiI":            # LuaJIT 64-bit integer / imaginary suffixes
                j += 1
            if j < n and (src[j].isalnum() or src[j] == "_"):
                raise LuaSyntaxError(f"malformed number near '{src[s:j + 1]}'", s, line)
            toks.append(Tok("num", src[s:j], s, j, line))
            i = j
        elif c in "\"'":
            j = i + 1
            while True:
                if j >= n or src[j] == "\n":
                    raise LuaSyntaxError("unfinished string", s, line)
                d = src[j]
                if d == "\\":
                    if j + 1 < n and src[j + 1] == "\r" and src.startswith("\r\n", j + 1):
                        j += 3
                        line += 1
                        continue
                    if j + 1 < n and src[j + 1] == "\n":
                        line += 1
                    if j + 1 < n and src[j + 1] == "z":         # \z skips the following blanks, newlines too
                        j += 2
                        while j < n and src[j] in " \t\r\n\f\v":
                            if src[j] == "\n":
                                line += 1
                            j += 1
                        continue
                    j += 2
                    continue
                if d == c:
                    j += 1
                    break
                j += 1
            toks.append(Tok("str", src[s:j], s, j, line))
            i = j
        elif c == "[" and _long_bracket(src, i) >= 0:
            lvl = _long_bracket(src, i)
            close = "]" + "=" * lvl + "]"
            j = src.find(close, i + lvl + 2)
            if j < 0:
                raise LuaSyntaxError("unfinished long string", s, line)
            toks.append(Tok("str", src[s:j + len(close)], s, j + len(close), line))
            line += src.count("\n", i, j)
            i = j + len(close)
        else:
            for op in OPS3 + OPS2:
                if src.startswith(op, i):
                    toks.append(Tok("op", op, s, i + len(op), line))
                    i += len(op)
                    break
            else:
                if c in OPS1:
                    toks.append(Tok("op", c, s, i + 1, line))
                    i += 1
                else:
                    raise LuaSyntaxError(f"unexpected symbol near '{c}'", s, line)


def string_value(raw):
    """The value of a string token (quoted or long bracket), escapes decoded; None if it can't tell."""
    if raw.startswith("["):
        lvl = raw.index("[", 1) - 1
        body = raw[lvl + 2:len(raw) - lvl - 2]
        if body.startswith("\r\n"):
            body = body[2:]
        elif body.startswith("\n"):
            body = body[1:]
        return body
    body, out, i = raw[1:-1], [], 0
    esc = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v", "\\": "\\", '"': '"',
           "'": "'", "\n": "\n"}
    while i < len(body):
        c = body[i]
        if c != "\\":
            out.append(c)
            i += 1
            continue
        d = body[i + 1:i + 2]
        if d in esc:
            out.append(esc[d])
            i += 2
        elif d.isdigit():
            j = i + 1
            while j < len(body) and j < i + 4 and body[j].isdigit():
                j += 1
            out.append(chr(int(body[i + 1:j]) & 0xFF))
            i = j
        elif d == "x":
            out.append(chr(int(body[i + 2:i + 4], 16)))
            i += 4
        elif d == "z":
            i += 2
            while i < len(body) and body[i] in " \t\r\n\f\v":
                i += 1
        else:
            return None
    return "".join(out)


class Node:
    """One syntax tree node: kind, its own fields, and its span (s..e bytes, first/last token)."""

    def __init__(self, kind, s=0, e=0, **kw):
        self.kind, self.s, self.e = kind, s, e
        self.__dict__.update(kw)

    def __repr__(self):
        return f"<{self.kind} {self.s}-{self.e}>"

    def children(self):
        for k, v in self.__dict__.items():
            if k in ("kind", "s", "e", "parent", "scope_binding", "line", "params_end", "body_start", "fparent"):
                continue
            if isinstance(v, Node):
                yield v
            elif isinstance(v, list):
                for x in v:
                    if isinstance(x, Node):
                        yield x
                    elif isinstance(x, tuple):
                        for y in x:
                            if isinstance(y, Node):
                                yield y


BINPRI = {"or": (1, 1), "and": (2, 2), "<": (3, 3), ">": (3, 3), "<=": (3, 3), ">=": (3, 3), "~=": (3, 3),
          "==": (3, 3), "..": (5, 4), "+": (6, 6), "-": (6, 6), "*": (7, 7), "/": (7, 7), "%": (7, 7),
          "^": (10, 9)}
UNARY_PRI = 8


class Parser:
    def __init__(self, src):
        self.src = src
        self.toks = tokenize(src)
        self.i = 0

    # --- helpers
    @property
    def tok(self):
        return self.toks[self.i]

    def peek(self, k=1):
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def check(self, v, t=None):
        tk = self.tok
        return tk.v == v and tk.t in ((t,) if t else ("op", "kw"))

    def accept(self, v):
        if self.check(v):
            self.i += 1
            return self.toks[self.i - 1]
        return None

    def expect(self, v):
        tk = self.accept(v)
        if tk is None:
            self.err(f"'{v}' expected near '{self.tok.v or '<eof>'}'")
        return tk

    def err(self, msg):
        raise LuaSyntaxError(msg, self.tok.s, self.tok.line)

    def name(self):
        tk = self.tok
        if tk.t != "name":
            self.err(f"<name> expected near '{tk.v or '<eof>'}'")
        self.i += 1
        return tk

    def prev_e(self):
        return self.toks[self.i - 1].e

    # --- chunk / blocks
    def parse(self):
        b = self.block()
        if self.tok.t != "eof":
            self.err(f"'<eof>' expected near '{self.tok.v}'")
        return Node("Chunk", 0, len(self.src), body=b)

    def block_end(self):
        tk = self.tok
        return tk.t == "eof" or tk.t == "kw" and tk.v in ("end", "else", "elseif", "until")

    def block(self):
        s = self.tok.s
        stats = []
        while not self.block_end():
            if self.check("return"):
                stats.append(self.retstat())
                break
            st = self.statement()
            if st is not None:
                stats.append(st)
        return Node("Block", s, self.prev_e() if stats else s, stats=stats)

    def retstat(self):
        s = self.tok.s
        line = self.tok.line
        self.i += 1
        exprs = []
        if not self.block_end() and not self.check(";"):
            exprs = self.exprlist()
        self.accept(";")
        return Node("Return", s, self.prev_e(), exprs=exprs, line=line)

    def statement(self):
        tk = self.tok
        s, line = tk.s, tk.line
        if self.accept(";"):
            return None
        if tk.t == "kw":
            v = tk.v
            if v == "if":
                self.i += 1
                clauses = []
                cond = self.expr()
                self.expect("then")
                clauses.append((cond, self.block()))
                orelse = None
                while True:
                    if self.accept("elseif"):
                        cond = self.expr()
                        self.expect("then")
                        clauses.append((cond, self.block()))
                    elif self.accept("else"):
                        orelse = self.block()
                        self.expect("end")
                        break
                    else:
                        self.expect("end")
                        break
                return Node("If", s, self.prev_e(), clauses=clauses, orelse=orelse, line=line)
            if v == "while":
                self.i += 1
                cond = self.expr()
                self.expect("do")
                body = self.block()
                self.expect("end")
                return Node("While", s, self.prev_e(), cond=cond, body=body, line=line)
            if v == "do":
                self.i += 1
                body = self.block()
                self.expect("end")
                return Node("Do", s, self.prev_e(), body=body, line=line)
            if v == "for":
                self.i += 1
                n1 = self.name()
                if self.accept("="):
                    a = self.expr()
                    self.expect(",")
                    b = self.expr()
                    c = self.expr() if self.accept(",") else None
                    self.expect("do")
                    body = self.block()
                    self.expect("end")
                    return Node("NumFor", s, self.prev_e(), var=n1.v, start=a, stop=b, step=c, body=body, line=line)
                names = [n1.v]
                while self.accept(","):
                    names.append(self.name().v)
                self.expect("in")
                exprs = self.exprlist()
                self.expect("do")
                body = self.block()
                self.expect("end")
                return Node("GenFor", s, self.prev_e(), names=names, exprs=exprs, body=body, line=line)
            if v == "repeat":
                self.i += 1
                body = self.block()
                self.expect("until")
                cond = self.expr()
                return Node("Repeat", s, self.prev_e(), body=body, cond=cond, line=line)
            if v == "function":
                self.i += 1
                n0 = self.name()
                path = [n0.v]
                method = False
                while self.accept("."):
                    path.append(self.name().v)
                if self.accept(":"):
                    path.append(self.name().v)
                    method = True
                f = self.funcbody(s, method)
                return Node("FuncStat", s, self.prev_e(), path=path, method=method, func=f, line=line,
                            name_s=n0.s)
            if v == "local":
                self.i += 1
                if self.accept("function"):
                    n0 = self.name()
                    f = self.funcbody(s, False)
                    return Node("LocalFunc", s, self.prev_e(), name=n0.v, func=f, line=line)
                names = [self.name().v]
                while self.accept(","):
                    names.append(self.name().v)
                exprs = self.exprlist() if self.accept("=") else []
                return Node("Local", s, self.prev_e(), names=names, exprs=exprs, line=line)
            if v == "return":
                return self.retstat()
            if v == "break":
                self.i += 1
                return Node("Break", s, self.prev_e(), line=line)
            if v == "goto" and self.peek().t == "name":
                self.i += 1
                lbl = self.name().v
                return Node("Goto", s, self.prev_e(), label=lbl, line=line)
        if self.accept("::"):
            lbl = self.name().v
            self.expect("::")
            return Node("Label", s, self.prev_e(), label=lbl, line=line)
        e = self.suffixedexp()
        if self.check("=") or self.check(","):
            targets = [e]
            while self.accept(","):
                targets.append(self.suffixedexp())
            self.expect("=")
            exprs = self.exprlist()
            for t in targets:
                if t.kind not in ("Name", "Index"):
                    raise LuaSyntaxError("syntax error near '='", t.s, line)
            return Node("Assign", s, self.prev_e(), targets=targets, exprs=exprs, line=line)
        if e.kind not in ("Call", "Method"):
            raise LuaSyntaxError("syntax error (statement is not a call)", e.s, line)
        return Node("CallStat", s, self.prev_e(), call=e, line=line)

    def funcbody(self, s, method):
        line = self.tok.line
        self.expect("(")
        params, vararg = (["self"] if method else []), False
        if not self.check(")"):
            while True:
                if self.accept("..."):
                    vararg = True
                    break
                params.append(self.name().v)
                if not self.accept(","):
                    break
        close = self.expect(")")
        body = self.block()
        end = self.expect("end")
        return Node("Function", s, end.e, params=params, vararg=vararg, body=body, params_end=close.e,
                    end_s=end.s, line=line)

    # --- expressions
    def exprlist(self):
        out = [self.expr()]
        while self.accept(","):
            out.append(self.expr())
        return out

    def expr(self, limit=0):
        tk = self.tok
        if tk.t in ("op", "kw") and tk.v in ("not", "-", "#"):
            self.i += 1
            operand = self.expr(UNARY_PRI)
            left = Node("Unop", tk.s, operand.e, op=tk.v, operand=operand)
        else:
            left = self.simpleexp()
        while True:
            tk = self.tok
            pri = BINPRI.get(tk.v) if tk.t in ("op", "kw") else None
            if pri is None or pri[0] <= limit:
                return left
            self.i += 1
            right = self.expr(pri[1])
            left = Node("Binop", left.s, right.e, op=tk.v, left=left, right=right)

    def simpleexp(self):
        tk = self.tok
        if tk.t == "num":
            self.i += 1
            return Node("Number", tk.s, tk.e, raw=tk.v)
        if tk.t == "str":
            self.i += 1
            return Node("String", tk.s, tk.e, raw=tk.v)
        if tk.t == "kw" and tk.v in ("nil", "true", "false"):
            self.i += 1
            return Node(tk.v.capitalize(), tk.s, tk.e)
        if tk.t == "op" and tk.v == "...":
            self.i += 1
            return Node("Vararg", tk.s, tk.e)
        if tk.t == "op" and tk.v == "{":
            return self.table()
        if tk.t == "kw" and tk.v == "function":
            self.i += 1
            return self.funcbody(tk.s, False)
        return self.suffixedexp()

    def primaryexp(self):
        tk = self.tok
        if tk.t == "name":
            self.i += 1
            return Node("Name", tk.s, tk.e, id=tk.v)
        if self.accept("("):
            e = self.expr()
            close = self.expect(")")
            return Node("Paren", tk.s, close.e, expr=e)
        self.err(f"unexpected symbol near '{tk.v or '<eof>'}'")

    def suffixedexp(self):
        e = self.primaryexp()
        while True:
            tk = self.tok
            if tk.t == "op" and tk.v == ".":
                self.i += 1
                nm = self.name()
                e = Node("Index", e.s, nm.e, obj=e, key=Node("String", nm.s, nm.e, raw=repr(nm.v)), field=nm.v)
            elif tk.t == "op" and tk.v == "[":
                self.i += 1
                k = self.expr()
                close = self.expect("]")
                fld = string_value(k.raw) if k.kind == "String" else None
                e = Node("Index", e.s, close.e, obj=e, key=k, field=None, bracket_field=fld)
            elif tk.t == "op" and tk.v == ":":
                self.i += 1
                nm = self.name()
                args, argkind = self.callargs()
                e = Node("Method", e.s, self.prev_e(), obj=e, name=nm.v, args=args, argkind=argkind,
                         line=nm.line)
            elif tk.t == "str" or tk.t == "op" and tk.v in ("(", "{"):
                line = tk.line
                args, argkind = self.callargs()
                e = Node("Call", e.s, self.prev_e(), func=e, args=args, argkind=argkind, line=line)
            else:
                return e

    def callargs(self):
        tk = self.tok
        if tk.t == "str":
            self.i += 1
            return [Node("String", tk.s, tk.e, raw=tk.v)], "str"
        if tk.t == "op" and tk.v == "{":
            return [self.table()], "table"
        self.expect("(")
        args = [] if self.check(")") else self.exprlist()
        self.expect(")")
        return args, "paren"

    def table(self):
        s = self.expect("{").s
        fields = []                           # (key name or None, key expr or None, value)
        while not self.check("}"):
            if self.tok.t == "op" and self.tok.v == "[":
                self.i += 1
                k = self.expr()
                self.expect("]")
                self.expect("=")
                fields.append((None, k, self.expr()))
            elif self.tok.t == "name" and self.peek().t == "op" and self.peek().v == "=":
                nm = self.name()
                self.i += 1
                fields.append((nm.v, Node("String", nm.s, nm.e, raw=repr(nm.v)), self.expr()))
            else:
                fields.append((None, None, self.expr()))
            if not (self.accept(",") or self.accept(";")):
                break
        close = self.expect("}")
        return Node("Table", s, close.e, fields=fields)


def parse(src):
    """The syntax tree of src (latin-1 text), with parent links set. Raises LuaSyntaxError."""
    tree = Parser(src).parse()
    link(tree)
    return tree


def link(root):
    stack = [(root, None)]
    while stack:
        n, p = stack.pop()
        n.parent = p
        for c in n.children():
            stack.append((c, n))


def walk(node):
    """Every node under node (node included), depth first, in source order."""
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        kids = list(n.children())
        kids.sort(key=lambda c: c.s, reverse=True)
        stack.extend(kids)


def walk_no_funcs(node):
    """Like walk, but does not go into nested function expressions/statements (node's own code only)."""
    stack = [node]
    first = True
    while stack:
        n = stack.pop()
        yield n
        if not first and n.kind == "Function":
            continue
        first = False
        kids = list(n.children())
        kids.sort(key=lambda c: c.s, reverse=True)
        stack.extend(kids)


def dotted(n):
    """'tes3.event.simulate' for a chain of names and dot fields (also ["x"] with a literal string), else None."""
    parts = []
    while n is not None:
        if n.kind == "Name":
            parts.append(n.id)
            return ".".join(reversed(parts))
        if n.kind == "Index":
            f = n.field if n.field is not None else getattr(n, "bracket_field", None)
            if f is None:
                return None
            parts.append(f)
            n = n.obj
        elif n.kind == "Paren":
            n = n.expr
        else:
            return None
    return None


def enclosing_function(n):
    p = n.parent
    while p is not None and p.kind != "Function":
        p = p.parent
    return p
