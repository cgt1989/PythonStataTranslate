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


def has(text, *frags):
    for f in frags:
        assert f in text, f"falta {f!r} en:\n{text}"


def test_stata_a_python():
    code, w = stata_to_python(DO)
    ast.parse(code)  # el resultado debe ser Python valido
    has(code, "import pandas as pd", "os.chdir(", "pd.read_stata('salarios.dta')",
        "# base principal", "# limpieza", "df['ln_w'] = df.eval('log(wage)'",
        "df.loc[df.eval('wage < 0', engine=\"python\"), 'wage'] = np.nan",
        "{controls.replace(' ', ' + ')} + C(region)", "cov_type='HC1'", "df = df[~df.eval('wage.isna()'",
        "groupby(['region'], as_index=False).agg(", "for v in ['wage', 'age']:", "for i in range(1, 4):",
        "if i > 2:", "else:", 'validate="1:1"', "pd.read_stata('otros.dta')",
        "# TODO (sin traducir): reshape", "# TODO (sin traducir): lasso")
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


def test_ingles():
    from traductor import EN
    for fn, src in ((stata_to_python, DO), (python_to_stata, PY)):
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
    test_ingles()
    print("OK")
