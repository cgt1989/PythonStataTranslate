# PythonStataTranslate

**[Español](#español) · [English](#english)**

---

## Español

Aplicación de escritorio para Windows (`.exe`) que traduce **do-files de Stata → scripts de Python** y **scripts de Python → do-files de Stata**, conservando los comentarios y avisando cuando algo no tiene equivalente (por ejemplo, Stata no tiene machine learning nativo).

### Descarga

Baja `PythonStataTranslate.exe` desde la sección [**Releases**](https://github.com/cgt1989/PythonStataTranslate/releases/latest). No necesitas instalar Python.

### Uso

1. Abre la app y elige la dirección (**Stata → Python** o **Python → Stata**), o pulsa **Abrir archivo…** (la dirección se detecta por la extensión `.do` / `.py`).
2. Pulsa **Traducir**. A la derecha aparece el resultado y abajo las **advertencias**.
3. **Guardar…** o **Copiar salida**.
4. El selector **Idioma** cambia la interfaz y las advertencias entre español e inglés.

### Qué traduce

| Stata → Python | Python → Stata |
|---|---|
| `use`, `import`, `save`, `export` (pandas) | `read_csv` / `read_excel` / `read_stata`, `to_csv` / `to_stata` |
| `gen`, `replace`, `egen`, `drop`, `keep`, `rename`, `sort` | `df["x"] = …`, `drop`, `dropna`, `query`, `rename`, `sort_values` |
| `regress`, `logit`, `probit`, `poisson` (statsmodels; `robust`, `cluster`) | `smf.ols/logit/probit/poisson` → `regress`, `logit`… (`vce()`) |
| `xtset`/`xtreg` y `ivregress` (linearmodels) | `groupby` → `collapse` / `egen`, `merge` → `merge` |
| `merge`, `append`, `collapse`, `tab`, `summarize`, `ttest` | `np.where` → `cond()`, `np.log` → `ln`, `isna` → `missing` |
| `local`, `global`, `foreach`, `forvalues`, `if`/`else`, `capture` | `for`, `range`, `if`/`else`, `while`, `print` → `display` |

Las librerías (`pandas`, `numpy`, `statsmodels`, `scipy`, `matplotlib`, `linearmodels`) se importan automáticamente según lo usado.

### Advertencias que genera

- **Machine learning** (`sklearn`, `torch`, `tensorflow`, `xgboost`…): Stata no lo tiene de forma nativa; sugiere `lasso`/`elasticnet`, `pystacked` o un bloque `python:` (Stata 16+).
- **Valores missing**: en Stata `x > 5` es verdadero si `x` es missing; en pandas es falso.
- **Sin equivalente automático** (`reshape`, `esttab`, `margins`, `mi`, `svy`, `graph`…): queda como `# TODO` con la librería sugerida.
- **Código no soportado**: se deja comentado (`* PYTHON:`) y se avisa.

### Límites

Es una traducción por reglas: cubre lo más común, no todo Stata ni todo Python. **Revisa siempre el resultado** antes de usarlo. Al pasar de Python a Stata, si una columna ya existía en el archivo y se reasigna sin haberla leído antes en el script, saldrá `generate` en lugar de `replace`.

### Ejecutar desde el código fuente

```bash
python app.py                 # abrir la interfaz
python test_traductor.py      # pruebas
build.bat                     # generar el .exe (requiere PyInstaller)
```

---

## English

Windows desktop app (`.exe`) that translates **Stata do-files → Python scripts** and **Python scripts → Stata do-files**, keeping comments and warning you when something has no equivalent (for example, Stata has no native machine learning).

### Download

Get `PythonStataTranslate.exe` from the [**Releases**](https://github.com/cgt1989/PythonStataTranslate/releases/latest) page. You don't need to install Python.

### Usage

1. Open the app and pick the direction (**Stata → Python** or **Python → Stata**), or click **Open file…** (the direction is detected from the `.do` / `.py` extension).
2. Click **Translate**. The result appears on the right and the **warnings** below.
3. **Save…** or **Copy output**.
4. The **Language** selector switches the interface and the warnings between Spanish and English.

### What it translates

| Stata → Python | Python → Stata |
|---|---|
| `use`, `import`, `save`, `export` (pandas) | `read_csv` / `read_excel` / `read_stata`, `to_csv` / `to_stata` |
| `gen`, `replace`, `egen`, `drop`, `keep`, `rename`, `sort` | `df["x"] = …`, `drop`, `dropna`, `query`, `rename`, `sort_values` |
| `regress`, `logit`, `probit`, `poisson` (statsmodels; `robust`, `cluster`) | `smf.ols/logit/probit/poisson` → `regress`, `logit`… (`vce()`) |
| `xtset`/`xtreg` and `ivregress` (linearmodels) | `groupby` → `collapse` / `egen`, `merge` → `merge` |
| `merge`, `append`, `collapse`, `tab`, `summarize`, `ttest` | `np.where` → `cond()`, `np.log` → `ln`, `isna` → `missing` |
| `local`, `global`, `foreach`, `forvalues`, `if`/`else`, `capture` | `for`, `range`, `if`/`else`, `while`, `print` → `display` |

Libraries (`pandas`, `numpy`, `statsmodels`, `scipy`, `matplotlib`, `linearmodels`) are imported automatically according to what is used.

### Warnings it produces

- **Machine learning** (`sklearn`, `torch`, `tensorflow`, `xgboost`…): Stata has no native support; it suggests `lasso`/`elasticnet`, `pystacked` or a `python:` block (Stata 16+).
- **Missing values**: in Stata `x > 5` is true when `x` is missing; in pandas it is false.
- **No automatic equivalent** (`reshape`, `esttab`, `margins`, `mi`, `svy`, `graph`…): left as a `# TODO` with a suggested library.
- **Unsupported code**: left commented out (`* PYTHON:`) with a warning.

### Limitations

This is a rule-based translation: it covers the most common constructs, not all of Stata or all of Python. **Always review the output** before using it. When going from Python to Stata, if a column already existed in the file and is reassigned without being read earlier in the script, the output will use `generate` instead of `replace`.

### Run from source

```bash
python app.py                 # open the GUI
python test_traductor.py      # tests
build.bat                     # build the .exe (requires PyInstaller)
```
