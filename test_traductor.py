"""Chequeo rapido: python test_traductor.py (sin frameworks)."""
import ast

from traductor import python_to_stata, stata_to_python

DO = r'''
* Analisis de salarios
set more off
cd "C:\datos"
use "salarios.dta", clear   // base principal
/* limpieza
   de datos */
gen ln_w = ln(wage)
gen adult = age >= 18 if age != .
replace wage = . if wage < 0
local controls age educ female
regress ln_w `controls' i.region, robust
drop if missing(wage)
keep id wage age educ region
bysort region: egen mw = mean(wage)
collapse (mean) wage (sum) n=educ, by(region)
foreach v in wage age {
    summarize `v'
    gen z_`v' = `v' * 2
}
forvalues i = 1/3 {
    display "iteracion `i'"
}
if `i' > 2 {
    display "grande"
}
else {
    display "chico"
}
merge 1:1 id using "otros.dta", keep(match) nogen
tabulate region
reshape wide x, i(id) j(t)
lasso linear y x1 x2
'''

PY = '''
import pandas as pd
import numpy as np
import statsmodels.formula.api as smf
from sklearn.ensemble import RandomForestClassifier

# cargar datos
df = pd.read_csv("datos.csv")
df["ln_w"] = np.log(df["wage"])  # logaritmo
df["adult"] = np.where(df["age"] >= 18, 1, 0)
df = df[df["wage"] > 0]
df = df.dropna(subset=["wage", "age"])
res = smf.ols("ln_w ~ age + C(region) + age:educ", data=df).fit(cov_type="HC1")
print(res.summary())
df["yhat"] = res.predict(df)
df["mw"] = df.groupby("region")["wage"].transform("mean")
out = df.groupby("region", as_index=False).agg(wage=("wage", "mean"))
for v in ["wage", "age"]:
    df[f"z_{v}"] = df[v] * 2
for i in range(1, 4):
    print(f"iteracion {i}")
n = len(df)
m = df["wage"].mean()
clf = RandomForestClassifier()
clf.fit(df[["age"]], df["wage"])
df.to_csv("salida.csv", index=False)
'''


EPI = r'''
*Unidad2_3: Regresión Logística
clear
cd "C:\Users\Luis\Clases\"
use "UCI Datav2.dta"
tabu ser sta, col chi2 exact nokey nolog
cc sta ser, w
logistic sta ser
tab agecat sta, chi2 exact nolog nokey
table (ser) (agecat sta)
cc sta ser, by(agecat) w
logistic sta i.ser i.agecat i.ser#i.agecat
miscomando x y
'''


def has(text, *frags):
    for f in frags:
        assert f in text, f"falta {f!r} en:\n{text}"


def test_stata_a_python():
    code, w = stata_to_python(DO)
    ast.parse(code)  # el resultado debe ser Python valido
    has(code, "import pandas as pd", "os.chdir(", "pd.read_stata('salarios.dta', convert_categoricals=False)",
        "# base principal", "# limpieza", "df['ln_w'] = df.eval('log(wage)'",
        "df.loc[df.eval('wage < 0', engine=\"python\"), 'wage'] = np.nan",
        "{controls.replace(' ', ' + ')} + C(region)", "cov_type='HC1'", "df = df[~df.eval('wage.isna()'",
        "groupby(['region'], as_index=False).agg(", "for v in ['wage', 'age']:", "for i in range(1, 4):",
        "if i > 2:", "else:", 'validate="1:1"', "pd.read_stata('otros.dta')",
        "df.pivot(", "# TODO (sin traducir): lasso")
    assert any("Missing" in x for x in w) and any("lasso" in x for x in w), w


def test_python_a_stata():
    code, w = python_to_stata(PY)
    has(code, "import delimited \"datos.csv\", clear", "* cargar datos", "generate ln_w = ln(wage)", "* logaritmo",
        "generate adult = cond(age >= 18, 1, 0)", "keep if wage > 0", "drop if missing(wage, age)",
        "regress ln_w age i.region c.age#c.educ, vce(robust)", "predict yhat", "bysort region: egen mw = mean(wage)",
        "collapse (mean) wage=wage, by(region)", "foreach v in wage age {", "generate z_`v' = `v' * 2",
        "forvalues i = 1/3 {", 'display "iteracion " `i\'', "local n = _N", "quietly summarize wage",
        "local m = r(mean)", "* PYTHON: clf = RandomForestClassifier()", 'export delimited "salida.csv", replace')
    assert any("machine learning" in x for x in w), w


def test_epidemiologia():
    code, w = stata_to_python(EPI)
    ast.parse(code)
    has(code, "from statsmodels.stats.contingency_tables import Table2x2, StratifiedTable",
        "ct = pd.crosstab(df['ser'], df['sta'])", "stats.chi2_contingency(ct, correction=False)", "stats.fisher_exact(ct)",
        "print(Table2x2(pd.crosstab(df['ser'], df['sta']).loc[[1, 0], [1, 0]]).summary())",
        "StratifiedTable(", "odds_ratios = ", "smf.logit('sta ~ C(ser) + C(agecat) + C(ser):C(agecat)'",
        "pd.crosstab([df['ser']], [df['agecat'], df['sta']])")
    # solo 'miscomando' debe fallar, y con el motivo explicado
    fallos = [x for x in w if x.startswith("No traducido")]
    assert len(fallos) == 1 and "miscomando" in fallos[0] and "motivo:" in fallos[0] and "no está soportado" in fallos[0], w
    # un comando conocido con sintaxis rara explica que es la sintaxis
    assert "sintaxis" in stata_to_python("generate = 5")[1][0]
    assert "stargazer" in stata_to_python("esttab using x.rtf")[1][0]


COURSE = r'''
use "bd.dta", clear
describe edad sexo
codebook sexo, compact
duplicates report id
label variable edad "Edad (años)"
label define sexo_lbl 1 "Hombre" 2 "Mujer"
label values sexo sexo_lbl
recode edad (min/39=1 "<40") (40/64=2 "40-64") (65/max=3 "65+"), gen(edadcat)
xtile q4 = coles, nq(4)
gen pam = round((2*coles + edad)/3, 0.1)
tabulate edadcat, missing
tab edadcat, gen(ed)
tabulate edadcat diabetes, row nofreq nokey
tabstat edad coles, stat(n mean sd p25 p50 p75) col(stat) by(diabetes)
summarize edad, detail
bysort diabetes: summarize edad coles
ci prop diabetes
ci means edad
prtest diabetes == 0.15
prtest diabetes, by(sexo)
ttest edad, by(diabetes) unequal
sdtest edad, by(diabetes)
swilk coles
histogram edad, percent by(diabetes)
graph box edad, over(diabetes)
graph bar, over(nedu) blabel(bar) ytitle("Frecuencia")
twoway (scatter coles edad) (lfit coles edad), by(sexo) title("Coles")
kdensity edad, normal
qnorm coles
graph export "g.png", replace width(1600)
regress coles c.edad##i.sexo
testparm c.edad#i.sexo
predict res_e, residuals
predict cook, cooksd
estat hettest
rvfplot, yline(0)
margins sexo, at(edad=(30 50 70))
marginsplot
scalar b1 = _b[edad]
logistic diabetes edad i.sexo
est store m1
logistic diabetes edad
est store m0
lrtest m1 m0
estat gof, group(10)
lroc
cci 215 228 1162 3104
csi 27 44 95 443
tabi 27 95 \ 44 443, row exp chi2 exact
iri 41 15 28010 19017
prtesti 122 0.2213 487 0.0903
input id a b
1 2 3
2 4 3
end
ttest a = b
summ a
display "dz = " r(mean)/r(sd)
'''


EXTRA = r'''
use "bd.dta", clear
preserve
gen str5 txt = "abc"
gen n = strlen(txt) + mod(edad, 7) + max(edad, coles) + min(edad, 50)
gen u = runiform()
egen g = group(sexo nedu)
egen t = tag(sexo)
egen rk = rank(coles)
egen rmax = rowmax(edad coles)
egen q50 = pctile(coles), p(50)
egen iq = iqr(coles), by(sexo)
encode txt, gen(txt_n)
decode sexo, gen(sexo_s)
tostring nedu, gen(nedu_s)
destring nedu_s, gen(nedu_n)
sample 80
levelsof nedu, local(niveles)
foreach l of local niveles {
    display "nivel `l'"
}
isid id
assert edad > 0
drop in 1/5
keep in 1/50
mean edad coles
oneway coles nedu
kwallis coles, by(sexo)
ranksum coles, by(sexo)
signrank edad = coles
spearman edad coles
anova coles sexo nedu
qreg coles edad, quantile(.5)
glm diabetes edad, family(binomial) link(logit)
nbreg edad coles
restore
keep id
gen x1 = 1
gen x2 = 2
reshape long x, i(id) j(t)
reshape wide x, i(id) j(t)
'''


def test_cobertura_extra():
    code, w = stata_to_python(EXTRA)
    ast.parse(code)
    assert not [x for x in w if x.startswith("No traducido")], w
    has(code, "_preserved = df.copy()", ".str.len()", "np.random.uniform", "ngroup()", "duplicated(", ".rank()",
        "pd.Categorical", "astype('string')", "pd.to_numeric(", "df.sample(frac=80 / 100)", "removesuffix",
        "stats.f_oneway(", "stats.kruskal(", "stats.mannwhitneyu(", "stats.wilcoxon(", "stats.spearmanr(",
        "anova_lm(", "smf.quantreg(", "smf.glm(", "negativebinomial", "pd.wide_to_long(")


SURV = r'''
use "s.dta", clear
stset time, failure(event==1)
stdescribe
stsum, by(treat)
strate sex
sts graph, by(treat) ci risktable title("KM")
sts list, by(treat)
sts test treat
sts test treat, wilcoxon
sts generate surv = s
stcox treat age i.sex
estat phtest, rank
predict hr, hr
predict mg, martingale
stcox treat age, strata(sex) robust
stcox treat age, nohr
stcurve, survival
streg treat age, dist(weibull)
streg treat age, dist(lognormal)
'''

PS_LIGHT = r'''
use "s.dta", clear
logit treat age bmi i.sex
predict ps, pr
gen iptw = treat/ps + (1-treat)/(1-ps)
regress y treat [pweight=iptw]
logit outcome treat [pw=iptw]
logistic outcome treat age [pweight=iptw]
stset time, failure(event)
stcox treat [pweight=iptw]
pscore treat age bmi i.sex, pscore(ps2) comsup
pbalchk treat age bmi
teffects psmatch (y) (treat age bmi i.sex), atet
teffects ipw (y) (treat age bmi)
tebalance summarize
teffects overlap
'''

PS_FULL = PS_LIGHT + r'''
teffects psmatch (y) (treat age bmi), nneighbor(3) caliper(.2)
teffects ra (y age bmi) (treat)
teffects aipw (y age bmi) (treat age bmi)
psmatch2 treat age bmi, outcome(y) neighbor(2) logit
'''


def test_supervivencia_y_ps():
    code, w = stata_to_python(SURV)
    ast.parse(code)
    assert not [x for x in w if x.startswith("No traducido")], w
    has(code, "df['_t'] = df['time']", "df['_d'] = (df['event'] == 1).astype(int)", "strate(df, by='treat', median=True)",
        "sts_graph(df, by='treat', ci=True, risktable=True)", "multivariate_logrank_test(", "weightings='wilcoxon'",
        "km_at(df, by=None)", "cox_fit(df, 'treat + age + C(sex)')", "proportional_hazard_test(cph, cph.data_, time_transform='rank')",
        "cph.predict_partial_hazard(cph.data_)", "strata=['sex'], robust=True", "WeibullAFTFitter", "LogNormalAFTFitter")
    code, w = stata_to_python(PS_FULL)
    ast.parse(code)
    assert not [x for x in w if x.startswith("No traducido")], w
    has(code, "smf.wls(", "freq_weights=", "weights='iptw'", "df['comsup'] = ", "balance(df, 'treat', 'age + bmi')",
        "method='psmatch', att=True", "method='ipw'", "method='ra'", "method='aipw'", "neighbors=3, caliper=.2",
        "te_last['data']", "link='logit'")
    assert stata_to_python("streg x, dist(exponential)")[1][0].startswith("No traducido")


def test_ejecucion_supervivencia_ps():
    try:
        import contextlib, io, os, tempfile, warnings
        import lifelines  # noqa: F401
        import matplotlib
        import numpy as np
        import pandas as pd
        import statsmodels  # noqa: F401
    except ImportError:
        print("(se omite test_ejecucion_supervivencia_ps: faltan lifelines/statsmodels/matplotlib)")
        return
    matplotlib.use("Agg")
    warnings.simplefilter("ignore")
    rng = np.random.default_rng(5)
    n = 300
    age, bmi = rng.normal(60, 10, n), rng.normal(27, 4, n)
    treat = (rng.random(n) < 1 / (1 + np.exp(-(0.05 * (age - 60) - 0.1 * (bmi - 27))))).astype(int)
    t_, c_ = rng.exponential(10 * np.exp(-0.6 * treat), n), rng.exponential(15, n)
    sim = pd.DataFrame({"time": np.minimum(t_, c_), "event": (t_ <= c_).astype(int), "treat": treat, "age": age,
                        "bmi": bmi, "sex": rng.integers(0, 2, n)})
    sim["y"] = 2 * sim.treat + 0.1 * sim.age + rng.normal(0, 2, n)
    sim["outcome"] = (rng.random(n) < .3).astype(int)
    pd.read_stata = lambda *a, **k: sim.copy()
    cwd = os.getcwd()
    os.chdir(tempfile.mkdtemp())
    try:
        for src in (SURV, PS_LIGHT):
            code, _ = stata_to_python(src)
            ns = {"__name__": "t"}
            for node in ast.parse(code).body:
                seg = ast.get_source_segment(code, node)
                if seg.startswith("plt.show"):
                    continue
                with contextlib.redirect_stdout(io.StringIO()):
                    try:
                        exec(compile(ast.Module([node], []), "t", "exec"), ns)
                    except Exception as e:  # noqa: BLE001
                        raise AssertionError(f"falló al ejecutar {seg.splitlines()[0]!r}: {e}")
        # el IPW debe acercar la diferencia estandarizada a 0
        b = ns["balance"]
        raw = abs(b(ns["te_last"]["data"], "treat", "age + bmi")["std_diff"]).max()
        wtd = abs(b(ns["te_last"]["data"], "treat", "age + bmi", weights="_w")["std_diff"]).max()
        assert wtd < raw, (raw, wtd)
    finally:
        os.chdir(cwd)


def test_cobertura_curso():
    """Comandos típicos de un curso de bioestadística: todo debe traducirse a Python válido."""
    code, w = stata_to_python(COURSE)
    ast.parse(code)
    assert not [x for x in w if x.startswith("No traducido")], w
    has(code, "tabstat(", "np.select(", "var_labels['edad']", "pd.qcut(", "proportion_confint(", "equal_var=False",
        "stats.shapiro(", "twoway(df,", "sm.qqplot(", "testparm(res,", "margins(res, df", "lrtest(estimates['m1']",
        "gof(res, groups=10)", "lroc(res)", "Table2x2(", "stats.binomtest(", "r['mean']/r['sd']", "plt.show()")


def test_ejecucion_curso():
    """Ejecuta el código generado con datos simulados (se omite si faltan pandas/statsmodels/matplotlib)."""
    try:
        import contextlib, io, os, tempfile, warnings
        import matplotlib
        import numpy as np
        import pandas as pd
        import statsmodels  # noqa: F401
    except ImportError:
        print("(se omite test_ejecucion_curso: faltan librerías)")
        return
    matplotlib.use("Agg")
    warnings.simplefilter("ignore")
    rng = np.random.default_rng(0)
    n = 300
    sim = pd.DataFrame({"id": np.arange(n), "edad": rng.integers(20, 85, n), "coles": rng.normal(200, 40, n),
                        "sexo": rng.integers(1, 3, n), "diabetes": (rng.random(n) < .2).astype(int),
                        "nedu": rng.integers(1, 4, n)})
    pd.read_stata = lambda *a, **k: sim.copy()
    cwd = os.getcwd()
    os.chdir(tempfile.mkdtemp())
    try:
        for src in (COURSE, EXTRA):
            code, _ = stata_to_python(src)
            ns = {"__name__": "t"}
            for node in ast.parse(code).body:
                seg = ast.get_source_segment(code, node)
                if seg.startswith("plt.show"):
                    continue
                with contextlib.redirect_stdout(io.StringIO()):
                    try:
                        exec(compile(ast.Module([node], []), "t", "exec"), ns)
                    except Exception as e:  # noqa: BLE001
                        raise AssertionError(f"falló al ejecutar {seg.splitlines()[0]!r}: {e}")
    finally:
        os.chdir(cwd)


def test_ingles():
    from traductor import EN
    for fn, src in ((stata_to_python, DO), (python_to_stata, PY), (stata_to_python, COURSE), (stata_to_python, EXTRA),
                    (stata_to_python, SURV), (stata_to_python, PS_FULL)):
        code, w = fn(src, "en")
        txt = code + "\n".join(w)
        # tras traducir, ningun fragmento en español debe quedar en marcas ni advertencias
        assert not [es for es, _ in EN if es in txt], [es for es, _ in EN if es in txt]
        assert "Translated from" in code and w
    assert "Not translated" in "\n".join(stata_to_python(DO, "en")[1])
    assert python_to_stata("x = (", "en")[1][0].startswith("The Python code is not valid")
    stata_to_python("", "es")  # restaurar el idioma por defecto


if __name__ == "__main__":
    test_stata_a_python()
    test_python_a_stata()
    test_epidemiologia()
    test_cobertura_curso()
    test_cobertura_extra()
    test_supervivencia_y_ps()
    test_ejecucion_curso()
    test_ejecucion_supervivencia_ps()
    test_ingles()
    print("OK")
