"""Traductor Stata <-> Python.

Stata -> Python: reglas por regex, linea a linea (bloques con llaves -> indentacion).
Python -> Stata: recorre el AST. Lo que no se sabe traducir queda comentado y se avisa.
Ambas funciones devuelven (codigo, advertencias).
"""
import ast
import io
import re
import tokenize

LANG = "es"  # idioma de advertencias y marcas; el codigo fuente de los mensajes esta en español
# fragmentos fijos es -> en (los más largos primero); las partes dinámicas (código del usuario) no se tocan
EN = [
    ("Missing: en Stata '.' es mayor que cualquier número (x > 5 es verdadero si x es missing); en pandas NaN > 5 es False. Revisar:",
     "Missing values: in Stata '.' is greater than any number (x > 5 is true if x is missing); in pandas NaN > 5 is False. Check:"),
    ("). Alternativas: lasso/elasticnet (Stata 16+), el paquete pystacked (SSC), o ejecutar el código original dentro de un bloque python: ... end (Stata 16+).",
     "). Alternatives: lasso/elasticnet (Stata 16+), the pystacked package (SSC), or run the original code inside a python: ... end block (Stata 16+)."),
    ("Stata no tiene machine learning nativo", "Stata has no native machine learning"),
    ("Resultados r()/e() no traducidos en:", "r()/e() results not translated in:"),
    ("_n/_N dentro de una expresión no se traduce automáticamente:", "_n/_N inside an expression is not translated automatically:"),
    ("Ponderadores [aweight/fweight/...] ignorados; usar", "Weights [aweight/fweight/...] ignored; use"),
    ("xtreg sin xtset previo: definir el índice (id, tiempo) con", "xtreg without a prior xtset: define the (id, time) index with"),
    ("merge m:m no tiene equivalente directo (Stata lo desaconseja); revisar el resultado",
     "merge m:m has no direct equivalent (Stata discourages it); check the result"),
    ("Stata solo mantiene un dataset en memoria: las lecturas posteriores reemplazan a la anterior",
     "Stata holds only one dataset in memory: later reads replace the previous one"),
    ("Stata solo tiene un dataset en memoria:", "Stata holds only one dataset in memory:"),
    ("se trata como el dataset activo", "is treated as the active dataset"),
    ("no tiene traducción directa; revisar vce()", "has no direct translation; check vce()"),
    ("merge usa", "merge uses"),
    ("en Stata el archivo 'using' debe estar en formato .dta (import + save antes)",
     "in Stata the 'using' file must be .dta (import + save first)"),
    ("merge: se asumió 1:1; ajustar a m:1 o 1:m según los datos", "merge: 1:1 assumed; adjust to m:1 or 1:m according to your data"),
    ("El código Python no es válido (línea", "The Python code is not valid (line"),
    (" — equivalente sugerido: ", " — suggested equivalent: "),
    ("# TODO (sin traducir): ", "# TODO (not translated): "),
    ("TODO bloque sin traducir:", "TODO untranslated block:"),
    ("No traducido (", "Not translated ("),
    ("No traducido:", "Not translated:"),
    ("Bloque no soportado:", "Unsupported block:"),
    ("Error al traducir", "Error while translating"),
    ("# Traducido de Stata a Python (revisar antes de usar)", "# Translated from Stata to Python (review before use)"),
    ("* Traducido de Python a Stata (revisar antes de usar)", "* Translated from Python to Stata (review before use)"),
    ("(sin equivalente en Stata)", "(no Stata equivalent)"),
    ("guarda los resultados en variables Python", "store results in Python variables"),
    ("WLS/GLM con pesos", "WLS/GLM with weights"),
    ("C(var) en la fórmula", "C(var) in the formula"),
    ("stargazer o statsmodels", "stargazer or statsmodels"),
    ("nombre de columna no constante", "non-constant column name"),
    ("operador unario", "unary operator"),
    ("operador", "operator"),
    ("comparación", "comparison"),
    ("función ", "function "),
    ("atributo ", "attribute "),
    ("for con desempaquetado", "for with unpacking"),
    ("for no soportado", "unsupported for"),
    ("asignación compleja", "complex assignment"),
    ("merge con un DataFrame ya cargado", "merge with an already loaded DataFrame"),
    ("groupby sin columnas explícitas", "groupby without explicit columns"),
    ("agg no soportado", "unsupported agg"),
    ("expresión", "expression"),
]


def tr(m):
    if LANG == "en":
        for es, en in EN:
            m = m.replace(es, en)
    return m


MAC = re.compile(r"`(\w+)'|\$\{(\w+)\}|\$(\w+)")


def _name(m):
    return m.group(1) or m.group(2) or m.group(3)


def q(s):
    """Texto Stata -> literal Python (f-string si hay macros, que se expanden como texto)."""
    t = MAC.sub(lambda m: "{" + _name(m) + "}", s)
    return ("f" if t != s else "") + repr(t)


def bare(s):
    return MAC.sub(_name, s)


def split_opts(s):
    """'cuerpo, opciones' -> (cuerpo, opciones), ignorando comas dentro de () o comillas."""
    d, qt = 0, False
    for i, c in enumerate(s):
        if c == '"':
            qt = not qt
        elif not qt:
            if c == "(":
                d += 1
            elif c == ")":
                d -= 1
            elif c == "," and d == 0:
                return s[:i].strip(), s[i + 1:].strip()
    return s.strip(), ""


def split_if(s):
    p = re.split(r"\s+if\s+", " " + s, maxsplit=1)
    return p[0].strip(), (p[1].strip() if len(p) > 1 else "")


# ============================================================ Stata -> Python

AB = {"g": "generate", "ge": "generate", "gen": "generate", "sum": "summarize", "su": "summarize",
      "summ": "summarize", "tab": "tabulate", "ta": "tabulate", "reg": "regress", "regr": "regress",
      "cap": "capture", "qui": "quietly", "noi": "noisily", "di": "display", "dis": "display",
      "disp": "display", "ren": "rename", "des": "describe", "d": "describe", "cor": "correlate",
      "corr": "correlate", "coll": "collapse", "mer": "merge", "app": "append", "rep": "replace",
      "repl": "replace", "l": "list", "li": "list", "hist": "histogram", "scat": "scatter",
      "so": "sort", "sor": "sort", "exp": "export", "imp": "import", "xtr": "xtreg", "ivreg": "ivregress"}
NOOP = {"set", "version", "compress", "format", "order", "label", "log", "cls", "timer", "pause",
        "tempvar", "tempfile", "tempname", "browse", "edit", "program", "end", "matrix", "mata", "notes", "note"}
HINT = {"reshape": "pd.melt / pd.wide_to_long / df.pivot", "esttab": "stargazer o statsmodels summary_col",
        "outreg2": "stargazer o statsmodels summary_col", "estout": "stargazer o statsmodels summary_col",
        "estimates": "guarda los resultados en variables Python", "margins": "res.get_margeff()",
        "lasso": "sklearn.linear_model.LassoCV", "elasticnet": "sklearn.linear_model.ElasticNetCV",
        "svy": "WLS/GLM con pesos (statsmodels)", "svyset": "WLS/GLM con pesos (statsmodels)",
        "mi": "sklearn.impute.IterativeImputer", "twoway": "matplotlib", "graph": "matplotlib",
        "bootstrap": "numpy.random.choice / sklearn.utils.resample", "test": "res.f_test / res.wald_test",
        "estat": "statsmodels.stats.diagnostic", "ml": "scipy.optimize.minimize",
        "assert": "assert (Python)", "duplicates": "df.drop_duplicates()", "encode": "pd.factorize / astype('category')",
        "destring": "pd.to_numeric", "tostring": "astype(str)", "recode": "df.replace / np.select",
        "preserve": "df.copy()", "restore": "df.copy()", "levelsof": "df[col].unique()", "xi": "C(var) en la fórmula"}
IMP = {"pandas": "import pandas as pd", "numpy": "import numpy as np", "os": "import os",
       "smf": "import statsmodels.formula.api as smf", "scipy": "from scipy import stats",
       "plt": "import matplotlib.pyplot as plt", "fnmatch": "from fnmatch import fnmatch",
       "linearmodels": "from linearmodels import PanelOLS, RandomEffects, IV2SLS"}
MODELS = {"regress": "ols", "logit": "logit", "probit": "probit", "poisson": "poisson"}
EG = {"mean": "mean", "sum": "sum", "total": "sum", "max": "max", "min": "min", "sd": "std",
      "count": "count", "median": "median"}
CST = {"mean": "mean", "sum": "sum", "count": "count", "sd": "std", "median": "median", "p50": "median",
       "min": "min", "max": "max", "first": "first", "last": "last"}


def prep(src):
    # /* ... */ -> lineas "//"; /// une la linea con la siguiente
    src = re.sub(r"/\*(.*?)\*/", lambda m: "\n".join("// " + l for l in m.group(1).splitlines()) + "\n", src, flags=re.S)
    src = re.sub(r"[ \t]*///[^\n]*\n", " ", src)
    return src.splitlines()


class S2P:
    def __init__(s):
        s.imp, s.warns, s.out, s.stack, s.ind, s.panel = {"pandas": 1}, [], [], [], 0, False

    def w(s, m):
        m = tr(m)
        if m not in s.warns:
            s.warns.append(m)

    def emit(s, line):
        s.out.append(("    " * s.ind + line) if line else "")

    # ---- utilidades de expresiones
    def pl(s, toks):
        """Lista de variables -> expresion Python (macros, _all, x*, a-b)."""
        parts = []
        for t in toks:
            m = MAC.fullmatch(t)
            if m:
                parts.append(f"*{_name(m)}.split()")
            elif t in ("_all", "*"):
                parts.append("*df.columns")
            elif "*" in t or "?" in t:
                s.imp["fnmatch"] = 1
                parts.append(f"*[c for c in df.columns if fnmatch(c, {t!r})]")
            elif re.fullmatch(r"\w+-\w+", t):
                a, b = t.split("-")
                parts.append(f'*df.loc[:, {a!r}:{b!r}].columns')
            else:
                parts.append(q(t))
        return "[" + ", ".join(parts) + "]"

    def formula(s, y, xs, extra=""):
        parts, f = [], False
        for t in xs:
            m = MAC.fullmatch(t)
            if m:
                parts.append("{" + _name(m) + ".replace(' ', ' + ')}")
                f = True
                continue
            t = re.sub(r"\bib(\d+)\.(\w+)", r"C(\2, Treatment(reference=\1))", t)
            t = re.sub(r"\bi\.(\w+)", r"C(\1)", t)
            t = re.sub(r"\bc\.", "", t).replace("##", "*").replace("#", ":")
            parts.append(t)
        txt = f"{y} ~ " + (" + ".join(parts) if parts else "1") + extra
        return ("f" if f else "") + repr(txt)

    def pyx(s, x):
        """Expresion escalar Stata -> Python (condiciones, locals, display)."""
        x = bare(x.strip())
        if re.search(r"\b[re]\(", x):
            s.w(f"Resultados r()/e() no traducidos en: {x}")
        x = re.sub(r"\b_N\b", "len(df)", x)
        x = x.replace("~=", "!=").replace("^", "**")
        x = re.sub(r"!(?!=)", " not ", x)
        x = re.sub(r"\s*&\s*", " and ", x)
        x = re.sub(r"\s*\|\s*", " or ", x)
        if re.search(r"\b(ln|log|sqrt|exp)\(", x):
            s.imp["numpy"] = 1
            x = re.sub(r"\b(?:ln|log)\(", "np.log(", x)
            x = re.sub(r"\b(sqrt|exp)\(", r"np.\1(", x)
        return x.strip()

    def E(s, e):
        if ">" in e:
            s.w(f"Missing: en Stata '.' es mayor que cualquier número (x > 5 es verdadero si x es missing); "
                f"en pandas NaN > 5 es False. Revisar: {e}")
        e = re.sub(r"(\w+)\s*==\s*\.(?![\w.])", r"\1.isna()", e)
        e = re.sub(r"(\w+)\s*!=\s*\.(?![\w.])", r"\1.notna()", e)
        e = re.sub(r"\bmissing\((\w+)\)", r"\1.isna()", e)
        e = re.sub(r"\binlist\((\w+),([^)]*)\)", r"\1.isin([\2])", e)
        e = re.sub(r"\binrange\((\w+),([^,]*),([^)]*)\)", r"\1.between(\2,\3)", e)
        e = re.sub(r"\bln\(", "log(", e).replace("~=", "!=")
        e = re.sub(r"!(?!=)", "~", e).replace("^", "**")
        return f'df.eval({q(e)}, engine="python")'

    def D(s, cond):
        return f"df[{s.E(cond)}]" if cond else "df"

    def unknown(s, st):
        c = st.split()[0]
        h = HINT.get(AB.get(c, c))
        s.w(f"No traducido: «{st[:70]}»" + (f" — equivalente sugerido: {h}" if h else ""))
        return [tr("# TODO (sin traducir): ") + st]

    # ---- una linea de comando -> lista de lineas Python
    def cmd(s, st, by=None):
        m = re.match(r"(bysort|bys|by)\s+([^:(]+?)\s*(?:\(([^)]*)\))?\s*:\s*(.*)$", st)
        if m:
            by = m.group(2).split()
            pre = [f"df = df.sort_values({s.pl(by + (m.group(3) or '').split())})"] if m.group(1) != "by" else []
            return pre + s.cmd(m.group(4), by)
        w = st.split(None, 1)
        c = AB.get(w[0], w[0])
        rest = w[1] if len(w) > 1 else ""
        if c in ("quietly", "noisily"):
            return s.cmd(rest.lstrip(": "), by)
        if c == "capture":
            return ["try:"] + ["    " + l for l in s.cmd(rest.lstrip(": "), by)] + ["except Exception:", "    pass"]
        if c in NOOP:
            if c == "set" and rest.startswith("seed"):
                s.imp["numpy"] = 1
                return [f"np.random.seed({rest.split()[1]})"]
            return ["# " + st]
        h = getattr(s, "c_" + c, None)
        return h(rest, by) if h else s.unknown(st)

    @staticmethod
    def fn(a, ext=".dta"):
        a = a.strip()
        if a.startswith("using "):
            a = a[6:].strip()
        a = a.strip('"')
        if ext and not re.search(r"\.\w+$", a):
            a += ext
        return q(a)

    def c_use(s, r, by):
        b, _ = split_opts(r)
        if " using " in b:
            v, b = b.split(" using ", 1)
            return [f"df = pd.read_stata({s.fn(b)}, columns={s.pl(v.split())})"]
        return [f"df = pd.read_stata({s.fn(b)})"]

    def c_import(s, r, by):
        kind, _, r = r.partition(" ")
        b, o = split_opts(r)
        f = s.fn(b, "")
        if kind == "delimited":
            m = re.search(r'delim\w*\("?(.)"?\)', o)
            return [f"df = pd.read_csv({f}" + (f", sep={m.group(1)!r}" if m else "") + ")"]
        if kind == "excel":
            m = re.search(r'sheet\("([^"]+)"\)', o)
            return [f"df = pd.read_excel({f}" + (f", sheet_name={m.group(1)!r}" if m else "")
                    + ("" if "firstrow" in o else ", header=None") + ")"]
        return s.unknown("import " + kind + " " + r)

    def c_save(s, r, by):
        return [f"df.to_stata({s.fn(split_opts(r)[0])}, write_index=False)"]

    def c_export(s, r, by):
        kind, _, r = r.partition(" ")
        f = s.fn(split_opts(r)[0], "")
        if kind == "delimited":
            return [f"df.to_csv({f}, index=False)"]
        if kind == "excel":
            return [f"df.to_excel({f}, index=False)"]
        return s.unknown("export " + kind + " " + r)

    def c_clear(s, r, by):
        return ["df = pd.DataFrame()"]

    def c_cd(s, r, by):
        s.imp["os"] = 1
        return [f"os.chdir({q(r.strip().strip(chr(34)))})"]

    def c_generate(s, r, by):
        e, cond = split_if(split_opts(r)[0])
        m = re.match(r"(?:(?:byte|int|long|float|double|str\d*)\s+)?(\S+?)\s*=\s*(.*)$", e)
        if not m:
            return s.unknown("generate " + r)
        v, x = m.groups()
        t, g = q(v), (s.pl(by) if by else None)
        sm = re.fullmatch(r"sum\((\w+)\)", x)
        if x == "_n":
            if g:
                rhs = f"df.groupby({g}).cumcount() + 1"
            else:
                s.imp["numpy"] = 1
                rhs = "np.arange(1, len(df) + 1)"
        elif x == "_N":
            rhs = f'df.groupby({g})[{q(by[0])}].transform("size")' if g else "len(df)"
        elif sm:
            rhs = (f"df.groupby({g})[{q(sm.group(1))}].cumsum()" if g else f"df[{q(sm.group(1))}].cumsum()")
        elif by:
            return s.unknown("by: generate " + r)
        elif x.strip() == ".":
            s.imp["numpy"] = 1
            rhs = "np.nan"
        else:
            if re.search(r"\b_[nN]\b", x):
                s.w(f"_n/_N dentro de una expresión no se traduce automáticamente: {x}")
            rhs = s.E(x)
        return [f"df.loc[{s.E(cond)}, {t}] = {rhs}" if cond else f"df[{t}] = {rhs}"]

    c_replace = c_generate

    def c_egen(s, r, by):
        b, o = split_opts(r)
        m = re.match(r"(?:\w+\s+)?(\S+?)\s*=\s*(\w+)\((.*)\)\s*$", split_if(b)[0])
        if not m:
            return s.unknown("egen " + r)
        v, f, a = m.groups()
        g = re.search(r"by\(([^)]*)\)", o)
        gb = g.group(1).split() if g else by
        if f in ("rowtotal", "rowmean"):
            return [f"df[{q(v)}] = df[{s.pl(a.split())}].{'sum' if f == 'rowtotal' else 'mean'}(axis=1)"]
        if f not in EG:
            return s.unknown("egen " + r)
        if gb:
            return [f'df[{q(v)}] = df.groupby({s.pl(gb)})[{q(a)}].transform("{EG[f]}")']
        return [f"df[{q(v)}] = df[{q(a)}].{EG[f]}()"]

    def c_drop(s, r, by):
        b, cond = split_if(split_opts(r)[0])
        if cond:
            return [f"df = df[~{s.E(cond)}]"]
        if re.match(r"in\b", b):
            return s.unknown("drop " + r)
        return [f"df = df.drop(columns={s.pl(b.split())})"]

    def c_keep(s, r, by):
        b, cond = split_if(split_opts(r)[0])
        if cond:
            return [f"df = df[{s.E(cond)}]"]
        if re.match(r"in\b", b):
            return s.unknown("keep " + r)
        return [f"df = df[{s.pl(b.split())}]"]

    def c_rename(s, r, by):
        t = r.split()
        if len(t) != 2:
            return s.unknown("rename " + r)
        return [f"df = df.rename(columns={{{q(t[0])}: {q(t[1])}}})"]

    def c_sort(s, r, by):
        return [f"df = df.sort_values({s.pl(r.split())})"]

    def c_gsort(s, r, by):
        t = r.split()
        return [f"df = df.sort_values({s.pl([x.lstrip('+-') for x in t])}, ascending={[not x.startswith('-') for x in t]})"]

    def c_summarize(s, r, by):
        b, cond = split_if(split_opts(r)[0])
        return [f"print({s.D(cond)}{'[' + s.pl(b.split()) + ']' if b else ''}.describe())"]

    def c_describe(s, r, by):
        return ["df.info()"]

    def c_count(s, r, by):
        return [f"print(len({s.D(split_if(r)[1])}))"]

    def c_list(s, r, by):
        b, cond = split_if(split_opts(r)[0])
        n = re.search(r"\bin\s+1/(\d+)", b)
        b = re.sub(r"\bin\s+\S+", "", b).strip()
        d = s.D(cond) + (f"[{s.pl(b.split())}]" if b else "")
        return [f"print({d}.head({n.group(1)}))" if n else f"print({d}.to_string())"]

    def c_tabulate(s, r, by):
        b, o = split_opts(r)
        v, cond = split_if(b)
        t, d = v.split(), s.D(cond)
        g = re.search(r"gen\w*\((\w+)\)", o)
        if g and len(t) == 1:
            return [f"df = df.join(pd.get_dummies(df[{q(t[0])}], prefix={g.group(1)!r}).astype(int))"]
        if len(t) == 1:
            return [f"print({d}[{q(t[0])}].value_counts(dropna=False))"]
        if len(t) == 2:
            return [f"print(pd.crosstab({d}[{q(t[0])}], {d}[{q(t[1])}]))"]
        return s.unknown("tabulate " + r)

    def c_correlate(s, r, by):
        v = split_opts(r)[0].split()
        return [f"print(df[{s.pl(v)}].corr())" if v else "print(df.corr(numeric_only=True))"]

    c_pwcorr = c_correlate

    def c_ttest(s, r, by):
        s.imp["scipy"] = 1
        b, o = split_opts(r)
        g = re.search(r"by\((\w+)\)", o)
        m = re.match(r"(\w+)\s*==\s*(-?[\d.]+)", b)
        if g:
            return [f'print(stats.ttest_ind(*[x[{q(b)}].dropna() for _, x in df.groupby({q(g.group(1))})]))']
        if m:
            return [f"print(stats.ttest_1samp(df[{q(m.group(1))}].dropna(), {m.group(2)}))"]
        return s.unknown("ttest " + r)

    def model(s, c, r, by):
        s.imp["smf"] = 1
        b, o = split_opts(r)
        b = re.sub(r"\[.*?\]", "", b)
        if "[" in r:
            s.w("Ponderadores [aweight/fweight/...] ignorados; usar smf.wls(..., weights=)")
        v, cond = split_if(b)
        t = v.split()
        if not t:
            return s.unknown(c + " " + r)
        f = s.formula(t[0], t[1:], " - 1" if re.search(r"\bnocons", o) else "")
        d, fit = s.D(cond), MODELS[c]
        cl = re.search(r"(?:vce\(cluster\s+|cluster\()(\w+)\)", o)
        hc = "HC1" if c == "regress" else "HC0"
        if cl:
            return [f"model = smf.{fit}({f}, data={d})",
                    f'res = model.fit(cov_type="cluster", cov_kwds={{"groups": df.loc[model.data.row_labels, {cl.group(1)!r}]}})',
                    "print(res.summary())"]
        rb = re.search(r"\brobust\b|vce\((?:robust|hc\d)\)", o)
        return [f'res = smf.{fit}({f}, data={d}).fit({f"cov_type={hc!r}" if rb else ""})', "print(res.summary())"]

    c_regress = lambda s, r, by: s.model("regress", r, by)
    c_logit = lambda s, r, by: s.model("logit", r, by)
    c_probit = lambda s, r, by: s.model("probit", r, by)
    c_poisson = lambda s, r, by: s.model("poisson", r, by)

    def c_xtset(s, r, by):
        t = split_opts(r)[0].split()
        s.panel = True
        return [f"df = df.set_index({s.pl(t[:2])}, drop=False)  # panel: (id, tiempo)"]

    def c_xtreg(s, r, by):
        s.imp["linearmodels"] = 1
        b, o = split_opts(r)
        t = split_if(b)[0].split()
        if not s.panel:
            s.w("xtreg sin xtset previo: definir el índice (id, tiempo) con df.set_index")
        fe = re.search(r"\bfe\b", o)
        f = s.formula(t[0], t[1:], " + EntityEffects" if fe else "")
        cls = "PanelOLS" if fe else "RandomEffects"
        if not fe:
            f = f.replace(" ~ ", " ~ 1 + ", 1)
        cov = ('cov_type="clustered", cluster_entity=True' if re.search(r"cluster", o)
               else 'cov_type="robust"' if "robust" in o else "")
        return [f"res = {cls}.from_formula({f}, data=df).fit({cov})", "print(res)"]

    def c_ivregress(s, r, by):
        s.imp["linearmodels"] = 1
        b, o = split_opts(r)
        m = re.match(r"2sls\s+(\w+)\s+([^(]*)\((.*?)=(.*?)\)\s*$", b)
        if not m:
            return s.unknown("ivregress " + r)
        y, ex, en, iv = m.groups()
        ex = " + ".join(["1"] + ex.split())
        cov = 'cov_type="robust"' if "robust" in o else ""
        return [f'res = IV2SLS.from_formula("{y} ~ {ex} + [{en.strip()} ~ {" + ".join(iv.split())}]", df).fit({cov})', "print(res)"]

    def c_predict(s, r, by):
        b, o = split_opts(r)
        return [f"df[{q(b.split()[0])}] = res.{'resid' if 'resid' in o else 'predict(df)'}"]

    def c_merge(s, r, by):
        m = re.match(r"(1:1|m:1|1:m|m:m)\s+(.*?)\s+using\s+(.*)$", r.strip())
        if not m:
            return s.unknown("merge " + r)
        rel, keys, rest = m.groups()
        b, o = split_opts(rest)
        k = re.search(r"keep\(([^)]*)\)", o)
        kv = set(k.group(1).split()) if k else set()
        how = ("outer" if not k else "inner" if kv <= {"match", "3"} else "left" if kv <= {"master", "match", "1", "3"}
               else "right" if kv <= {"using", "match", "2", "3"} else "outer")
        ind = "" if re.search(r"nogen", o) else ', indicator="_merge"'
        val = "" if rel == "m:m" else f', validate="{rel}"'
        if rel == "m:m":
            s.w("merge m:m no tiene equivalente directo (Stata lo desaconseja); revisar el resultado")
        return [f"df = df.merge(pd.read_stata({s.fn(b)}), on={s.pl(keys.split())}, how={how!r}{val}{ind})"]

    def c_append(s, r, by):
        return [f"df = pd.concat([df, pd.read_stata({s.fn(split_opts(r)[0])})], ignore_index=True)"]

    def c_collapse(s, r, by):
        b, o = split_opts(r)
        g = re.search(r"by\(([^)]*)\)", o)
        if not g:
            return s.unknown("collapse " + r)
        aggs, stat = [], "mean"
        for i, ch in enumerate(re.split(r"\((\w+)\)", b)):
            if i % 2:
                stat = CST.get(ch, ch)
                continue
            for tok in ch.split():
                new, _, old = tok.partition("=")
                aggs.append(f'{new}=({q(old or new)}, "{stat}")')
        return [f"df = df.groupby({s.pl(g.group(1).split())}, as_index=False).agg({', '.join(aggs)})"]

    def c_display(s, r, by):
        r = re.sub(r"\bas \w+\b|_newline|_continue", "", r).strip()
        parts = [q(p[1:-1]) if p.startswith('"') else s.pyx(p)
                 for p in (x.strip() for x in re.split(r'("[^"]*")', r)) if p]
        return [f"print({', '.join(parts)})"]

    def c_local(s, r, by):
        m = re.match(r"(\w+)\s*(=)?\s*(.*)$", r.strip())
        if not m:
            return s.unknown("local " + r)
        n, eq, v = m.groups()
        if eq:
            return [f"{n} = {s.pyx(v)}"]
        v = v.strip().strip('"')
        return [f"{n} = {v}" if re.fullmatch(r"-?\d+(\.\d+)?", v) else f"{n} = {q(v)}"]

    c_global = c_scalar = c_local

    def c_histogram(s, r, by):
        s.imp["plt"] = 1
        return [f"df[{q(split_opts(r)[0].split()[0])}].plot.hist()", "plt.show()"]

    def c_scatter(s, r, by):
        s.imp["plt"] = 1
        t = split_opts(r)[0].split()
        return [f"df.plot.scatter(x={q(t[1])}, y={q(t[0])})", "plt.show()"]

    # ---- bloques
    def foreach(s, a):
        m = re.match(r"(\w+)\s+(in|of\s+\w+)\s+(.*)$", a)
        if not m:
            return None
        v, kind, items = m.groups()
        kind = re.sub(r"\s+", " ", kind)
        t = items.split()
        if kind == "in":
            it = ("[" + ", ".join(t) + "]") if all(re.fullmatch(r"-?\d+(\.\d+)?", x) for x in t) else s.pl(t)
        elif kind == "of local" or kind == "of global":
            it = f"{bare(items.strip())}.split()"
        elif kind == "of numlist":
            r = re.fullmatch(r"(\d+)/(\d+)", items.strip())
            it = f"range({r.group(1)}, {int(r.group(2)) + 1})" if r else "[" + ", ".join(t) + "]"
        else:
            it = s.pl(t)
        return f"for {v} in {it}:"

    def forvalues(s, a):
        m = re.match(r"(\w+)\s*=\s*([^/()\s]+)(?:/|\(([^)]+)\))([^/()\s]+)$", a)
        if not m:
            return None
        v, a0, st, b0 = m.groups()
        a0, b0 = bare(a0), bare(b0)
        if st and st.startswith("-"):
            return f"for {v} in range({a0}, {int(b0) - 1 if b0.lstrip('-').isdigit() else b0 + ' - 1'}, {st}):"
        end = int(b0) + 1 if b0.lstrip("-").isdigit() else b0 + " + 1"
        return f"for {v} in range({a0}, {end}" + (f", {st})" if st else ")") + ":"

    def open(s, h):
        k, _, a = h.partition(" ")
        a = a.strip()
        kind = None
        if k == "foreach":
            line = s.foreach(a)
        elif k in ("forvalues", "forval", "forvalue"):
            line = s.forvalues(a)
        elif k in ("if", "while"):
            line = f"{k} {s.pyx(a)}:"
        elif k == "else":
            line = f"elif {s.pyx(a[2:])}:" if a.startswith("if ") else "else:"
        elif k in ("quietly", "qui", "noisily", "noi"):
            line = "if True:  # " + k
        elif k in ("capture", "cap"):
            line, kind = "try:", "try"
        else:
            line = None
        if line is None:
            s.w(f"Bloque no soportado: «{h[:60]}»")
            line = "if True:  # " + tr("TODO bloque sin traducir:") + " " + h
        s.emit(line)
        s.stack.append(kind)
        s.ind += 1

    def close(s):
        kind = s.stack.pop() if s.stack else None
        real = [l for l in reversed(s.out) if l.strip() and not l.strip().startswith("#")]
        if real and real[0].endswith(":"):
            s.emit("pass")
        s.ind = max(0, s.ind - 1)
        if kind == "try":
            s.emit("except Exception:")
            s.emit("    pass")

    def run(s, src):
        for raw in prep(src):
            st = raw.strip()
            if not st:
                s.out.append("")
                continue
            if st.startswith(("*", "//")):
                t = st.lstrip("*/ ").rstrip()
                s.emit("# " + t if t else "#")
                continue
            m = re.search(r"\s//\s?(.*)$", st)
            cm = ""
            if m:
                st, cm = st[:m.start()].strip(), "  # " + m.group(1)
                if not st:
                    s.emit("# " + m.group(1))
                    continue
            if st.startswith("}"):
                s.close()
                st = st[1:].strip()
                if not st:
                    continue
            if st.endswith("{"):
                s.open(st[:-1].strip())
                if cm:
                    s.out[-1] += cm
                continue
            try:
                lines = s.cmd(st)
            except Exception as e:  # una linea mala no debe tumbar todo
                lines = s.unknown(st)
                s.w(f"Error al traducir «{st[:50]}»: {e}")
            for i, l in enumerate(lines):
                s.emit(l + (cm if i == 0 else ""))
        while s.stack:
            s.close()
        head = [tr("# Traducido de Stata a Python (revisar antes de usar)")] + [IMP[k] for k in IMP if k in s.imp]
        return "\n".join(head + ["", *s.out]).rstrip() + "\n", s.warns


def stata_to_python(src, lang="es"):
    global LANG
    LANG = lang
    return S2P().run(src)


# ============================================================ Python -> Stata

ML = {"sklearn", "torch", "tensorflow", "keras", "xgboost", "lightgbm", "catboost", "transformers"}
QUIET = {"pandas", "numpy", "statsmodels", "matplotlib", "os", "sys", "warnings", "scipy", "seaborn", "linearmodels"}
BIN = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Pow: "^", ast.BitAnd: "&", ast.BitOr: "|"}
CMP = {ast.Eq: "==", ast.NotEq: "!=", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}
FUN = {"log": "ln", "log10": "log10", "exp": "exp", "sqrt": "sqrt", "abs": "abs", "floor": "floor", "ceil": "ceil",
       "sin": "sin", "cos": "cos", "tan": "tan", "int": "int", "max": "max", "min": "min", "maximum": "max",
       "minimum": "min", "str": "string"}
STR = {"upper": "upper", "lower": "lower", "strip": "trim", "len": "strlen"}
AGG = {"mean": "r(mean)", "std": "r(sd)", "sum": "r(sum)", "min": "r(min)", "max": "r(max)", "count": "r(N)",
       "var": "r(Var)", "median": "r(p50)"}
STAT = {"std": "sd", "sum": "sum", "mean": "mean", "count": "count", "median": "median", "min": "min", "max": "max",
        "first": "first", "last": "last"}
MODS = {"ols": "regress", "logit": "logit", "probit": "probit", "poisson": "poisson"}
ML_MSG = ("Stata no tiene machine learning nativo ('{}'). Alternativas: lasso/elasticnet (Stata 16+), "
          "el paquete pystacked (SSC), o ejecutar el código original dentro de un bloque python: ... end (Stata 16+).")


class U(Exception):
    """Construccion Python sin equivalente automatico."""


class P2S:
    def __init__(s, src):
        s.src, s.out, s.ind, s.warns = src, [], 0, []
        s.made, s.seen, s.models, s.fits = set(), set(), {}, set()
        s.frames, s.bare, s.reads, s.tmp = {"df", "data"}, False, 0, 0
        s.cm = {t.start[0]: t.string.lstrip("# ").rstrip()
                for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.COMMENT}

    def w(s, m):
        m = tr(m)
        if m not in s.warns:
            s.warns.append(m)

    def emit(s, line):
        s.out.append(("    " * s.ind + line) if line else "")

    def flush(s, upto):
        for ln in sorted(l for l in s.cm if l < upto):
            s.emit("* " + s.cm.pop(ln))

    # ---- expresiones
    def isframe(s, n):
        return isinstance(n, ast.Name) and n.id in s.frames

    def col(s, sl):
        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
            return sl.value
        if isinstance(sl, ast.Name):
            return f"`{sl.id}'"
        if isinstance(sl, ast.JoinedStr):
            return "".join(p.value if isinstance(p, ast.Constant) else f"`{p.value.id}'" for p in sl.values)
        raise U("nombre de columna no constante")

    def names(s, n):
        if isinstance(n, (ast.List, ast.Tuple)):
            return [s.col(e) for e in n.elts]
        return [s.col(n)]

    def p(s, n):
        e = s.ex(n)
        return f"({e})" if isinstance(n, (ast.BinOp, ast.BoolOp, ast.Compare)) else e

    def ex(s, n):
        T = type(n)
        if T is ast.Constant:
            v = n.value
            if isinstance(v, str):
                return '"' + v.replace('"', "'") + '"'
            if v is None or (isinstance(v, float) and v != v):
                return "."
            return str(int(v)) if isinstance(v, bool) else repr(v)
        if T is ast.Name:
            return n.id if s.bare else f"`{n.id}'"
        if T is ast.Subscript and s.isframe(n.value):
            c = s.col(n.slice)
            s.seen.add(c)
            return c
        if T is ast.Attribute:
            if n.attr == "nan":
                return "."
            if n.attr == "pi":
                return "_pi"
            if s.isframe(n.value):
                s.seen.add(n.attr)
                return n.attr
            raise U("atributo " + n.attr)
        if T is ast.BinOp:
            a, b = s.p(n.left), s.p(n.right)
            if type(n.op) is ast.Mod:
                return f"mod({a}, {b})"
            if type(n.op) is ast.FloorDiv:
                return f"floor({a} / {b})"
            if type(n.op) in BIN:
                return f"{a} {BIN[type(n.op)]} {b}"
            raise U("operador")
        if T is ast.UnaryOp:
            o = {ast.Not: "!", ast.Invert: "!", ast.USub: "-", ast.UAdd: ""}.get(type(n.op))
            if o is None:
                raise U("operador unario")
            return o + s.p(n.operand)
        if T is ast.BoolOp:
            return (" & " if type(n.op) is ast.And else " | ").join(s.p(v) for v in n.values)
        if T is ast.Compare:
            out, left = [], n.left
            for op, right in zip(n.ops, n.comparators):
                if type(op) in (ast.In, ast.NotIn) and isinstance(right, (ast.List, ast.Tuple)):
                    t = f"inlist({s.ex(left)}, {', '.join(s.ex(e) for e in right.elts)})"
                    out.append(t if type(op) is ast.In else "!" + t)
                elif type(op) in CMP:
                    out.append(f"{s.p(left)} {CMP[type(op)]} {s.p(right)}")
                else:
                    raise U("comparación")
                left = right
            return " & ".join(f"({x})" for x in out) if len(out) > 1 else out[0]
        if T is ast.Call:
            return s.call(n)
        raise U(type(n).__name__)

    def call(s, n):
        f, a = n.func, n.args
        name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
        base = f.value if isinstance(f, ast.Attribute) else None
        mod = base is None or (isinstance(base, ast.Name) and base.id in ("np", "numpy", "math", "pd"))
        if mod and name in ("round",) and a:
            k = a[1].value if len(a) > 1 and isinstance(a[1], ast.Constant) else 0
            return f"round({s.ex(a[0])}" + (f", {10.0 ** -k:g})" if k else ")")
        if mod and name == "where" and len(a) == 3:
            return f"cond({s.ex(a[0])}, {s.ex(a[1])}, {s.ex(a[2])})"
        if mod and name in ("isna", "isnull", "isnan") and a:
            return f"missing({s.ex(a[0])})"
        if mod and name == "len" and a:
            return "_N"
        if mod and name in FUN and a:
            return f"{FUN[name]}({', '.join(s.ex(x) for x in a)})"
        if base is not None and name in ("isna", "isnull"):
            return f"missing({s.ex(base)})"
        if base is not None and name in ("notna", "notnull"):
            return f"!missing({s.ex(base)})"
        if base is not None and name == "between" and len(a) == 2:
            return f"inrange({s.ex(base)}, {s.ex(a[0])}, {s.ex(a[1])})"
        if base is not None and name == "isin" and isinstance(a[0], (ast.List, ast.Tuple)):
            return f"inlist({s.ex(base)}, {', '.join(s.ex(e) for e in a[0].elts)})"
        if base is not None and name in ("abs", "round") and not a:
            return f"{name}({s.ex(base)})"
        if isinstance(base, ast.Attribute) and base.attr == "str" and name in STR:
            return f"{STR[name]}({s.ex(base.value)})"
        raise U("función " + str(name))

    def cond(s, node):
        """Expresion donde los nombres son columnas (strings de query / formulas)."""
        s.bare = True
        try:
            return s.ex(node)
        finally:
            s.bare = False

    def condstr(s, txt):
        return s.cond(ast.parse(txt.strip(), mode="eval").body)

    def val(s, n, pre):
        """Valor escalar; agregados de columna generan un summarize previo."""
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in AGG and not n.args
                and isinstance(n.func.value, ast.Subscript) and s.isframe(n.func.value.value)):
            c = s.col(n.func.value.slice)
            pre.append(f"quietly summarize {c}" + (", detail" if n.func.attr == "median" else ""))
            return AGG[n.func.attr]
        return s.ex(n)

    # ---- sentencias
    def body(s, stmts):
        for n in stmts:
            s.flush(n.lineno)
            try:
                s.stmt(n)
            except U as e:
                seg = ast.get_source_segment(s.src, n) or ""
                for l in seg.splitlines():
                    s.emit("* PYTHON: " + l)
                for ln in range(n.lineno, getattr(n, "end_lineno", n.lineno) + 1):
                    s.cm.pop(ln, None)
                s.w(f"No traducido ({e}): «{seg.splitlines()[0][:70] if seg else ''}»")

    def block(s, stmts):
        s.ind += 1
        s.body(stmts)
        s.ind -= 1

    def lines(s, ls):
        for l in ls:
            s.emit(l)

    def stmt(s, n):
        T = type(n)
        if T in (ast.Import, ast.ImportFrom):
            mods = [a.name for a in n.names] if T is ast.Import else [n.module or ""]
            for m in mods:
                top = m.split(".")[0]
                if top in ML:
                    s.w(ML_MSG.format(top))
                    s.emit(f"* import {m}   " + tr("(sin equivalente en Stata)"))
                elif top not in QUIET:
                    s.emit(f"* import {m}")
        elif T is ast.Pass:
            pass
        elif T is ast.Expr:
            s.expr(n.value)
        elif T is ast.Assign and len(n.targets) == 1:
            s.assign(n.targets[0], n.value)
        elif T is ast.AugAssign and isinstance(n.target, ast.Name) and type(n.op) in BIN:
            s.emit(f"local {n.target.id} = `{n.target.id}' {BIN[type(n.op)]} {s.p(n.value)}")
        elif T is ast.For:
            s.loop(n)
        elif T is ast.If:
            s.If(n)
        elif T is ast.While:
            h = f"while {s.ex(n.test)} {{"
            s.emit(h)
            s.block(n.body)
            s.emit("}")
        else:
            raise U(T.__name__)

    def If(s, n, first=True):
        s.emit(("if " if first else "} else if ") + s.ex(n.test) + " {")
        s.block(n.body)
        o = n.orelse
        if len(o) == 1 and isinstance(o[0], ast.If):
            return s.If(o[0], False)
        if o:
            s.emit("} else {")
            s.block(o)
        s.emit("}")

    def loop(s, n):
        if not isinstance(n.target, ast.Name):
            raise U("for con desempaquetado")
        v, it = n.target.id, n.iter
        if isinstance(it, (ast.List, ast.Tuple)) and all(isinstance(e, ast.Constant) for e in it.elts):
            h = f"foreach {v} in {' '.join(str(e.value) for e in it.elts)} {{"
        elif isinstance(it, ast.Call) and getattr(it.func, "id", "") == "range" and 1 <= len(it.args) <= 3:
            r = [s.ex(x) for x in it.args]
            lo, hi, st = ("0", r[0], None) if len(r) == 1 else (r[0], r[1], r[2] if len(r) == 3 else None)
            neg = st is not None and st.startswith("-")
            last = f"`={hi}{'+' if neg else '-'}1'" if not hi.lstrip("-").isdigit() else str(int(hi) + (1 if neg else -1))
            h = f"forvalues {v} = {lo}" + (f"({st})" if st else "/") + f"{last} {{"
        elif isinstance(it, ast.Attribute) and it.attr == "columns":
            h = f"foreach {v} of varlist _all {{"
        else:
            raise U("for no soportado")
        s.emit(h)
        s.block(n.body)
        s.emit("}")

    def setvar(s, c, v, cond=None):
        pre = []
        if isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute):
            f, a = v.func, v.args
            # df.groupby(g)["x"].transform("mean")
            if f.attr == "transform" and a and isinstance(f.value, ast.Subscript) and isinstance(f.value.value, ast.Call):
                g = f.value.value
                if getattr(g.func, "attr", "") == "groupby" and isinstance(a[0], ast.Constant):
                    fn = {"std": "sd", "sum": "total"}.get(a[0].value, a[0].value)
                    return s.emit(f"bysort {' '.join(s.names(g.args[0]))}: egen {c} = {fn}({s.col(f.value.slice)})")
            if f.attr == "predict" and isinstance(f.value, ast.Name) and f.value.id in s.fits:
                return s.emit(f"predict {c}")
            if f.attr in ("sum", "mean") and any(k.arg == "axis" for k in v.keywords) and isinstance(f.value, ast.Subscript):
                return s.emit(f"egen {c} = {'rowtotal' if f.attr == 'sum' else 'rowmean'}({' '.join(s.names(f.value.slice))})")
        if isinstance(v, ast.Attribute) and isinstance(v.value, ast.Name) and v.value.id in s.fits and v.attr in ("resid", "fittedvalues"):
            return s.emit(f"predict {c}" + (", residuals" if v.attr == "resid" else ", xb"))
        x = s.val(v, pre)
        s.lines(pre)
        if cond:
            if c not in s.made and c not in s.seen:
                s.emit(f"generate {c} = " + ('""' if x.startswith('"') else "."))
            s.made.add(c)
            return s.emit(f"replace {c} = {x} if {cond}")
        reuse = c in s.made or c in s.seen
        s.made.add(c)
        s.emit(f"{'replace' if reuse else 'generate'} {c} = {x}")

    def assign(s, t, v):
        if isinstance(t, ast.Subscript) and s.isframe(t.value):
            return s.setvar(s.col(t.slice), v)
        if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Attribute) and t.value.attr == "loc"
                and isinstance(t.slice, ast.Tuple) and len(t.slice.elts) == 2):
            return s.setvar(s.col(t.slice.elts[1]), v, s.ex(t.slice.elts[0]))
        if not isinstance(t, ast.Name):
            raise U("asignación compleja")
        m = s.model(v, t.id)
        if m:
            return
        ls = s.dataop(v)
        if ls is not None:
            if t.id not in s.frames:
                s.frames.add(t.id)
                if t.id != "df":
                    s.w(f"Stata solo tiene un dataset en memoria: '{t.id}' se trata como el dataset activo")
            return s.lines(ls)
        pre = []
        x = s.val(v, pre)
        s.lines(pre)
        s.emit(f"local {t.id} = {x}")

    def expr(s, v):
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            for l in v.value.strip().splitlines():
                s.emit("* " + l.strip())
            return
        if isinstance(v, ast.Call):
            if getattr(v.func, "attr", "") == "summary":
                return  # Stata ya muestra los resultados
            if getattr(v.func, "id", "") == "print":
                return s.lines(s.disp(v.args))
            if s.model(v, None):
                return
            ls = s.dataop(v, stmt=True)
            if ls is not None:
                return s.lines(ls)
        raise U("expresión")

    def disp(s, args):
        pre, items = [], []
        for a in args:
            if isinstance(a, ast.Call) and getattr(a.func, "attr", "") == "summary":
                return []  # Stata ya muestra los resultados
            if isinstance(a, ast.JoinedStr):
                items.append(" ".join(f'"{p.value}"' if isinstance(p, ast.Constant) else s.val(p.value, pre)
                                      for p in a.values))
            else:
                ls = s.dataop(a, stmt=True)
                if ls is not None:
                    return ls
                items.append(s.val(a, pre))
        return pre + ["display " + ' " " '.join(items)]

    # ---- modelos
    def parse_model(s, c):
        f = c.func
        fm = c.args[0] if c.args else next((k.value for k in c.keywords if k.arg == "formula"), None)
        if not (isinstance(f, ast.Attribute) and f.attr in MODS and isinstance(fm, ast.Constant)):
            return None
        cond = ""
        data = c.args[1] if len(c.args) > 1 else next((k.value for k in c.keywords if k.arg == "data"), None)
        if isinstance(data, ast.Subscript) and s.isframe(data.value) and not isinstance(data.slice, (ast.List, ast.Constant)):
            cond = s.ex(data.slice)
        return MODS[f.attr], fm.value, cond

    def term(s, t, pre):
        t = re.sub(r"^I\((.*)\)$", r"\1", t.strip())
        if t in ("1", "0", "-1"):
            return None
        m = re.fullmatch(r"C\((\w+)(?:,\s*Treatment\(reference=(\w+)\))?\)", t)
        if m:
            return f"ib{m.group(2)}.{m.group(1)}" if m.group(2) else f"i.{m.group(1)}"
        if "*" in t or ":" in t:
            sep = "##" if "*" in t else "#"
            return sep.join("c." + (s.term(x, pre) or "") if not x.strip().startswith("C(") else s.term(x, pre)
                            for x in re.split(r"[*:]", t))
        if re.fullmatch(r"[A-Za-z_]\w*", t):
            return t
        s.tmp += 1
        pre.append(f"generate _t{s.tmp} = {s.condstr(t)}")
        return f"_t{s.tmp}"

    def fit(s, kind, formula, cond, kws):
        pre = []
        lhs, rhs = formula.split("~", 1)
        rhs, nocons = re.subn(r"\s*-\s*1\s*$|\s*\+\s*0\s*$|^\s*0\s*\+", "", rhs)
        terms, d, cur = [], 0, ""
        for ch in rhs:  # separar por '+' fuera de parentesis
            d += (ch == "(") - (ch == ")")
            if ch == "+" and d == 0:
                terms.append(cur)
                cur = ""
            else:
                cur += ch
        xs = [x for x in (s.term(t, pre) for t in terms + [cur] if t.strip()) if x]
        y = s.term(lhs, pre)
        opts = ["noconstant"] if nocons else []
        ct = next((k.value.value for k in kws if k.arg == "cov_type" and isinstance(k.value, ast.Constant)), None)
        if ct == "cluster":
            kw = next((k.value for k in kws if k.arg == "cov_kwds"), None)
            if isinstance(kw, ast.Dict) and kw.values and isinstance(kw.values[0], ast.Subscript):
                opts.append(f"vce(cluster {s.col(kw.values[0].slice)})")
        elif ct and ct.startswith("HC"):
            opts.append("vce(robust)")
        elif ct:
            s.w(f"cov_type='{ct}' no tiene traducción directa; revisar vce()")
        return pre + [f"{kind} {y} {' '.join(xs)}" + (f" if {cond}" if cond else "") + (", " + " ".join(opts) if opts else "")]

    def model(s, v, target):
        """smf.ols(...) / .fit(...) / modelo.fit(...). True si lo manejó."""
        if not (isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute)):
            return False
        if v.func.attr == "fit":
            b = v.func.value
            pm = s.models.get(b.id) if isinstance(b, ast.Name) else (s.parse_model(b) if isinstance(b, ast.Call) else None)
            if not pm:
                return False
            s.lines(s.fit(*pm, v.keywords))
            if target:
                s.fits.add(target)
            return True
        pm = s.parse_model(v)
        if pm and target:
            s.models[target] = pm
            return True
        return False

    # ---- operaciones sobre el dataset (devuelven lineas Stata o None)
    def file(s, a):
        return s.col(a.args[0]) if a.args else None

    def dataop(s, v, stmt=False):
        # lecturas
        if isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and isinstance(v.func.value, ast.Name) and v.func.value.id == "pd":
            f, name = s.file(v), v.func.attr
            if name in ("read_csv", "read_excel", "read_stata"):
                s.reads += 1
                if s.reads > 1:
                    s.w("Stata solo mantiene un dataset en memoria: las lecturas posteriores reemplazan a la anterior")
                if name == "read_csv":
                    return [f'import delimited "{f}", clear']
                if name == "read_stata":
                    return [f'use "{f}", clear']
                sh = next((k.value.value for k in v.keywords if k.arg == "sheet_name" and isinstance(k.value, ast.Constant)), None)
                return [f'import excel "{f}"' + (f', sheet("{sh}")' if isinstance(sh, str) else "") + ", firstrow clear"]
            if name == "crosstab" and len(v.args) == 2:
                return [f"tabulate {s.ex(v.args[0])} {s.ex(v.args[1])}"]
            return None
        if not (isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute)):
            return s.plot(v) if isinstance(v, ast.Call) else (s.subset(v) if isinstance(v, ast.Subscript) else None)
        f, a, kw = v.func.attr, v.args, {k.arg: k.value for k in v.keywords}
        b = v.func.value
        if f in ("copy", "reset_index"):
            return s.dataop(b) if not isinstance(b, ast.Name) else []
        if f == "drop":
            cols = kw.get("columns") or (a[0] if a else None)
            if cols is None:
                return None
            return ["drop " + " ".join(s.names(cols))]
        if f == "dropna":
            if "subset" in kw:
                return [f"drop if missing({', '.join(s.names(kw['subset']))})"]
            return ["foreach v of varlist _all {", "    drop if missing(`v')", "}"]
        if f == "query" and a:
            return ["keep if " + s.condstr(a[0].value)]
        if f == "rename" and isinstance(kw.get("columns"), ast.Dict):
            d = kw["columns"]
            return [f"rename {s.col(k)} {s.col(x)}" for k, x in zip(d.keys, d.values)]
        if f == "sort_values":
            by = s.names(kw.get("by") or a[0])
            asc = kw.get("ascending")
            if isinstance(asc, ast.Constant) and asc.value is False:
                return ["gsort " + " ".join("-" + x for x in by)]
            return ["sort " + " ".join(by)]
        if f == "drop_duplicates":
            return ["duplicates drop " + (" ".join(s.names(kw["subset"])) if "subset" in kw else "") + ", force"]
        if f == "merge" and a:
            o = a[0]
            if not (isinstance(o, ast.Call) and getattr(o.func, "attr", "") in ("read_stata", "read_csv", "read_excel")):
                raise U("merge con un DataFrame ya cargado")
            fl = s.file(o)
            if not fl.endswith(".dta"):
                s.w(f"merge usa '{fl}': en Stata el archivo 'using' debe estar en formato .dta (import + save antes)")
                fl = re.sub(r"\.\w+$", "", fl) + ".dta"
            on = " ".join(s.names(kw["on"])) if "on" in kw else ""
            how = kw["how"].value if isinstance(kw.get("how"), ast.Constant) else "inner"
            keep = {"inner": " keep(match)", "left": " keep(master match)", "right": " keep(using match)"}.get(how, "")
            rel = {"one_to_one": "1:1", "many_to_one": "m:1", "one_to_many": "1:m"}.get(
                getattr(kw.get("validate"), "value", ""), getattr(kw.get("validate"), "value", "") or "1:1")
            if "validate" not in kw:
                s.w("merge: se asumió 1:1; ajustar a m:1 o 1:m según los datos")
            return [f'merge {rel} {on} using "{fl}",{keep} nogenerate']
        if f in AGG or f == "agg":
            return s.group(v)
        if f in ("to_csv", "to_stata", "to_excel"):
            fl = s.file(v)
            return {"to_csv": [f'export delimited "{fl}", replace'], "to_stata": [f'save "{fl}", replace'],
                    "to_excel": [f'export excel "{fl}", replace firstrow(variables)']}[f]
        if stmt:
            tgt, cols = (b.value if isinstance(b, ast.Subscript) else b), None
            if isinstance(b, ast.Subscript) and s.isframe(b.value):
                cols = s.names(b.slice)
            if s.isframe(tgt) or cols:
                cs = " ".join(cols or [])
                if f == "describe":
                    return [f"summarize {cs}".strip()]
                if f == "info":
                    return ["describe"]
                if f == "head":
                    return [f"list {cs} in 1/{a[0].value if a else 5}".replace("  ", " ")]
                if f == "value_counts":
                    return [f"tabulate {cs}, missing"]
                if f == "corr":
                    return [f"correlate {cs}".strip()]
        return s.plot(v)

    def subset(s, v):
        if not s.isframe(v.value):
            return None
        if isinstance(v.slice, ast.List):
            return ["keep " + " ".join(s.names(v.slice))]
        if isinstance(v.slice, ast.Constant):
            return None
        return ["keep if " + s.ex(v.slice)]

    def group(s, v):
        f, b = v.func.attr, v.func.value
        cols = None
        if isinstance(b, ast.Subscript):
            cols, b = s.names(b.slice), b.value
        if not (isinstance(b, ast.Call) and getattr(b.func, "attr", "") == "groupby"):
            return None
        by = " ".join(s.names(b.args[0]))
        if f != "agg":
            if cols is None:
                raise U("groupby sin columnas explícitas")
            return [f"collapse ({STAT.get(f, f)}) {' '.join(cols)}, by({by})"]
        parts = []
        for k in v.keywords:
            if not (isinstance(k.value, ast.Tuple) and len(k.value.elts) == 2):
                raise U("agg no soportado")
            old, st = k.value.elts
            parts.append(f"({STAT.get(st.value, st.value)}) {k.arg}={old.value}")
        return [f"collapse {' '.join(parts)}, by({by})"]

    def plot(s, v):
        name = getattr(v.func, "attr", "")
        base = v.func.value if isinstance(v.func, ast.Attribute) else None
        if isinstance(base, ast.Name) and base.id == "plt":
            if name in ("show", "figure", "title", "xlabel", "ylabel", "legend", "tight_layout"):
                return []
            if name == "savefig":
                return [f'graph export "{s.file(v)}", replace']
            if name == "hist" and v.args:
                return [f"histogram {s.ex(v.args[0])}"]
            if name == "scatter" and len(v.args) >= 2:
                return [f"scatter {s.ex(v.args[1])} {s.ex(v.args[0])}"]
        if name == "hist" and isinstance(base, ast.Subscript):
            return [f"histogram {s.col(base.slice)}"]
        if name == "scatter":
            kw = {k.arg: s.col(k.value) for k in v.keywords if k.arg in ("x", "y")}
            if len(kw) == 2:
                return [f"scatter {kw['y']} {kw['x']}"]
        if isinstance(base, ast.Attribute) and name == "seed" and base.attr == "random":
            return [f"set seed {v.args[0].value}"]
        if isinstance(base, ast.Name) and base.id == "os" and name == "chdir":
            return [f'cd "{s.file(v)}"']
        return None


def python_to_stata(src, lang="es"):
    global LANG
    LANG = lang
    try:
        ast.parse(src)
    except SyntaxError as e:
        return "", [tr(f"El código Python no es válido (línea {e.lineno}): {e.msg}")]
    s = P2S(src)
    s.body(ast.parse(src).body)
    s.flush(10 ** 9)
    head = [tr("* Traducido de Python a Stata (revisar antes de usar)")]
    return "\n".join(head + ["", *s.out]).rstrip() + "\n", s.warns
