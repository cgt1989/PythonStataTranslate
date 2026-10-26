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
    (" — motivo: ", " — reason: "),
    ("la sintaxis u opciones de", "the syntax or options of"),
    ("no se reconocieron", "were not recognized"),
    ("no tiene traducción automática; equivalente sugerido:", "has no automatic translation; suggested equivalent:"),
    ("el comando", "the command"),
    ("aún no está soportado (¿comando propio/.ado o abreviatura poco común?)",
     "is not supported yet (user-written/.ado command or uncommon abbreviation?)"),
    ("cc: se asume codificación 0/1 (1 = caso/expuesto); revisar si tus variables usan otros valores",
     "cc: assumes 0/1 coding (1 = case/exposed); check whether your variables use other values"),
    ("use: las etiquetas de valor de Stata se leen como códigos numéricos (convert_categoricals=False), "
     "así las condiciones como sexo==1 funcionan igual que en Stata",
     "use: Stata value labels are read as numeric codes (convert_categoricals=False), "
     "so conditions like sexo==1 work as in Stata"),
    ("margins: se calculan sin errores estándar (Stata usa el método delta); para efectos marginales con IC usa res.get_margeff()",
     "margins: computed without standard errors (Stata uses the delta method); for marginal effects with CIs use res.get_margeff()"),
    ("stset ... if: la condición no se aplica; filtra los datos antes con keep if",
     "stset ... if: the condition is not applied; filter the data first with keep if"),
    ("stcox: lifelines trata los empates con el método de Efron; Stata usa Breslow por defecto "
     "(la diferencia es pequeña salvo con muchos empates)",
     "stcox: lifelines handles ties with the Efron method; Stata uses Breslow by default "
     "(the difference is small unless there are many ties)"),
    ("teffects: el error estándar se calcula por bootstrap (Stata usa estimadores analíticos, p. ej. "
     "Abadie-Imbens en psmatch), por lo que difiere ligeramente",
     "teffects: the standard error is computed by bootstrap (Stata uses analytic estimators, e.g. "
     "Abadie-Imbens for psmatch), so it differs slightly"),
    ("psmatch2: se estima con teffects (ATT salvo que uses ate); no se crean _pscore, _weight ni _id, "
     "y el error estándar es por bootstrap",
     "psmatch2: estimated with teffects (ATT unless you use ate); _pscore, _weight and _id are not created, "
     "and the standard error is bootstrapped"),
    ("la función '", "the function '"),
    ("' no tiene equivalente automático en Stata", "' has no automatic equivalent in Stata"),
    ("el atributo '", "the attribute '"),
    ("' no se reconoce", "' is not recognized"),
    ("el elemento '", "the element '"),
    ("' no se soporta en expresiones", "' is not supported in expressions"),
    ("la sentencia '", "the statement '"),
    ("' no se soporta", "' is not supported"),
    ("llamada o expresión no reconocida", "unrecognized call or expression"),
    ("# TODO (sin traducir): ", "# TODO (not translated): "),
    ("TODO bloque sin traducir:", "TODO untranslated block:"),
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
    ("for con desempaquetado", "for with unpacking"),
    ("for no soportado", "unsupported for"),
    ("asignación compleja", "complex assignment"),
    ("merge con un DataFrame ya cargado", "merge with an already loaded DataFrame"),
    ("groupby sin columnas explícitas", "groupby without explicit columns"),
    ("agg no soportado", "unsupported agg"),
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
NOOP = {"set", "version", "compress", "format", "order", "log", "cls", "timer", "pause", "ssc", "help", "exit",
        "more", "discard", "macro", "window", "update", "adopath",
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
        "preserve": "df.copy()", "restore": "df.copy()", "levelsof": "df[col].unique()", "xi": "C(var) in the formula",
        "cs": "statsmodels Table2x2(...).riskratio", "tabodds": "statsmodels Table2x2 / StratifiedTable",
        "mhodds": "statsmodels StratifiedTable", "lroc": "sklearn.metrics.roc_curve / roc_auc_score",
        "roctab": "sklearn.metrics.roc_auc_score", "lincom": "res.t_test / res.wald_test",
        "swilk": "scipy.stats.shapiro", "sktest": "scipy.stats.normaltest", "ranksum": "scipy.stats.mannwhitneyu",
        "signrank": "scipy.stats.wilcoxon", "kwallis": "scipy.stats.kruskal", "oneway": "scipy.stats.f_oneway",
        "anova": "statsmodels.stats.anova.anova_lm", "prtest": "statsmodels.stats.proportion.proportions_ztest",
        "mlogit": "smf.mnlogit", "ologit": "statsmodels OrderedModel", "streg": "lifelines (exponential y gompertz no disponibles)",
        "stsplit": "lifelines.utils.to_episodic_format", "stjoin": "df.groupby(id).agg(...)",
        "stcrreg": "lifelines.AalenJohansenFitter (riesgos competitivos)", "stptime": "df['_t'].sum()",
        "stphplot": "cph.check_assumptions(...)", "stcoxkm": "lifelines.KaplanMeierFitter", "stmh": "statsmodels StratifiedTable",
        "nnmatch": "teffects(..., method='psmatch') o scipy.spatial.cKDTree", "pstest": "balance(df, treat, covs)",
        "ci": "df[col].mean() / scipy.stats.sem",
        "means": "df[col].mean()", "ttesti": "scipy.stats.ttest_ind_from_stats"}
IMP = {"pandas": "import pandas as pd", "numpy": "import numpy as np", "os": "import os",
       "smf": "import statsmodels.formula.api as smf", "scipy": "from scipy import stats",
       "plt": "import matplotlib.pyplot as plt", "fnmatch": "from fnmatch import fnmatch",
       "linearmodels": "from linearmodels import PanelOLS, RandomEffects, IV2SLS",
       "contingency": "from statsmodels.stats.contingency_tables import Table2x2, StratifiedTable",
       "sm": "import statsmodels.api as sm", "diag": "from statsmodels.stats.diagnostic import het_breuschpagan",
       "prop": "from statsmodels.stats.proportion import proportion_confint, proportions_ztest",
       "vif": "from statsmodels.stats.outliers_influence import variance_inflation_factor",
       "ordered": "from statsmodels.miscmodels.ordinal_model import OrderedModel",
       "patsy": "import patsy", "km": "from lifelines import KaplanMeierFitter", "cox": "from lifelines import CoxPHFitter",
       "aft": "from lifelines import WeibullAFTFitter, LogNormalAFTFitter, LogLogisticAFTFitter",
       "lls": "from lifelines.statistics import multivariate_logrank_test, proportional_hazard_test"}
MODELS = {"regress": "ols", "logit": "logit", "logistic": "logit", "probit": "probit", "poisson": "poisson",
          "mlogit": "mnlogit", "nbreg": "negativebinomial"}
EG = {"mean": "mean", "sum": "sum", "total": "sum", "max": "max", "min": "min", "sd": "std",
      "count": "count", "median": "median"}
CST = {"mean": "mean", "sum": "sum", "count": "count", "sd": "std", "median": "median", "p50": "median",
       "min": "min", "max": "max", "first": "first", "last": "last"}


def head(r):
    """'sub resto' o 'sub, opciones' -> (sub, resto): separa la primera palabra aunque vaya pegada a una coma."""
    m = re.match(r"(\w+)\s*(.*)$", r.strip(), re.S)
    return (m.group(1), m.group(2)) if m else ("", r.strip())


PREF = {"tabulate": 3, "summarize": 2, "regress": 3, "correlate": 3, "describe": 3, "collapse": 4, "histogram": 4,
        "logistic": 5, "display": 3, "rename": 3, "replace": 4, "export": 3, "import": 3, "append": 3, "merge": 3,
        "generate": 3, "scatter": 4, "capture": 3, "quietly": 3, "noisily": 3, "estimates": 3, "duplicates": 3,
        "codebook": 3, "tabstat": 4, "predict": 4, "twoway": 2, "kdensity": 4, "margins": 4, "recode": 3, "label": 3}

QS = re.compile(r'"([^"]*)"')
NUM = re.compile(r"-?\d+(\.\d+)?")


def opt(o, name):
    """Contenido de name(...) dentro de las opciones o (admite paréntesis anidados); None si no está."""
    m = re.search(r"(?<!\w)" + name + r"\(", o or "")
    if not m:
        return None
    d, i = 1, m.end()
    while i < len(o) and d:
        d += (o[i] == "(") - (o[i] == ")")
        i += 1
    return o[m.end():i - 1]


def groups(b):
    """'(a b) (c d) resto' -> (['a b', 'c d'], 'resto'): grupos entre paréntesis de primer nivel."""
    out, rest, d, cur = [], "", 0, ""
    for c in b:
        if c == "(":
            d += 1
            if d == 1:
                cur = ""
                continue
        elif c == ")":
            d -= 1
            if d == 0:
                out.append(cur)
                continue
        if d:
            cur += c
        else:
            rest += c
    return out, rest


def gparse(o):
    """Opciones de gráfico de Stata -> dict (title, xtitle, ytitle, yline, xline, legend)."""
    g = {}
    for k in ("title", "xtitle", "ytitle"):
        v = opt(o, k)
        if v is not None:
            g[k] = (QS.findall(v) or [v.strip()])[0]
    for k in ("yline", "xline"):
        v = opt(o, k)
        if v:
            g[k] = [float(x) if "." in x else int(x) for x in v.split(",")[0].split() if NUM.fullmatch(x)]
    lo = opt(opt(o, "legend") or "", "order")
    if lo:
        g["legend"] = QS.findall(lo)
    return g


def _extreme(a, op):
    r = a[0]
    for x in a[1:]:
        r = f"({r}).where(({r}) {op} ({x}), ({x}))"
    return r


# funciones de Stata que df.eval no tiene: nombre -> (lista de argumentos -> expresión equivalente)
REWRITES = {
    # floor(x/u + .5)*u: Stata round(x, u); evita (expr).round(), que pandas 2.x no admite dentro de eval
    "round": lambda a: f"floor(({a[0]}) / ({a[1]}) + 0.5) * ({a[1]})" if len(a) > 1 else f"floor(({a[0]}) + 0.5)",
    "strlen": lambda a: f"({a[0]}).str.len()", "upper": lambda a: f"({a[0]}).str.upper()",
    "lower": lambda a: f"({a[0]}).str.lower()", "trim": lambda a: f"({a[0]}).str.strip()",
    "substr": lambda a: f"({a[0]}).str[({a[1]}) - 1:({a[1]}) - 1 + ({a[2]})]",
    "mod": lambda a: f"(({a[0]}) % ({a[1]}))",
    "max": lambda a: _extreme(a, ">="), "min": lambda a: _extreme(a, "<="),
}


def rewrite_fn(e, name, f):
    """Reemplaza name(a, b, ...) por f([a, b, ...]), separando argumentos de primer nivel."""
    while True:
        m = re.search(r"(?<![.\w])" + name + r"\(", e)
        if not m:
            return e
        i, d, args, cur = m.end(), 1, [], ""
        while i < len(e) and d:
            c = e[i]
            d += (c == "(") - (c == ")")
            if c == "," and d == 1:
                args.append(cur.strip())
                cur = ""
            elif d:
                cur += c
            i += 1
        args.append(cur.strip())
        e = e[:m.start()] + f(args) + e[i:]


def rewrite_round(e):
    for name, f in REWRITES.items():
        e = rewrite_fn(e, name, f)
    return e


# funciones auxiliares que se copian al script generado cuando se usan: (imports que necesitan, código)
HELPERS = {
    "tab": (("pandas",), '''def tab(x, missing=False):
    """Frecuencias, porcentaje y acumulado / frequencies, percent, cumulative (tabulate)."""
    t = x.value_counts(dropna=not missing).sort_index()
    p = t / t.sum() * 100
    return pd.DataFrame({"Freq.": t, "Percent": p, "Cum.": p.cumsum()})'''),
    "tabstat": (("pandas",), '''def tabstat(df, cols, stats=("mean",), by=None):
    """Estadísticos por variable / statistics per variable (tabstat)."""
    m2 = lambda x: ((x - x.mean()) ** 2).mean()
    def f(s):
        if s[0] == "p" and s[1:].isdigit():
            return lambda x: x.quantile(int(s[1:]) / 100)
        return {"n": "count", "mean": "mean", "sd": "std", "variance": "var", "var": "var", "min": "min",
                "max": "max", "sum": "sum", "median": "median", "semean": "sem",
                "skewness": lambda x: ((x - x.mean()) ** 3).mean() / m2(x) ** 1.5,
                "kurtosis": lambda x: ((x - x.mean()) ** 4).mean() / m2(x) ** 2,
                "iqr": lambda x: x.quantile(.75) - x.quantile(.25), "range": lambda x: x.max() - x.min(),
                "cv": lambda x: x.std() / x.mean()}[s]
    stats = [t for s in stats for t in (["p25", "p50", "p75"] if s == "q" else [s])]
    if by:
        return pd.concat({k: tabstat(g, cols, stats) for k, g in df.groupby(by)})
    return pd.DataFrame({c: {s: df[c].agg(f(s)) for s in stats} for c in cols}).loc[stats]'''),
    "testparm": (("numpy",), '''def testparm(res, *terms):
    """Prueba conjunta: los términos valen 0 / joint test that the terms are 0 (testparm)."""
    def match(name, term):
        a, b = name.split(":"), term.split(":")
        return len(a) == len(b) and all(any(p == c or p.startswith(c + "[") for p in a) for c in b)
    names = list(res.params.index)
    pick = [i for i, n in enumerate(names) if any(match(n, t) for t in terms)]
    if not pick:
        raise ValueError(f"testparm: ningún coeficiente del último modelo coincide con {terms} / no matching coefficient")
    R = np.zeros((len(pick), len(names)))
    for row, i in enumerate(pick):
        R[row, i] = 1
    return res.wald_test(R, scalar=True)'''),
    "lrtest": (("scipy",), '''def lrtest(a, b):
    """Razón de verosimilitud entre modelos anidados / likelihood-ratio test (lrtest)."""
    full, rest = (a, b) if a.df_model >= b.df_model else (b, a)
    lr, df = 2 * (full.llf - rest.llf), full.df_model - rest.df_model
    return {"chi2": lr, "df": df, "p": stats.chi2.sf(lr, df)}'''),
    "lroc": (("numpy", "plt"), '''def lroc(res):
    """Curva ROC y área bajo la curva tras logit / ROC curve and AUC after logit (lroc)."""
    y, p = np.asarray(res.model.endog), np.asarray(res.predict())
    o = np.argsort(-p)
    tpr = np.r_[0, np.cumsum(y[o]) / y.sum()]
    fpr = np.r_[0, np.cumsum(1 - y[o]) / (1 - y).sum()]
    auc = ((fpr[1:] - fpr[:-1]) * (tpr[1:] + tpr[:-1]) / 2).sum()
    plt.figure()
    plt.plot(fpr, tpr)
    plt.plot([0, 1], [0, 1], "--", color="gray")
    plt.xlabel("1 - Specificity")
    plt.ylabel("Sensitivity")
    plt.title(f"Area under ROC curve = {auc:.4f}")
    return auc'''),
    "gof": (("pandas", "scipy"), '''def gof(res, groups=None):
    """Bondad de ajuste tras logit / goodness of fit after logit (estat gof)."""
    d = pd.DataFrame(res.model.exog, columns=res.model.exog_names)
    d["y"], d["p"] = res.model.endog, res.predict()
    if groups:  # Hosmer-Lemeshow
        d["g"] = pd.qcut(d["p"], groups, duplicates="drop", labels=False)
        t = d.groupby("g").agg(n=("y", "size"), obs=("y", "sum"), p=("p", "sum"))
        chi2, df_ = (((t.obs - t.p) ** 2) / (t.p * (1 - t.p / t.n))).sum(), len(t) - 2
    else:  # chi2 de Pearson por patrones de covariables
        t = d.groupby(res.model.exog_names).agg(n=("y", "size"), obs=("y", "sum"), p=("p", "first"))
        chi2, df_ = (((t.obs - t.n * t.p) ** 2) / (t.n * t.p * (1 - t.p))).sum(), len(t) - len(res.params)
    return {"chi2": chi2, "df": df_, "p": stats.chi2.sf(chi2, df_)}'''),
    "margins": (("pandas",), '''def margins(res, df, factors=(), dydx=(), at=None):
    """Márgenes predictivos promedio / average predictive margins (margins; sin errores estándar)."""
    import itertools
    at = at or {}
    rows = []
    for g in [dict(zip(at, v)) for v in itertools.product(*at.values())] or [{}]:
        for combo in itertools.product(*[sorted(df[f].dropna().unique()) for f in factors]):
            fixed = {**g, **dict(zip(factors, combo))}
            d, row = df.assign(**fixed), dict(fixed)
            if dydx:
                for v in dydx:
                    h = 1e-4 * max(1.0, abs(d[v]).mean())
                    up, lo = d.assign(**{v: d[v] + h}), d.assign(**{v: d[v] - h})
                    row["dy/dx " + v] = ((res.predict(up) - res.predict(lo)) / (2 * h)).mean()
            else:
                row["margin"] = res.predict(d).mean()
            rows.append(row)
    return pd.DataFrame(rows)'''),
    "twoway": (("numpy", "plt"), '''def twoway(df, plots, title=None, xtitle=None, ytitle=None, legend=None, yline=(), xline=(), by=None):
    """Gráfico tipo twoway / twoway-style plot: plots = [(scatter|lfit|line, y, x, condición)]."""
    groups = list(df.groupby(by)) if by else [(None, df)]
    fig, axes = plt.subplots(1, len(groups), squeeze=False, sharey=True)
    for ax, (k, d) in zip(axes[0], groups):
        for kind, y, x, cond in plots:
            e = (d[d.eval(cond, engine="python")] if cond else d)[[x, y]].dropna()
            if kind == "scatter":
                ax.scatter(e[x], e[y])
            elif kind == "lfit":
                xs = np.sort(e[x].unique())
                ax.plot(xs, np.polyval(np.polyfit(e[x], e[y], 1), xs))
            else:
                e = e.sort_values(x)
                ax.plot(e[x], e[y])
        for v in yline:
            ax.axhline(v, linestyle="--", color="gray", linewidth=1)
        for v in xline:
            ax.axvline(v, linestyle="--", color="gray", linewidth=1)
        ax.set_xlabel(xtitle or plots[0][2])
        ax.set_ylabel(ytitle or plots[0][1])
        if legend:
            ax.legend(legend)
        if by:
            ax.set_title(f"{by} = {k}")
    if title:
        fig.suptitle(title)
    return fig'''),
}
HELPERS.update({
    "km_fit": (("pandas", "km"), '''def km_fit(df, by=None):
    """Kaplan-Meier por grupo / by group: {grupo: KaplanMeierFitter}."""
    out = {}
    for k, d in (df.groupby(by) if by else [("all", df)]):
        out[k] = KaplanMeierFitter(label=str(k)).fit(d["_t"], d["_d"], entry=d["_t0"])
    return out'''),
    "sts_graph": (("km_fit", "plt"), '''def sts_graph(df, by=None, failure=False, ci=False, risktable=False):
    """Curvas de Kaplan-Meier / Kaplan-Meier curves (sts graph)."""
    fits = km_fit(df, by)
    ax = None
    for f in fits.values():
        ax = f.plot_cumulative_density(ci_show=ci, ax=ax) if failure else f.plot_survival_function(ci_show=ci, ax=ax)
    if risktable:
        from lifelines.plotting import add_at_risk_counts
        add_at_risk_counts(*fits.values(), ax=ax)
    ax.set_xlabel("analysis time")
    ax.set_ylabel("Failure probability" if failure else "Survival probability")
    return ax'''),
    "sts_list": (("km_fit",), '''def sts_list(df, by=None):
    """Tabla de supervivencia en cada tiempo de falla / survival table at failure times (sts list)."""
    rows = []
    for k, f in km_fit(df, by).items():
        t = f.event_table[["at_risk", "observed"]].rename(columns={"at_risk": "N at risk", "observed": "Fail"})
        t["Survivor"] = f.survival_function_.iloc[:, 0].reindex(t.index)
        ci = f.confidence_interval_.reindex(t.index)
        t["Lower"], t["Upper"] = ci.iloc[:, 0], ci.iloc[:, 1]
        rows.append(t[t["Fail"] > 0].assign(group=k))
    return pd.concat(rows)'''),
    "km_at": (("numpy", "pandas", "km"), '''def km_at(df, by=None):
    """Supervivencia de Kaplan-Meier en el tiempo de cada observación (sts generate)."""
    s = pd.Series(np.nan, index=df.index)
    for k, d in (df.groupby(by) if by else [("all", df)]):
        f = KaplanMeierFitter().fit(d["_t"], d["_d"], entry=d["_t0"])
        s[d.index] = f.survival_function_at_times(d["_t"]).values
    return s'''),
    "strate": (("pandas", "scipy", "km"), '''def strate(df, by=None, median=False):
    """Tasas de incidencia con IC exacto / incidence rates with exact CI (strate, stsum)."""
    rows = {}
    for k, d in (df.groupby(by) if by else [("all", df)]):
        D, Y = d["_d"].sum(), (d["_t"] - d["_t0"]).sum()
        r = {"subjects": len(d), "failures": D, "time at risk": Y, "rate": D / Y,
             "lower": stats.chi2.ppf(.025, 2 * D) / (2 * Y) if D else 0.0,
             "upper": stats.chi2.ppf(.975, 2 * D + 2) / (2 * Y)}
        if median:
            f = KaplanMeierFitter().fit(d["_t"], d["_d"], entry=d["_t0"])
            r.update({"p25": f.percentile(.75), "p50": f.percentile(.5), "p75": f.percentile(.25)})
        rows[k] = r
    return pd.DataFrame(rows).T'''),
    "cox_fit": (("pandas", "patsy", "cox"), '''def cox_fit(df, covs, strata=None, weights=None, cluster=None, entry=False, robust=False):
    """Regresión de Cox / Cox regression (stcox) con lifelines; los datos usados quedan en cph.data_."""
    X = patsy.dmatrix(covs, df, return_type="dataframe").drop(columns="Intercept", errors="ignore")
    extra = ["_t", "_d"] + (["_t0"] if entry else []) + list(strata or []) + [c for c in (weights, cluster) if c]
    d = X.join(df[list(dict.fromkeys(extra))]).dropna()
    cph = CoxPHFitter()
    cph.fit(d, "_t", "_d", strata=strata, weights_col=weights, cluster_col=cluster,
            entry_col="_t0" if entry else None, robust=robust or bool(weights) or bool(cluster))
    cph.data_ = d
    return cph'''),
    "aft_fit": (("pandas", "patsy", "aft"), '''def aft_fit(model, df, covs):
    """Modelo paramétrico de supervivencia / parametric survival model (streg) con lifelines."""
    X = patsy.dmatrix(covs, df, return_type="dataframe").drop(columns="Intercept", errors="ignore")
    return model().fit(X.join(df[["_t", "_d"]]).dropna(), "_t", "_d")'''),
    "balance": (("numpy", "pandas", "patsy"), '''def balance(df, treat, covs, weights=None):
    """Balance de covariables / covariate balance (tebalance summarize, pbalchk): diferencia estandarizada."""
    X = patsy.dmatrix(covs, df, return_type="dataframe").drop(columns="Intercept", errors="ignore")
    d = X.join(df[[treat] + ([weights] if weights else [])]).dropna()
    w = d[weights] if weights else pd.Series(1.0, index=d.index)
    rows = {}
    for c in X.columns:
        m, v = {}, {}
        for g in (0, 1):
            s = d[d[treat] == g]
            m[g] = np.average(s[c], weights=w[s.index])
            v[g] = np.average((s[c] - m[g]) ** 2, weights=w[s.index])
        rows[c] = {"mean_control": m[0], "mean_treated": m[1],
                   "std_diff": (m[1] - m[0]) / np.sqrt((v[0] + v[1]) / 2), "var_ratio": v[1] / v[0] if v[0] else np.nan}
    return pd.DataFrame(rows).T'''),
    "teffects": (("numpy", "pandas", "smf", "scipy"), '''te_last = {}


def teffects(df, y, t, covs, method="psmatch", att=False, neighbors=1, caliper=None, ocovs=None, link="logit",
             reps=200, seed=0):
    """Efectos de tratamiento / treatment effects (teffects psmatch | ipw | ra | aipw).
    ATE por defecto, ATT con att=True. Error estándar por bootstrap (Stata usa fórmulas analíticas)."""
    from scipy.spatial import cKDTree

    def one(d):
        d = d.dropna(subset=[y, t])
        if method != "ra":
            ps = getattr(smf, link)(f"{t} ~ {covs}", d).fit(disp=0).predict(d)
            d, ps = d[ps.notna()], ps[ps.notna()].clip(1e-6, 1 - 1e-6).to_numpy()
        else:
            ps = np.full(len(d), .5)
        T, Y, w = d[t].to_numpy(float), d[y].to_numpy(float), np.ones(len(d))
        if method == "ipw":
            w = T + (1 - T) * ps / (1 - ps) if att else T / ps + (1 - T) / (1 - ps)
            est = (w * T * Y).sum() / (w * T).sum() - (w * (1 - T) * Y).sum() / (w * (1 - T)).sum()
        elif method in ("ra", "aipw"):
            mu0, mu1 = [smf.ols(f"{y} ~ {ocovs or covs}", d[d[t] == v]).fit().predict(d).to_numpy() for v in (0, 1)]
            if method == "ra":
                est = (mu1 - mu0)[T == 1].mean() if att else (mu1 - mu0).mean()
            elif att:
                est = ((T * (Y - mu0)).sum() - ((1 - T) * ps / (1 - ps) * (Y - mu0)).sum()) / T.sum()
            else:
                est = (mu1 - mu0 + T * (Y - mu1) / ps - (1 - T) * (Y - mu0) / (1 - ps)).mean()
        else:  # psmatch: vecino(s) más cercano(s) en el propensity score, con reemplazo
            i1, i0 = np.where(T == 1)[0], np.where(T == 0)[0]
            k, acc = max(1, min(neighbors, len(i0), len(i1))), np.zeros(len(d))

            def impute(src, pool):
                dist, nn = cKDTree(ps[pool][:, None]).query(ps[src][:, None], k=k)
                dist, nn = dist.reshape(len(src), -1), nn.reshape(len(src), -1)
                ok = dist <= caliper if caliper else np.ones(dist.shape, bool)
                cnt = ok.sum(1)
                rows, cols = np.nonzero(ok)
                np.add.at(acc, pool[nn[rows, cols]], 1 / cnt[rows])
                return np.where(cnt > 0, (Y[pool][nn] * ok).sum(1) / np.maximum(cnt, 1), np.nan)

            diffs = [Y[i1] - impute(i1, i0)] + ([] if att else [impute(i0, i1) - Y[i0]])
            est = np.nanmean(np.concatenate(diffs))
            w = (T if att else 1) + acc  # peso de emparejamiento de cada observación
        return est, w, ps, d

    def boot(i):
        try:
            return one(df.sample(len(df), replace=True, random_state=i))[0]
        except Exception:
            return np.nan

    est, w, ps, d = one(df)
    se = np.nanstd([boot(i) for i in range(reps)], ddof=1)
    te_last.update(data=d.assign(_w=w, _ps=ps), treat=t, covs=covs, y=y)
    return pd.Series({"estimate": est, "boot_se": se, "z": est / se, "p": 2 * stats.norm.sf(abs(est / se)),
                      "ci_low": est - 1.96 * se, "ci_high": est + 1.96 * se})'''),
})
BASIC = "['n', 'mean', 'sd', 'min', 'max']"
DETAIL = ("['n', 'mean', 'sd', 'variance', 'skewness', 'kurtosis', 'min', 'p1', 'p5', 'p10', 'p25', 'p50', 'p75', "
          "'p90', 'p95', 'p99', 'max']")


def canon(w):
    """Abreviatura de Stata -> nombre completo (tabu -> tabulate)."""
    w = AB.get(w, w)
    for full, n in PREF.items():
        if len(w) >= n and full.startswith(w):
            return full
    return w


def prep(src):
    # /* ... */ -> lineas "//"; /// une la linea con la siguiente
    src = re.sub(r"/\*(.*?)\*/", lambda m: "\n".join("// " + l for l in m.group(1).splitlines()) + "\n", src, flags=re.S)
    src = re.sub(r"[ \t]*///[^\n]*\n", " ", src)
    return src.splitlines()


class S2P:
    def __init__(s):
        s.imp, s.warns, s.out, s.stack, s.ind, s.panel = {"pandas": 1}, [], [], [], 0, False
        s.helpers, s.init, s.plots, s.labels, s.margins, s.kind, s.rows = {}, [], False, False, None, None, None
        s.st_enter, s.wglm = False, False

    def w(s, m):
        m = tr(m)
        if m not in s.warns:
            s.warns.append(m)

    def need(s, name):
        """Incluye una función auxiliar en el script generado, con sus dependencias e imports."""
        for k in HELPERS[name][0]:
            if k in HELPERS:
                s.need(k)
            else:
                s.imp[k] = 1
        s.helpers[name] = 1

    @staticmethod
    def by1(v):
        return repr(v[0]) if len(v) == 1 else repr(v)

    def use_labels(s):
        if not s.labels:
            s.labels = True
            s.init.append("var_labels, label_sets, value_labels = {}, {}, {}")

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
        txt, f = s.rhs(xs)
        return ("f" if f else "") + repr(f"{y} ~ {txt}{extra}")

    def rhs_lit(s, xs):
        """Lado derecho de una fórmula (a + C(b)) como literal Python."""
        txt, f = s.rhs(xs)
        return ("f" if f else "") + repr(txt)

    def rhs(s, xs):
        parts, f = [], False
        for t in xs:
            m = MAC.fullmatch(t)
            if m:
                parts.append("{" + _name(m) + ".replace(' ', ' + ')}")
                f = True
                continue
            t = re.sub(r"\bb\((\d+)\)\.(\w+)", r"ib\1.\2", t)  # b(5).x -> ib5.x
            t = re.sub(r"\bib(\d+)\.(\w+)", r"C(\2, Treatment(reference=\1))", t)
            t = re.sub(r"\bi\.(\w+)", r"C(\1)", t)
            t = re.sub(r"\bc\.", "", t).replace("##", "*").replace("#", ":")
            parts.append(t)
        return (" + ".join(parts) if parts else "1"), f

    def pyx(s, x):
        """Expresion escalar Stata -> Python (condiciones, locals, display)."""
        x = bare(x.strip())
        x = re.sub(r"\br\((\w+)\)", r"r['\1']", x)
        x = re.sub(r"\b_(b|se)\[([^\]]+)\]",
                   lambda m: f"res.{'params' if m.group(1) == 'b' else 'bse'}[{s.coef(m.group(2))!r}]", x)
        if re.search(r"\be\(", x):
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

    @staticmethod
    def coef(n):
        """Nombre de coeficiente de Stata (c.a#c.b, 1.sexo, _cons) -> nombre en statsmodels."""
        out = []
        for p in n.split("#"):
            m = re.fullmatch(r"(\d+)b?\.(\w+)", p)
            out.append(f"C({m.group(2)})[T.{m.group(1)}]" if m else "Intercept" if p == "_cons" else re.sub(r"^c\.", "", p))
        return ":".join(out)

    @staticmethod
    def term(t):
        """Término de Stata (i.a#c.b) -> término de fórmula (C(a):b)."""
        t = re.sub(r"\bib?(\d+)\.(\w+)", r"C(\2, Treatment(reference=\1))", t)
        return re.sub(r"\bc\.", "", re.sub(r"\bi\.(\w+)", r"C(\1)", t)).replace("##", ":").replace("#", ":")

    def E(s, e):
        return f'df.eval({q(s.ev(e))}, engine="python")'

    def ev(s, e):
        """Expresión de Stata -> texto para df.eval."""
        if ">" in e:
            s.w(f"Missing: en Stata '.' es mayor que cualquier número (x > 5 es verdadero si x es missing); "
                f"en pandas NaN > 5 es False. Revisar: {e}")
        e = rewrite_round(e)
        e = re.sub(r"(\w+)\s*<\s*\.(?![\w.])", r"\1.notna()", e)
        e = re.sub(r"(\w+)\s*>=\s*\.(?![\w.])", r"\1.isna()", e)
        e = re.sub(r"(\w+)\s*==\s*\.(?![\w.])", r"\1.isna()", e)
        e = re.sub(r"(\w+)\s*!=\s*\.(?![\w.])", r"\1.notna()", e)
        e = re.sub(r"\bmissing\((\w+)\)", r"\1.isna()", e)
        e = re.sub(r"\binlist\((\w+),([^)]*)\)", r"\1.isin([\2])", e)
        e = re.sub(r"\binrange\((\w+),([^,]*),([^)]*)\)", r"\1.between(\2,\3)", e)
        e = re.sub(r"\bln\(", "log(", e).replace("~=", "!=")
        return re.sub(r"!(?!=)", "~", e).replace("^", "**")

    def D(s, cond):
        return f"df[{s.E(cond)}]" if cond else "df"

    def unknown(s, st, syntax=True):
        """syntax=True: el comando existe pero su sintaxis/opciones no se reconocieron."""
        c = canon(re.match(r"\w*", st).group())
        h = HINT.get(c)
        if h:
            why = f"'{c}' no tiene traducción automática; equivalente sugerido: {h}"
        elif syntax:
            why = f"la sintaxis u opciones de '{c}' no se reconocieron"
        else:
            why = f"el comando '{c}' aún no está soportado (¿comando propio/.ado o abreviatura poco común?)"
        s.w(f"No traducido: «{st[:70]}» — motivo: {why}")
        return [tr("# TODO (sin traducir): ") + st]

    # ---- una linea de comando -> lista de lineas Python
    def cmd(s, st, by=None):
        m = re.match(r"(bysort|bys|by)\s+([^:(]+?)\s*(?:\(([^)]*)\))?\s*:\s*(.*)$", st)
        if m:
            by = m.group(2).split()
            pre = [f"df = df.sort_values({s.pl(by + (m.group(3) or '').split())})"] if m.group(1) != "by" else []
            return pre + s.cmd(m.group(4), by)
        c, rest = head(st)
        c = canon(c)
        if c in ("quietly", "noisily"):
            return s.cmd(rest.lstrip(": "), by)
        if c == "capture":
            inner = s.cmd(rest.lstrip(": "), by)
            if all(l.lstrip().startswith("#") for l in inner):  # try: con solo comentarios no es Python valido
                return inner
            return ["try:"] + ["    " + l for l in inner] + ["except Exception:", "    pass"]
        if c in NOOP:
            if c == "set" and rest.startswith("seed"):
                s.imp["numpy"] = 1
                return [f"np.random.seed({rest.split()[1]})"]
            return ["# " + st]
        h = getattr(s, "c_" + c, None)
        return h(rest, by) if h else s.unknown(st, syntax=False)

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
        s.w("use: las etiquetas de valor de Stata se leen como códigos numéricos (convert_categoricals=False), "
            "así las condiciones como sexo==1 funcionan igual que en Stata")
        if " using " in b:
            v, b = b.split(" using ", 1)
            return [f"df = pd.read_stata({s.fn(b)}, columns={s.pl(v.split())}, convert_categoricals=False)"]
        return [f"df = pd.read_stata({s.fn(b)}, convert_categoricals=False)"]

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
        lab = ""
        if s.labels:  # conserva las etiquetas definidas con label variable/define/values
            lab = (", variable_labels={k: v[:80] for k, v in var_labels.items() if k in df}, "
                   "value_labels={k: v for k, v in value_labels.items() if k in df}")
        return [f"df.to_stata({s.fn(split_opts(r)[0])}, write_index=False{lab})"]

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
        elif re.fullmatch(r"runiform\(\)", x.strip()):
            s.imp["numpy"] = 1
            rhs = "np.random.uniform(size=len(df))"
        elif re.fullmatch(r"rnormal\(\s*([^,]*),\s*([^)]*)\)", x.strip()):
            s.imp["numpy"] = 1
            mu, sd = re.fullmatch(r"rnormal\(\s*([^,]*),\s*([^)]*)\)", x.strip()).groups()
            rhs = f"np.random.normal({mu}, {sd}, len(df))"
        elif x.strip() in ("rnormal()",):
            s.imp["numpy"] = 1
            rhs = "np.random.normal(size=len(df))"
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
        cols = a.split()
        if f == "group":
            return [f"df[{q(v)}] = df.groupby({s.pl(cols)}).ngroup() + 1"]
        if f == "tag":
            return [f"df[{q(v)}] = (~df.duplicated({s.pl(cols)})).astype(int)"]
        if f in ("rowmax", "rowmin", "rowsd", "rownonmiss"):
            return [f"df[{q(v)}] = df[{s.pl(cols)}].{ {'rowmax': 'max', 'rowmin': 'min', 'rowsd': 'std', 'rownonmiss': 'count'}[f] }(axis=1)"]
        if f in ("rank", "iqr", "pctile"):
            qn = int(opt(o, "p") or 50) / 100
            fn = {"rank": None, "iqr": "lambda x: x.quantile(.75) - x.quantile(.25)", "pctile": f"lambda x: x.quantile({qn})"}[f]
            if f == "rank":
                return [f"df[{q(v)}] = " + (f"df.groupby({s.pl(gb)})[{q(a)}].rank()" if gb else f"df[{q(a)}].rank()")]
            return [f"df[{q(v)}] = " + (f"df.groupby({s.pl(gb)})[{q(a)}].transform({fn})" if gb
                                        else f"(lambda x: {fn[10:]})(df[{q(a)}])")]
        if f not in EG:
            return s.unknown("egen " + r)
        if gb:
            return [f'df[{q(v)}] = df.groupby({s.pl(gb)})[{q(a)}].transform("{EG[f]}")']
        return [f"df[{q(v)}] = df[{q(a)}].{EG[f]}()"]

    def c_drop(s, r, by):
        b, cond = split_if(split_opts(r)[0])
        if cond:
            return [f"df = df[~{s.E(cond)}]"]
        m = re.match(r"in\s+(\d+)/(\d+)$", b)
        if m:
            return [f"df = df.drop(df.index[{int(m.group(1)) - 1}:{m.group(2)}])"]
        if re.match(r"in\b", b):
            return s.unknown("drop " + r)
        return [f"df = df.drop(columns={s.pl(b.split())})"]

    def c_keep(s, r, by):
        b, cond = split_if(split_opts(r)[0])
        if cond:
            return [f"df = df[{s.E(cond)}]"]
        m = re.match(r"in\s+(\d+)/(\d+)$", b)
        if m:
            return [f"df = df.iloc[{int(m.group(1)) - 1}:{m.group(2)}]"]
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
        b, o = split_opts(r)
        v, cond = split_if(b)
        s.need("tabstat")
        cols = s.pl(v.split()) if v else "list(df.select_dtypes('number').columns)"
        st = DETAIL if re.search(r"\bd(etail)?\b", o) else BASIC
        d = s.D(cond)
        if by:
            return [f"for k, g in {d}.groupby({s.pl(by)}):", "    print(k)", f"    print(tabstat(g, {cols}, {st}))"]
        out = [f"print(tabstat({d}, {cols}, {st}))"]
        last = v.split()[-1] if v.split() else ""
        if last and re.fullmatch(r"\w+", last):  # r(mean), r(sd)... de la ultima variable, como en Stata
            out.append(f"r = {d}[{q(last)}].agg(['mean', 'std', 'count', 'min', 'max', 'sum', 'var', 'median'])"
                       ".rename({'std': 'sd', 'count': 'N', 'var': 'Var', 'median': 'p50'})")
        return out

    def c_tabstat(s, r, by):
        b, o = split_opts(r)
        v, cond = split_if(b)
        s.need("tabstat")
        st = (opt(o, "stat") or opt(o, "statistics") or "mean").replace(",", " ").split()
        g = opt(o, "by")
        by_ = f", by={g.split()[0]!r}" if g else ""
        t = ".T" if (opt(o, "col") or opt(o, "columns") or "").startswith("stat") else ""
        return [f"print(tabstat({s.D(cond)}, {s.pl(v.split())}, {st!r}{by_}){t})"]

    def c_describe(s, r, by):
        v = split_opts(r)[0].split()
        return [f"df[{s.pl(v)}].info()" if v else "df.info()"]

    def c_codebook(s, r, by):
        v = split_opts(r)[0].split()
        d = f"df[{s.pl(v)}]" if v else "df"
        return [f"print(pd.DataFrame({{'n': {d}.count(), 'missing': {d}.isna().sum(), 'unique': {d}.nunique(), "
                f"'min': {d}.min(), 'max': {d}.max()}}))"]

    def c_duplicates(s, r, by):
        sub, rest = head(r)
        b, o = split_opts(rest)
        cols = s.pl(b.split()) if b.split() else "list(df.columns)"
        if sub == "report":
            return [f"dup = df.groupby({cols}).size().value_counts().sort_index()",
                    "print(pd.DataFrame({'copies': dup.index, 'observations': dup.index * dup.values, "
                    "'surplus': (dup.index - 1) * dup.values}))"]
        if sub == "list":
            return [f"print(df[df.duplicated({cols}, keep=False)])"]
        if sub == "drop":
            return [f"df = df.drop_duplicates({cols})"]
        g = opt(o, "gen") or opt(o, "generate")
        if sub == "tag" and g:
            return [f"df[{q(g)}] = df.groupby({cols})[{cols}[0]].transform('size') - 1"]
        return s.unknown("duplicates " + r)

    def c_label(s, r, by):
        sub, rest = head(r)
        if sub in ("variable", "var"):
            m = re.match(r'(\w+)\s+"(.*)"\s*$', rest.strip())
            if m:
                s.use_labels()
                return [f"var_labels[{q(m.group(1))}] = {q(m.group(2))}"]
        elif sub == "define":
            name, _, items = rest.strip().partition(" ")
            b, o = split_opts(items)
            pairs = re.findall(r'(-?\d+)\s+"([^"]*)"', b)
            if name and pairs:
                s.use_labels()
                d = "{" + ", ".join(f"{k}: {q(t)}" for k, t in pairs) + "}"
                if re.search(r"\b(modify|add)\b", o):
                    return [f"label_sets.setdefault({name!r}, {{}}).update({d})"]
                return [f"label_sets[{name!r}] = {d}"]
        elif sub == "values":
            t = rest.split()
            if len(t) >= 2:
                s.use_labels()
                return [f"value_labels[{q(v)}] = label_sets[{t[-1]!r}]" for v in t[:-1]]
        return ["# label " + r]

    def c_recode(s, r, by):
        b, o = split_opts(r)
        m = re.match(r"(\w+)\s+(.*)$", b.strip())
        if not m:
            return s.unknown("recode " + r)
        v, rules = m.groups()
        new = opt(o, "gen") or opt(o, "generate") or v
        x, conds, vals, labs, default = f"df[{q(v)}]", [], [], {}, f"df[{q(v)}]" if new == v else "np.nan"
        for rule in groups(rules)[0]:
            mm = re.match(r'(.*?)=\s*(\S+)\s*(?:"([^"]*)")?\s*$', rule.strip())
            if not mm:
                return s.unknown("recode " + r)
            lhs, val, lab = mm.groups()
            val = "np.nan" if val == "." else val
            parts = []
            for t in lhs.split():
                if t in ("else", "*"):
                    default = val
                    continue
                if "/" in t:
                    a, z = t.split("/")
                    c = ([f"({x} >= {a})"] if a != "min" else []) + ([f"({x} <= {z})"] if z != "max" else [])
                    parts.append(" & ".join(c) or f"{x}.notna()")
                else:
                    parts.append(f"({x} == {t})")
            if parts:
                conds.append(" | ".join(parts))
                vals.append(val)
            if lab is not None:
                labs[val] = lab
        s.imp["numpy"] = 1
        out = [f"df[{q(new)}] = np.select([{', '.join(conds)}], [{', '.join(vals)}], default={default})"]
        if labs:
            s.use_labels()
            out += [f"label_sets[{new!r}] = {{{', '.join(f'{k}: {t!r}' for k, t in labs.items())}}}",
                    f"value_labels[{new!r}] = label_sets[{new!r}]"]
        return out

    def c_xtile(s, r, by):
        b, o = split_opts(r)
        m = re.match(r"(\w+)\s*=\s*(\w+)", b.strip())
        if not m:
            return s.unknown("xtile " + r)
        return [f"df[{q(m.group(1))}] = pd.qcut(df[{q(m.group(2))}], {opt(o, 'nq') or 2}, labels=False, "
                "duplicates='drop') + 1"]

    def c_input(s, r, by):
        s.rows = (r.split(), [])  # las filas se leen en run() hasta 'end'
        return []

    def c_ci(s, r, by):
        b, o = split_opts(r)
        t = b.split()
        kind = "means"
        if t and t[0] in ("prop", "proportion", "proportions"):
            kind, t = "prop", t[1:]
        elif t and t[0] in ("means", "mean"):
            t = t[1:]
        alpha = round(1 - float(opt(o, "level") or 95) / 100, 4)
        out = []
        for v in t:
            out.append(f"x = df[{q(v)}].dropna()")
            if kind == "prop":
                s.imp["prop"] = 1
                out.append(f"print(x.mean(), proportion_confint(x.sum(), len(x), alpha={alpha}, method='beta'))")
            else:
                s.imp["scipy"] = 1
                out.append(f"print(x.mean(), stats.t.interval({1 - alpha:g}, len(x) - 1, loc=x.mean(), scale=stats.sem(x)))")
        return out or s.unknown("ci " + r)

    def c_prtest(s, r, by):
        s.imp["prop"] = 1
        b, o = split_opts(r)
        g = opt(o, "by")
        if g:
            return [f"x = df.groupby({q(g)})[{q(b.strip())}]", "print(proportions_ztest(x.sum().values, x.count().values))"]
        m = re.match(r"(\w+)\s*==\s*([\d.]+)\s*$", b.strip())
        if m:
            return [f"x = df[{q(m.group(1))}].dropna()",
                    f"print(proportions_ztest(x.sum(), len(x), {m.group(2)}, prop_var={m.group(2)}))"]
        return s.unknown("prtest " + r)

    def c_prtesti(s, r, by):
        s.imp["prop"] = 1
        t = split_opts(r)[0].split()
        if len(t) == 4:
            return [f"print(proportions_ztest([round({t[0]} * {t[1]}), round({t[2]} * {t[3]})], [{t[0]}, {t[2]}]))"]
        if len(t) == 3:
            return [f"print(proportions_ztest(round({t[0]} * {t[1]}), {t[0]}, {t[2]}, prop_var={t[2]}))"]
        return s.unknown("prtesti " + r)

    def c_sdtest(s, r, by):
        s.imp["scipy"] = 1
        b, o = split_opts(r)
        g = opt(o, "by")
        if not g:
            return s.unknown("sdtest " + r)
        return [f"g = [x[{q(b.strip())}].dropna() for _, x in df.groupby({q(g)})]", "f = g[0].var() / g[1].var()",
                "print({'F': f, 'p': 2 * min(stats.f.cdf(f, len(g[0]) - 1, len(g[1]) - 1), "
                "stats.f.sf(f, len(g[0]) - 1, len(g[1]) - 1))})"]

    def c_swilk(s, r, by):
        s.imp["scipy"] = 1
        return [f"print({q(v)}, stats.shapiro(df[{q(v)}].dropna()))" for v in split_opts(r)[0].split()]

    def c_sktest(s, r, by):
        s.imp["scipy"] = 1
        return [f"print({q(v)}, stats.normaltest(df[{q(v)}].dropna()))" for v in split_opts(r)[0].split()]

    # ---- comandos inmediatos (datos dados como numeros): cci/csi/tabi/iri
    def c_cci(s, r, by):
        t = split_opts(r)[0].split()
        if len(t) != 4:
            return s.unknown("cci " + r)
        s.imp["contingency"] = s.imp["numpy"] = 1
        a, b, c, d = t  # a,b = casos expuestos/no expuestos; c,d = controles (o no casos) expuestos/no expuestos
        return [f"print(Table2x2(np.array([[{a}, {c}], [{b}, {d}]])).summary())"]

    c_csi = c_cci

    def c_tabi(s, r, by):
        b, o = split_opts(r)
        rows = [x.split() for x in b.split("\\")]
        if not all(rows) or len({len(x) for x in rows}) != 1:
            return s.unknown("tabi " + r)
        return s.crossopts("pd.DataFrame([" + ", ".join("[" + ", ".join(x) + "]" for x in rows) + "])", o)

    def c_iri(s, r, by):
        t = split_opts(r)[0].split()
        if len(t) != 4:
            return s.unknown("iri " + r)
        s.imp["scipy"] = 1
        return [f"a, b, n1, n0 = {', '.join(t)}", "bt = stats.binomtest(a, a + b, n1 / (n1 + n0))",
                "ci_ = bt.proportion_ci(method='exact')",
                "print({'IRR': (a / n1) / (b / n0), 'CI95': [p / (1 - p) * n0 / n1 for p in (ci_.low, ci_.high)], "
                "'p': bt.pvalue})"]

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
        miss = bool(re.search(r"\bmiss", o))
        if g and len(t) == 1:  # una variable indicadora por categoria: stub1, stub2, ...
            return [f"dm = pd.get_dummies(df[{q(t[0])}]).astype(int)",
                    f"dm.columns = [f'{g.group(1)}{{i}}' for i in range(1, dm.shape[1] + 1)]",
                    "df = pd.concat([df.drop(columns=dm.columns, errors='ignore'), dm], axis=1)"]
        if len(t) == 1:
            s.need("tab")
            return [f"print(tab({d}[{q(t[0])}]{', missing=True' if miss else ''}))"]
        if len(t) == 2:
            dn = ", dropna=False" if miss else ""
            return s.crossopts(f"pd.crosstab({d}[{q(t[0])}], {d}[{q(t[1])}]{dn})", o)
        return s.unknown("tabulate " + r)

    def crossopts(s, ct, o):
        """Opciones de tabulate/tabi sobre una tabla cruzada: row col cell nofreq expected chi2 exact."""
        has = lambda p: re.search(p, o)
        col, row, cell, nofreq = has(r"\bcol\w*"), has(r"\brow\b"), has(r"\bcell\b"), has(r"\bnofreq\b")
        exp, chi, ex = has(r"\bexp\w*"), has(r"\bchi2\b"), has(r"\bexact\b")
        if not (col or row or cell or nofreq or exp or chi or ex):
            return [f"print({ct})"]
        out = [f"ct = {ct}"] + ([] if nofreq else ["print(ct)"])
        if col:
            out.append("print((ct / ct.sum(axis=0) * 100).round(1))  # % column")
        if row:
            out.append("print((ct.div(ct.sum(axis=1), axis=0) * 100).round(1))  # % row")
        if cell:
            out.append("print((ct / ct.values.sum() * 100).round(1))  # % cell")
        if exp or chi or ex:
            s.imp["scipy"] = 1
        if exp:
            out.append("print(pd.DataFrame(stats.chi2_contingency(ct)[3], index=ct.index, columns=ct.columns).round(1))"
                       "  # expected")
        if chi:  # Stata: chi2 de Pearson, sin correccion de continuidad
            out.append("print(stats.chi2_contingency(ct, correction=False)[:3])  # chi2, p, df")
        if ex:
            out.append("print(stats.fisher_exact(ct))  # 2x2")
        return out

    def c_table(s, r, by):
        b, _ = split_opts(r)
        m = re.match(r"\(([^)]*)\)\s*(?:\(([^)]*)\))?\s*$", b.strip())
        rows, cols = (m.group(1).split(), (m.group(2) or "").split()) if m else (b.split()[:1], b.split()[1:2])
        if not rows:
            return s.unknown("table " + r)
        key = lambda vs: ", ".join(f"df[{q(v)}]" for v in vs)
        if not cols:
            return [f"print(df[{q(rows[0])}].value_counts(dropna=False))"]
        return [f"print(pd.crosstab([{key(rows)}], [{key(cols)}]))"]

    def c_cc(s, r, by):
        b, o = split_opts(r)
        t = b.split()
        if len(t) != 2:
            return s.unknown("cc " + r)
        s.imp["contingency"] = 1
        s.w("cc: se asume codificación 0/1 (1 = caso/expuesto); revisar si tus variables usan otros valores")
        case, ex = t
        g = re.search(r"by\((\w+)\)", o)
        tab = lambda d: f"pd.crosstab({d}[{q(ex)}], {d}[{q(case)}]).loc[[1, 0], [1, 0]]"
        if not g:
            return [f"print(Table2x2({tab('df')}).summary())"]
        return [f"tabs = {{k: {tab('x')} for k, x in df.groupby({q(g.group(1))})}}",
                "for k, t in tabs.items():", "    print(k)", "    print(Table2x2(t).summary())",
                "print(StratifiedTable(list(tabs.values())).summary())"]

    def c_correlate(s, r, by):
        v = split_opts(r)[0].split()
        return [f"print(df[{s.pl(v)}].corr())" if v else "print(df.corr(numeric_only=True))"]

    c_pwcorr = c_correlate

    def c_ttest(s, r, by):
        s.imp["scipy"] = 1
        b, o = split_opts(r)
        g = opt(o, "by")
        eq = ", equal_var=False" if re.search(r"\bunequal\b", o) else ""
        if g:
            return [f"print(stats.ttest_ind(*[x[{q(b.strip())}].dropna() for _, x in df.groupby({q(g)})]{eq}))"]
        m = re.match(r"(\w+)\s*==?\s*(-?[\d.]+)\s*$", b.strip())
        if m:
            return [f"print(stats.ttest_1samp(df[{q(m.group(1))}].dropna(), {m.group(2)}))"]
        m = re.match(r"(\w+)\s*==?\s*(\w+)\s*$", b.strip())
        if m:  # muestras pareadas
            a, c = q(m.group(1)), q(m.group(2))
            return [f"d = df[[{a}, {c}]].dropna()", f"print(stats.ttest_rel(d[{a}], d[{c}]))"]
        return s.unknown("ttest " + r)

    # ---- manejo de datos y pruebas de uso general
    c_cs = c_cc

    def c_reshape(s, r, by):
        kind, rest = head(r)
        b, o = split_opts(rest)
        i, j = (opt(o, "i") or "").split(), (opt(o, "j") or "").split()
        stubs = [x.replace("@", "") for x in b.split()]
        if kind == "wide" and i and j and stubs:
            return [f"df = df.pivot(index={s.pl(i)}, columns={q(j[0])}, values={stubs!r})",
                    "df.columns = [f'{a}{b}' for a, b in df.columns]", "df = df.reset_index()"]
        if kind == "long" and i and j and stubs:
            return [f"df = pd.wide_to_long(df, stubnames={stubs!r}, i={s.pl(i)}, j={q(j[0])}).reset_index()"]
        return s.unknown("reshape " + r)

    def c_encode(s, r, by):
        b, o = split_opts(r)
        g, v = opt(o, "gen") or opt(o, "generate"), (b.split() or [None])[0]
        if not (g and v):
            return s.unknown("encode " + r)
        s.use_labels()
        s.imp["numpy"] = 1
        return [f"cat = pd.Categorical(df[{q(v)}])",
                f"df[{q(g)}] = pd.Series(cat.codes + 1, index=df.index).replace(0, np.nan)",
                f"label_sets[{g!r}] = dict(enumerate(cat.categories, 1))", f"value_labels[{g!r}] = label_sets[{g!r}]"]

    def c_decode(s, r, by):
        b, o = split_opts(r)
        g, v = opt(o, "gen") or opt(o, "generate"), (b.split() or [None])[0]
        if not (g and v):
            return s.unknown("decode " + r)
        s.use_labels()
        return [f"df[{q(g)}] = df[{q(v)}].map(value_labels.get({q(v)}, {{}}))"]

    def c_destring(s, r, by):
        b, o = split_opts(r)
        v, g, ign = b.split(), opt(o, "gen") or opt(o, "generate"), QS.findall(opt(o, "ignore") or "")
        conv = lambda c: (f"pd.to_numeric(df[{q(c)}]" + (f".astype(str).str.replace({ign[0]!r}, '', regex=False)" if ign else "")
                          + ", errors='coerce')")
        if g and len(v) == 1:
            return [f"df[{q(g)}] = {conv(v[0])}"]
        if v and re.search(r"\breplace\b", o):
            return [f"df[{q(c)}] = {conv(c)}" for c in v]
        return s.unknown("destring " + r)

    def c_tostring(s, r, by):
        b, o = split_opts(r)
        v, g = b.split(), opt(o, "gen") or opt(o, "generate")
        if g and len(v) == 1:
            return [f"df[{q(g)}] = df[{q(v[0])}].astype('string')"]
        if v and re.search(r"\breplace\b", o):
            return [f"df[{q(c)}] = df[{q(c)}].astype('string')" for c in v]
        return s.unknown("tostring " + r)

    def c_preserve(s, r, by):
        return ["_preserved = df.copy()"]

    def c_restore(s, r, by):
        return ["df = _preserved.copy()"]

    def c_sample(s, r, by):
        b, o = split_opts(r)
        if not b.split():
            return s.unknown("sample " + r)
        n = b.split()[0]
        return [f"df = df.sample(n={n})" if re.search(r"\bcount\b", o) else f"df = df.sample(frac={n} / 100)"]

    def c_levelsof(s, r, by):
        b, o = split_opts(r)
        lv, loc = f"sorted(df[{q(b.split()[0])}].dropna().unique())", opt(o, "local")
        if loc:
            return [f"{loc} = ' '.join(str(x).removesuffix('.0') for x in {lv})", f"print({loc})"]
        return [f"print({lv})"]

    def c_isid(s, r, by):
        return [f"assert not df.duplicated({s.pl(split_opts(r)[0].split())}).any()"]

    def c_assert(s, r, by):
        return [f"assert {s.E(split_opts(r)[0])}.all()"]

    def c_mean(s, r, by):
        v, cond = split_if(split_opts(r)[0])
        return [f"print({s.D(cond)}[{s.pl(v.split())}].agg(['count', 'mean', 'sem']).T)"]

    def groups_of(s, b, o):
        """Valores de la variable b agrupados por by(): lista de Series (para pruebas de k grupos)."""
        g = opt(o, "by")
        return f"[x[{q(b.strip())}].dropna() for _, x in df.groupby({q(g)})]" if g else None

    def c_oneway(s, r, by):
        s.imp["scipy"] = 1
        t = split_opts(r)[0].split()
        if len(t) != 2:
            return s.unknown("oneway " + r)
        return [f"print(stats.f_oneway(*[x[{q(t[0])}].dropna() for _, x in df.groupby({q(t[1])})]))"]

    def c_kwallis(s, r, by):
        s.imp["scipy"] = 1
        b, o = split_opts(r)
        g = s.groups_of(b, o)
        return [f"print(stats.kruskal(*{g}))"] if g else s.unknown("kwallis " + r)

    def c_ranksum(s, r, by):
        s.imp["scipy"] = 1
        b, o = split_opts(r)
        g = s.groups_of(b, o)
        return ([f"print(stats.mannwhitneyu(*{g}, method='asymptotic', use_continuity=False))"] if g
                else s.unknown("ranksum " + r))

    def c_signrank(s, r, by):
        s.imp["scipy"] = 1
        m = re.match(r"(\w+)\s*=\s*(\w+)\s*$", split_opts(r)[0].strip())
        if not m:
            return s.unknown("signrank " + r)
        a, c = q(m.group(1)), q(m.group(2))
        return [f"d = df[[{a}, {c}]].dropna()", f"print(stats.wilcoxon(d[{a}], d[{c}]))"]

    def c_spearman(s, r, by):
        s.imp["scipy"] = 1
        t = split_opts(r)[0].split()
        if len(t) != 2:
            return s.unknown("spearman " + r)
        return [f"d = df[[{q(t[0])}, {q(t[1])}]].dropna()", f"print(stats.spearmanr(d[{q(t[0])}], d[{q(t[1])}]))"]

    def c_ktau(s, r, by):
        return [l.replace("spearmanr", "kendalltau") for l in s.c_spearman(r, by)]

    def c_anova(s, r, by):
        s.imp["smf"] = s.imp["sm"] = 1
        t = split_opts(r)[0].split()
        if len(t) < 2:
            return s.unknown("anova " + r)
        term = lambda x: ":".join(p[2:] if p.startswith("c.") else f"C({p}, Sum)" for p in x.split("#"))
        f = f"{t[0]} ~ " + " + ".join(term(x) for x in t[1:])
        return [f"print(sm.stats.anova_lm(smf.ols({f!r}, data=df).fit(), typ=3))"]

    # ---- más modelos
    def c_qreg(s, r, by):
        s.imp["smf"] = 1
        b, o = split_opts(r)
        v, cond = split_if(b)
        t = v.split()
        if not t:
            return s.unknown("qreg " + r)
        return [f"res = smf.quantreg({s.formula(t[0], t[1:])}, data={s.D(cond)}).fit(q={opt(o, 'quantile') or '.5'})",
                "print(res.summary())"]

    def c_glm(s, r, by):
        s.imp["smf"] = s.imp["sm"] = 1
        b, o = split_opts(r)
        v, cond = split_if(b)
        t = v.split()
        fam = {"binomial": "Binomial", "poisson": "Poisson", "gaussian": "Gaussian", "gamma": "Gamma"}.get(
            (opt(o, "family") or opt(o, "fam") or "gaussian").split()[0])
        if not (t and fam):
            return s.unknown("glm " + r)
        ln = (opt(o, "link") or "").split()
        lk = {"identity": "Identity", "log": "Log", "logit": "Logit", "probit": "Probit"}.get(ln[0]) if ln else None
        arg = f"link=sm.families.links.{lk}()" if lk else ""
        return [f"res = smf.glm({s.formula(t[0], t[1:])}, data={s.D(cond)}, family=sm.families.{fam}({arg})).fit()",
                "print(res.summary())"]

    def c_ologit(s, r, by, distr="logit"):
        s.imp["ordered"] = 1
        b, o = split_opts(r)
        v, cond = split_if(b)
        t = v.split()
        if not t:
            return s.unknown("ologit " + r)
        f = s.formula(t[0], t[1:]).replace(" ~ ", " ~ 0 + ", 1)
        return [f"res = OrderedModel.from_formula({f}, data={s.D(cond)}, distr='{distr}').fit(method='bfgs')",
                "print(res.summary())"]

    def c_oprobit(s, r, by):
        return s.c_ologit(r, by, "probit")

    # ---- análisis de supervivencia (lifelines). stset crea _t0, _t, _d y _st igual que Stata.
    def c_stset(s, r, by):
        b, o = split_opts(r)
        v, cond = split_if(b)
        t = v.split()
        if not t:
            return ["# stset"]
        ref = lambda x: x if NUM.fullmatch(x) else f"df[{q(x)}]"
        strip = lambda x: re.sub(r"^time\s+", "", x.strip())
        sc = f" / {opt(o, 'scale')}" if opt(o, "scale") else ""
        og = ref(strip(opt(o, "origin"))) if opt(o, "origin") else None
        en = ref(strip(opt(o, "enter"))) if opt(o, "enter") else None
        s.st_enter = bool(en)
        if cond:
            s.w("stset ... if: la condición no se aplica; filtra los datos antes con keep if")
        fl = opt(o, "failure") or opt(o, "fail")
        d = "1"
        if fl:
            m = re.match(r"(\w+)\s*(?:==\s*(.+))?$", fl.strip())
            if not m:
                return s.unknown("stset " + r)
            col, vals = f"df[{q(m.group(1))}]", m.group(2)
            if vals:
                vs = [x for x in re.split(r"[,\s]+", vals.strip()) if x]
                d = f"({col} == {vs[0]}).astype(int)" if len(vs) == 1 else f"{col}.isin([{', '.join(vs)}]).astype(int)"
            else:
                d = f"({col}.notna() & ({col} != 0)).astype(int)"
        t1 = f"df[{q(t[0])}]" + (f" - {og}" if og else "")
        t0 = (f"{en}" + (f" - {og}" if og else "")) if en else "0.0"
        wrap = lambda e: f"({e}){sc}" if sc else e
        return [f"df['_t0'] = {wrap(t0)}", f"df['_t'] = {wrap(t1)}", f"df['_d'] = {d}", "df['_st'] = 1"]

    def c_stdescribe(s, r, by):
        return ["print({'subjects': len(df), 'failures': int(df['_d'].sum()), "
                "'time at risk': (df['_t'] - df['_t0']).sum(), 'median time': df['_t'].median()})"]

    def c_stsum(s, r, by):
        s.need("strate")
        g = (opt(split_opts(r)[1], "by") or "").split()
        return [f"print(strate(df, by={s.by1(g)}, median=True))" if g else "print(strate(df, median=True))"]

    def c_strate(s, r, by):
        s.need("strate")
        t = split_opts(r)[0].split()
        return [f"print(strate(df, by={s.by1(t)}))" if t else "print(strate(df))"]

    def c_sts(s, r, by):
        sub, rest = head(r)
        b, o = split_opts(rest)
        g = (opt(o, "by") or "").split()
        gv = s.by1(g) if g else "None"
        if sub == "graph":
            s.need("sts_graph")
            s.plots = True
            fl = "".join(f", {k}=True" for k, p in (("failure", r"\bfailure\b"), ("ci", r"\bci\b"),
                                                  ("risktable", r"\brisktable\b")) if re.search(p, o))
            return [f"sts_graph(df, by={gv}{fl})"] + s.axopts(o)
        if sub == "list":
            s.need("sts_list")
            return [f"print(sts_list(df, by={gv}))"]
        if sub == "test" and b.split():
            s.imp["lls"] = 1
            wt = {"wilcoxon": "wilcoxon", "tware": "tarone-ware", "peto": "peto"}
            w = next((f", weightings={v!r}" for k, v in wt.items() if re.search(rf"\b{k}\b", o)), "")
            return [f"print(multivariate_logrank_test(df['_t'], df[{q(b.split()[0])}], df['_d']{w}).summary)"]
        m = re.match(r"(\w+)\s*=\s*(\w+)", b.strip())
        if sub in ("generate", "gen") and m and m.group(2) in ("s", "survivor"):
            s.need("km_at")
            return [f"df[{q(m.group(1))}] = km_at(df, by={gv})"]
        return s.unknown("sts " + r)

    def c_stcox(s, r, by):
        b, o = split_opts(r)
        wm = re.search(r"\[\s*(\w+)\s*=\s*(\w+)\s*\]", b)
        v, _ = split_if(re.sub(r"\[.*?\]", "", b))
        s.need("cox_fit")
        s.kind = "stcox"
        s.w("stcox: lifelines trata los empates con el método de Efron; Stata usa Breslow por defecto "
            "(la diferencia es pequeña salvo con muchos empates)")
        kw = ""
        if opt(o, "strata"):
            kw += f", strata={opt(o, 'strata').split()!r}"
        cl = re.search(r"(?:vce\(cluster\s+|cluster\()(\w+)\)", o)
        if cl:
            kw += f", cluster={cl.group(1)!r}"
        if wm:
            kw += f", weights={wm.group(2)!r}"
        if re.search(r"\brobust\b|vce\(robust\)", o):
            kw += ", robust=True"
        if s.st_enter:
            kw += ", entry=True"
        cols = ("'coef', 'se(coef)', 'z', 'p', 'coef lower 95%', 'coef upper 95%'" if re.search(r"\bnohr\b", o)
                else "'exp(coef)', 'z', 'p', 'exp(coef) lower 95%', 'exp(coef) upper 95%'")
        return [f"cph = cox_fit(df, {s.rhs_lit(v.split())}{kw})", f"print(cph.summary[[{cols}]])"]

    def c_streg(s, r, by):
        b, o = split_opts(r)
        d = (opt(o, "dist") or opt(o, "d") or "").split()
        cls = {"weibull": "WeibullAFTFitter", "lognormal": "LogNormalAFTFitter", "lnormal": "LogNormalAFTFitter",
               "loglogistic": "LogLogisticAFTFitter", "llogistic": "LogLogisticAFTFitter"}.get(d[0] if d else "")
        if not cls:
            return s.unknown("streg " + r)
        s.need("aft_fit")
        s.kind = "streg"
        out = [f"aft = aft_fit({cls}, df, {s.rhs_lit(b.split())})", "print(aft.summary)"]
        if d[0] == "weibull" and not re.search(r"\btime\b", o):  # Stata muestra razones de riesgo (métrica PH)
            s.imp["numpy"] = 1
            out += ["rho = np.exp(aft.params_[('rho_', 'Intercept')])",
                    "print(np.exp(-aft.params_['lambda_'].drop('Intercept') * rho))  # hazard ratios"]
        return out

    def c_stcurve(s, r, by):
        o = split_opts(r)[1]
        s.imp["plt"] = 1
        s.plots = True
        if re.search(r"\bsurv", o):
            return ["cph.baseline_survival_.plot()"] + s.axopts(o)
        if re.search(r"\bcumh", o):
            return ["cph.baseline_cumulative_hazard_.plot()"] + s.axopts(o)
        return s.unknown("stcurve " + r)

    # ---- propensity score, IPTW y emparejamiento
    def c_pscore(s, r, by):
        b, o = split_opts(r)
        t, ps = b.split(), opt(o, "pscore")
        if len(t) < 2 or not ps:
            return s.unknown("pscore " + r)
        s.imp["smf"] = 1
        s.kind = "logit"
        out = [f"res = smf.logit({s.formula(t[0], t[1:])}, data=df).fit(disp=0)", "print(res.summary())",
               f"df[{q(ps)}] = res.predict(df)"]
        if re.search(r"\bcomsup\b", o):
            x, tr = q(ps), q(t[0])
            lo = f"max(df.loc[df[{tr}] == 1, {x}].min(), df.loc[df[{tr}] == 0, {x}].min())"
            hi = f"min(df.loc[df[{tr}] == 1, {x}].max(), df.loc[df[{tr}] == 0, {x}].max())"
            out.append(f"df['comsup'] = df[{x}].between({lo}, {hi}).astype(int)")
        return out

    def c_teffects(s, r, by):
        method, rest = head(r)
        if method == "overlap":
            return s.c_psgraph("", by)
        b, o = split_opts(rest)
        gs, _ = groups(b)
        if method not in ("psmatch", "ipw", "ra", "aipw") or len(gs) != 2:
            return s.unknown("teffects " + r)
        (a1, _), (a2, o2) = split_opts(gs[0]), split_opts(gs[1])
        t1, t2 = a1.split(), a2.split()
        if not (t1 and t2):
            return s.unknown("teffects " + r)
        y, oc, tr = t1[0], t1[1:], t2[0]
        pc = oc if method == "ra" else t2[1:]
        kw = f", method={method!r}"
        if re.search(r"\batet\b", o):
            kw += ", att=True"
        if opt(o, "nneighbor") or opt(o, "nn"):
            kw += f", neighbors={opt(o, 'nneighbor') or opt(o, 'nn')}"
        if opt(o, "caliper"):
            kw += f", caliper={opt(o, 'caliper')}"
        if method in ("ra", "aipw") and oc:
            kw += f", ocovs={s.rhs_lit(oc)}"
        if re.search(r"\bprobit\b", o2):
            kw += ", link='probit'"
        s.need("teffects")
        s.w("teffects: el error estándar se calcula por bootstrap (Stata usa estimadores analíticos, p. ej. "
            "Abadie-Imbens en psmatch), por lo que difiere ligeramente")
        return [f"print(teffects(df, {q(y)}, {q(tr)}, {s.rhs_lit(pc)}{kw}))"]

    def c_psmatch2(s, r, by):
        b, o = split_opts(r)
        t, ys = b.split(), (opt(o, "outcome") or "").split()
        if len(t) < 2:
            return s.unknown("psmatch2 " + r)
        s.w("psmatch2: se estima con teffects (ATT salvo que uses ate); no se crean _pscore, _weight ni _id, "
            "y el error estándar es por bootstrap")
        if not ys:
            return s.c_pscore(f"{b}, pscore(_pscore)", by)
        s.need("teffects")
        kw = ", method='psmatch'" + ("" if re.search(r"\bate\b", o) else ", att=True")
        if opt(o, "neighbor") or opt(o, "n"):
            kw += f", neighbors={opt(o, 'neighbor') or opt(o, 'n')}"
        if opt(o, "caliper"):
            kw += f", caliper={opt(o, 'caliper')}"
        kw += ", link='logit'" if re.search(r"\blogit\b", o) else ", link='probit'"
        return [f"print(teffects(df, {q(y)}, {q(t[0])}, {s.rhs_lit(t[1:])}{kw}))" for y in ys]

    def c_tebalance(s, r, by):
        sub, _ = head(r)
        if sub != "summarize":
            return s.unknown("tebalance " + r)
        s.need("balance")
        s.need("teffects")
        a = "te_last['data'], te_last['treat'], te_last['covs']"
        return ["print('Raw'); print(balance(" + a + "))", "print('Matched/weighted'); print(balance(" + a + ", weights='_w'))"]

    def c_pbalchk(s, r, by):
        t = split_opts(r)[0].split()
        if len(t) < 2:
            return s.unknown("pbalchk " + r)
        s.need("balance")
        return [f"print(balance(df, {q(t[0])}, {s.rhs_lit(t[1:])}))"]

    def c_psgraph(s, r, by):
        s.imp["plt"] = 1
        s.plots = True
        s.need("teffects")
        return ["plt.figure()", "for g, x in te_last['data'].groupby(te_last['treat']):",
                "    plt.hist(x['_ps'], bins=20, alpha=.5, label=f'treat = {g}')", "plt.xlabel('Propensity score')",
                "plt.legend()"]

    def model(s, c, r, by):
        s.imp["smf"] = 1
        s.kind = c
        b, o = split_opts(r)
        wm = re.search(r"\[\s*(\w+)\s*=\s*(\w+)\s*\]", b)
        b = re.sub(r"\[.*?\]", "", b)
        if "[" in r and (not wm or c in ("mlogit", "nbreg")):
            s.w("Ponderadores [aweight/fweight/...] ignorados; usar smf.wls(..., weights=)")
            wm = None
        v, cond = split_if(b)
        t = v.split()
        if not t:
            return s.unknown(c + " " + r)
        f = s.formula(t[0], t[1:], " - 1" if re.search(r"\bnocons", o) else "")
        d, fit, pre = s.D(cond), MODELS[c], []
        if wm:  # [pweight=w] (IPTW, muestreo) / [fweight] / [aweight] / [iweight]
            wv = q(wm.group(2))
            s.imp["sm"] = 1
            if cond:
                pre, d = [f"d = {d}"], "d"
            if c == "regress":
                ctor = f"smf.wls({f}, data={d}, weights={d}[{wv}])"
            else:
                fam = {"poisson": "Poisson()", "probit": "Binomial(link=sm.families.links.Probit())"}.get(c, "Binomial()")
                ctor = f"smf.glm({f}, data={d}, family=sm.families.{fam}, freq_weights={d}[{wv}])"
                s.wglm = True
        else:
            ctor = f"smf.{fit}({f}, data={d})"
        cl = re.search(r"(?:vce\(cluster\s+|cluster\()(\w+)\)", o)
        hc = "HC1" if c == "regress" or wm else "HC0"
        odds = []
        if c == "logistic" or (c == "logit" and re.search(r"\bor\b", o)):
            s.imp["numpy"] = 1
            odds = ["ci = res.conf_int()",
                    "odds_ratios = pd.DataFrame({'OR': np.exp(res.params), 'CI_low': np.exp(ci[0]), 'CI_high': np.exp(ci[1])})",
                    "print(odds_ratios)"]
        if cl:
            return pre + [f"model = {ctor}",
                          f'res = model.fit(cov_type="cluster", cov_kwds={{"groups": df.loc[model.data.row_labels, {cl.group(1)!r}]}})',
                          "print(res.summary())"] + odds
        rb = re.search(r"\brobust\b|vce\((?:robust|hc\d)\)", o) or (wm and wm.group(1) == "pweight")
        return pre + [f'res = {ctor}.fit({f"cov_type={hc!r}" if rb else ""})', "print(res.summary())"] + odds

    c_regress = lambda s, r, by: s.model("regress", r, by)
    c_logit = lambda s, r, by: s.model("logit", r, by)
    c_logistic = lambda s, r, by: s.model("logistic", r, by)
    c_probit = lambda s, r, by: s.model("probit", r, by)
    c_poisson = lambda s, r, by: s.model("poisson", r, by)
    c_mlogit = lambda s, r, by: s.model("mlogit", r, by)
    c_nbreg = lambda s, r, by: s.model("nbreg", r, by)

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
        v, cond = split_if(b)
        t, op = v.split(), set(o.split())
        if not t:
            return s.unknown("predict " + r)
        ins = "e(sample)" in cond  # solo la muestra del modelo
        if s.kind == "stcox":
            sel = next((k for k in ("xb", "martingale", "deviance") if k in op), "hr")
            rhs = {"hr": "cph.predict_partial_hazard(cph.data_)", "xb": "cph.predict_log_partial_hazard(cph.data_)"}.get(
                sel, f"cph.compute_residuals(cph.data_, {sel!r})[{sel!r}]")
            return [f"df[{q(t[-1])}] = {rhs}"]
        idx = "res.fittedvalues.index"
        infl = lambda a: f"pd.Series(res.get_influence().{a}, index={idx})"
        if op & {"residuals", "resid", "res"}:
            rhs = "res.resid"
        elif "rstudent" in op:
            rhs = infl("resid_studentized_external")
        elif "hat" in op:
            rhs = infl("hat_matrix_diag")
        elif "cooksd" in op:
            rhs = infl("cooks_distance[0]")
        elif "xb" in op or s.kind in (None, "regress"):
            lin = "res.predict(df)" if s.kind in (None, "regress") else "res.predict(df, which='linear')"
            rhs = "res.fittedvalues" if ins and not s.wglm else lin
        else:  # logit/probit: probabilidad
            rhs = f"res.predict(df).loc[{idx}]" if ins else "res.predict(df)"
        return [f"df[{q(t[-1])}] = {rhs}"]

    def c_lroc(s, r, by):
        s.need("lroc")
        s.plots = True
        return ["print('AUC', lroc(res))"]

    def c_estimates(s, r, by):
        sub, rest = head(r)
        if sub == "store" and rest.split():
            if "estimates = {}" not in s.init:
                s.init.append("estimates = {}")
            return [f"estimates[{rest.split()[0]!r}] = res"]
        return s.unknown("estimates " + r)

    def c_lrtest(s, r, by):
        t = split_opts(r)[0].split()
        if len(t) != 2:
            return s.unknown("lrtest " + r)
        s.need("lrtest")
        nm = lambda x: "res" if x == "." else f"estimates[{x!r}]"
        return [f"print(lrtest({nm(t[0])}, {nm(t[1])}))"]

    def c_testparm(s, r, by):
        t = split_opts(r)[0].split()
        if not t:
            return s.unknown("testparm " + r)
        s.need("testparm")
        return [f"print(testparm(res, {', '.join(repr(s.term(x)) for x in t)}))"]

    def c_estat(s, r, by):
        sub, rest = head(r)
        o = split_opts(rest)[1] if rest else ""
        if sub == "hettest":
            s.imp["sm"] = s.imp["diag"] = 1
            return ["print(dict(zip(['chi2', 'p', 'F', 'p_F'], "
                    "het_breuschpagan(res.resid, sm.add_constant(res.fittedvalues), robust=False))))"]
        if sub == "gof":
            s.need("gof")
            g = opt(o, "group")
            return [f"print(gof(res{', groups=' + g if g else ''}))"]
        if sub == "vif":
            s.imp["vif"] = 1
            return ["print(pd.Series([variance_inflation_factor(res.model.exog, i) "
                    "for i in range(res.model.exog.shape[1])], index=res.model.exog_names))"]
        if sub == "phtest":
            s.imp["lls"] = 1
            tt = next((k for k in ("rank", "km", "log") if re.search(rf"\b{k}\b", o)), "identity")
            return [f"print(proportional_hazard_test(cph, cph.data_, time_transform={tt!r}).summary)"]
        if sub == "ic":
            return ["print({'AIC': res.aic, 'BIC': res.bic, 'll': res.llf})"]
        if sub == "classification":
            return ["print(pd.crosstab(res.model.endog, res.predict() >= 0.5, rownames=['observed'], "
                    "colnames=['predicted (>=0.5)']))"]
        return s.unknown("estat " + r)

    def c_margins(s, r, by):
        b, o = split_opts(r)
        fac = [x for tok in b.split() for x in (p.split(".")[-1] for p in tok.split("#")) if x]
        dy = (opt(o, "dydx") or "").split()
        at = {m.group(1): [float(x) if "." in x else int(x) for x in m.group(2).strip("()").split() if NUM.fullmatch(x)]
              for m in re.finditer(r"(\w+)\s*=\s*(\([^)]*\)|[^\s()]+)", opt(o, "at") or "")}
        s.need("margins")
        s.margins = (fac, dy, list(at))
        s.w("margins: se calculan sin errores estándar (Stata usa el método delta); "
            "para efectos marginales con IC usa res.get_margeff()")
        kw = (f", factors={fac!r}" if fac else "") + (f", dydx={dy!r}" if dy else "") + (f", at={at!r}" if at else "")
        return [f"mg = margins(res, df{kw})", "print(mg)"]

    def c_marginsplot(s, r, by):
        fac, dy, atk = s.margins or ([], [], [])
        s.imp["plt"] = 1
        s.plots = True
        if dy and atk:
            return [f"mg.plot(x={atk[0]!r}, y={'dy/dx ' + dy[0]!r}, marker='o')"]
        if len(fac) >= 2:
            return [f"mg.pivot(index={fac[0]!r}, columns={fac[1:]!r}, values='margin').plot(marker='o')"]
        if fac or atk:
            return [f"mg.plot(x={(fac or atk)[0]!r}, y='margin', marker='o')"]
        return s.unknown("marginsplot " + r)

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

    # ---- gráficos (matplotlib; todas las figuras se muestran al final con plt.show())
    def axopts(s, o):
        g = gparse(o)
        out = [f"plt.{fn}({g[k]!r})" for k, fn in (("title", "title"), ("xtitle", "xlabel"), ("ytitle", "ylabel")) if k in g]
        out += [f"plt.axhline({v}, linestyle='--', color='gray')" for v in g.get("yline", [])]
        out += [f"plt.axvline({v}, linestyle='--', color='gray')" for v in g.get("xline", [])]
        return out + ([f"plt.legend({g['legend']!r})"] if "legend" in g else [])

    def gkw(s, o):
        kw = [f"{k}={v!r}" for k, v in gparse(o).items()]
        by = opt(o, "by")
        return "".join(", " + k for k in kw + ([f"by={by.split(',')[0].split()[0]!r}"] if by else []))

    def c_histogram(s, r, by):
        s.imp["plt"] = s.imp["numpy"] = 1
        s.plots = True
        b, o = split_opts(r)
        v, cond = split_if(b)
        x, d, g = v.split()[0], s.D(cond), opt(o, "by")
        nb = f", bins={opt(o, 'bin')}" if opt(o, "bin") else ""
        if re.search(r"\bpercent\b", o):
            w, yl = ", weights=np.ones(len(v)) / len(v) * 100", "%"
        elif re.search(r"\bfraction\b", o):
            w, yl = ", weights=np.ones(len(v)) / len(v)", "Fraction"
        elif re.search(r"\bfreq", o):
            w, yl = "", "Frequency"
        else:
            w, yl = ", density=True", "Density"
        if g:
            g = g.split(",")[0].split()[0]
            return [f"grp = {d}.groupby({q(g)})", "fig, axes = plt.subplots(1, grp.ngroups, sharey=True, squeeze=False)",
                    "for ax, (k, e) in zip(axes[0], grp):", f"    v = e[{q(x)}].dropna()", f"    ax.hist(v{nb}{w})",
                    f"    ax.set_title(f'{g} = {{k}}')", f"    ax.set_xlabel({x!r})", f"    ax.set_ylabel({yl!r})"] + s.axopts(o)
        return ["plt.figure()", f"v = {d}[{q(x)}].dropna()", f"plt.hist(v{nb}{w})", f"plt.xlabel({x!r})",
                f"plt.ylabel({yl!r})"] + s.axopts(o)

    def plotspec(s, kind, content, gcond=""):
        v, cond = split_if(split_opts(content)[0])
        t = v.split()
        if kind not in ("scatter", "lfit", "line", "connected") or len(t) < 2:
            return None
        cond = cond or gcond
        cd = repr(s.ev(cond)) if cond else "None"
        return f"({('line' if kind == 'connected' else kind)!r}, {q(t[0])}, {q(t[-1])}, {cd})"

    def c_twoway(s, r, by):
        s.imp["plt"] = s.imp["numpy"] = 1
        s.plots = True
        b, o = split_opts(r)
        gs, rest = groups(b)
        specs = [s.plotspec(g.split()[0], g.partition(" ")[2], split_if(rest)[1]) for g in gs if g.split()]
        if not specs or None in specs:
            return s.unknown("twoway " + r)
        s.need("twoway")
        return [f"twoway(df, [{', '.join(specs)}]{s.gkw(o)})"]

    def c_scatter(s, r, by):
        b, o = split_opts(r)
        return s.c_twoway(f"(scatter {b})" + (", " + o if o else ""), by)

    def c_aaplot(s, r, by):
        b, o = split_opts(r)
        v, cond = split_if(b)
        t = v.split()
        out = s.c_twoway(f"(scatter {b}) (lfit {b})" + (", " + o if o else ""), by)
        s.imp["scipy"] = 1
        return out + [f"m = {s.D(cond)}[[{q(t[1])}, {q(t[0])}]].dropna()",
                      f"print(stats.linregress(m[{q(t[1])}], m[{q(t[0])}]))  # slope, intercept, r, p, se"]

    def c_kdensity(s, r, by):
        s.imp["plt"] = s.imp["numpy"] = s.imp["scipy"] = 1
        s.plots = True
        b, o = split_opts(r)
        x = b.split()[0]
        out = [f"v = df[{q(x)}].dropna()", "ax = v.plot.kde()"]
        if re.search(r"\bnormal\b", o):
            out += ["xs = np.linspace(v.min(), v.max(), 200)", "ax.plot(xs, stats.norm.pdf(xs, v.mean(), v.std()), '--')"]
        return out + [f"plt.xlabel({x!r})"] + s.axopts(o)

    def c_qnorm(s, r, by):
        s.imp["sm"] = s.imp["plt"] = 1
        s.plots = True
        b, o = split_opts(r)
        return [f"sm.qqplot(df[{q(b.split()[0])}].dropna(), line='q')"] + s.axopts(o)

    def c_rvfplot(s, r, by):
        s.imp["plt"] = 1
        s.plots = True
        o = split_opts(r)[1]
        return (["plt.figure()", "plt.scatter(res.fittedvalues, res.resid)", "plt.xlabel('Fitted values')",
                 "plt.ylabel('Residuals')"] + s.axopts(o))

    def c_lintrend(s, r, by):
        s.imp["plt"] = s.imp["numpy"] = 1
        s.plots = True
        b, o = split_opts(r)
        y, x = b.split()[:2]
        col = "log_odds" if opt(o, "plot") == "log" else "p"
        return [f"grp = pd.qcut(df[{q(x)}], {opt(o, 'groups') or 5}, labels=False, duplicates='drop')",
                f"lt = df.groupby(grp).agg(x=({q(x)}, 'mean'), p=({q(y)}, 'mean'))",
                "lt['log_odds'] = np.log(lt['p'] / (1 - lt['p']))", "print(lt)", "plt.figure()",
                f"plt.plot(lt['x'], lt['{col}'], marker='o')", f"plt.xlabel({x!r})", f"plt.ylabel({col!r})"]

    def c_graph(s, r, by):
        kind, rest = head(r)
        if kind == "export":
            b, o = split_opts(rest)
            s.imp["plt"] = 1
            w = opt(o, "width")
            return [f"plt.savefig({s.fn(b, '')}, dpi={round(int(w) / 6.4) if w and w.isdigit() else 150}, "
                    "bbox_inches='tight')"]
        if kind == "twoway":
            return s.c_twoway(rest, by)
        if kind in ("bar", "hbar"):
            return s.gbar(rest, kind == "hbar")
        if kind in ("box", "hbox"):
            return s.gbox(rest, kind == "hbox")
        return s.unknown("graph " + r)

    def gbar(s, r, horiz):
        s.imp["plt"] = 1
        s.plots = True
        b, o = split_opts(r)
        m = re.match(r"(?:\((\w+)\))?\s*(.*)$", b.strip())
        stat, ys = m.group(1) or "", split_if(m.group(2))[0].split()
        ov = re.findall(r"over\((\w+)", o)
        if not ov:
            return s.unknown("graph bar " + r)
        pct = re.search(r"\bpercent", o)
        if not ys and len(ov) == 1:
            data = [f"t = df[{q(ov[0])}].value_counts().sort_index()"] + ([] if stat == "count" else ["t = t / t.sum() * 100"])
        elif not ys:  # over(serie) over(grupo): el ultimo over() es el eje; la serie va en la leyenda
            data = [f"t = pd.crosstab(df[{q(ov[1])}], df[{q(ov[0])}])"]
            if pct:
                data.append("t = t.div(t.sum(axis=1), axis=0) * 100  # % within each category of " + ov[1])
            elif stat != "count":
                data.append("t = t / t.values.sum() * 100")
        else:
            fn = CST.get(stat or "mean", stat or "mean")
            data = [f"t = df.groupby({list(reversed(ov))!r})[{ys!r}].{fn}()" + (".unstack()" if len(ov) > 1 and len(ys) == 1 else "")]
        out = data + [f"ax = t.plot.{'barh' if horiz else 'bar'}(rot=0)"]
        bl = opt(o, "blabel")
        if bl is not None:
            fm = re.search(r"format\(([^)]*)\)", bl)
            out += ["for c in ax.containers:", f"    ax.bar_label(c, fmt={(fm.group(1) if fm else '%g')!r})"]
        return out + s.axopts(o)

    def gbox(s, r, horiz):
        s.imp["plt"] = 1
        s.plots = True
        b, o = split_opts(r)
        v, cond = split_if(b)
        ov = re.findall(r"over\((\w+)", o)
        call = (f"{s.D(cond)}.boxplot(column={v.split()!r}" + (f", by={ov[0]!r}" if ov else "")
                + (", vert=False" if horiz else "") + ", grid=False)")
        return ([] if ov else ["plt.figure()"]) + [call] + (["plt.suptitle('')"] if ov else []) + s.axopts(o)

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
            if s.rows is not None:  # filas de datos entre 'input' y 'end'
                if st == "end":
                    cols, rows = s.rows
                    s.rows = None
                    s.emit("df = pd.DataFrame([")
                    s.out += ["    " * (s.ind + 1) + "[" + ", ".join(rw) + "]," for rw in rows]
                    s.emit(f"], columns={cols!r})")
                elif st and not st.startswith(("*", "//")):
                    s.imp["numpy"] = s.imp.get("numpy") or "." in st.split()
                    s.rows[1].append(["np.nan" if t == "." else t if NUM.fullmatch(t) else repr(t) for t in st.split()])
                continue
            if st.startswith(". "):  # prompt de la consola de Stata copiado junto al comando
                st = st[2:].lstrip()
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
        if s.plots:
            s.emit("plt.show()")
        head = [tr("# Traducido de Stata a Python (revisar antes de usar)")] + [IMP[k] for k in IMP if s.imp.get(k)]
        for k in s.helpers:
            head += ["", "", HELPERS[k][1]]
        return "\n".join(head + [""] + s.init + ["", *s.out]).rstrip() + "\n", s.warns


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
            raise U(f"el atributo '{n.attr}' no se reconoce")
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
        raise U(f"el elemento '{type(n).__name__}' no se soporta en expresiones")

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
        raise U(f"la función '{name}' no tiene equivalente automático en Stata")

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
                s.w(f"No traducido: «{seg.splitlines()[0][:70] if seg else ''}» — motivo: {e}")

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
            raise U(f"la sentencia '{T.__name__}' no se soporta")

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
        raise U("llamada o expresión no reconocida")

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
