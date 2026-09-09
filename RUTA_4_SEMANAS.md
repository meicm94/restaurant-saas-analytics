# Ruta de 4 semanas: cómo usar este proyecto para cerrar los gaps

Este repositorio no es solo un entregable: es el soporte de un plan de estudio.
La idea es no empezar cinco certificados a la vez, sino construir **un único
proyecto comercial** que atraviese todas las competencias.

| Competencia | Dónde se practica aquí | Prioridad |
|---|---|---|
| SQL | `02_sql/` (31 consultas) | Muy alta |
| Power Query y DAX | `05_powerbi/02_power_query_steps.md` y `03_dax_medidas.md` | Muy alta |
| Python con pandas | `03_python/01_panel_y_metricas.py` | Alta |
| Regresión, clasificación y clustering | `03_python/02_modelos.py` | Media-alta |
| Métricas SaaS | `02_sql/04_saas_metrics.sql` y `05_cohorts.sql` | Media-alta |
| A/B testing y OLS | `04_experiment/ab_test_onboarding.py` | Media |
| Microsoft Fabric | ver semana 4 (solo la introducción) | Media |

---

## Semana 1 · SQL y Power Query

**Objetivo:** escribir sin dudar `SELECT`, `WHERE`, `GROUP BY`, `CASE`, `JOIN`,
CTE y funciones de ventana, y limpiar un origen sucio.

Ejercicios sobre este repositorio:

1. Ejecutar `02_sql/01_exploration.sql` consulta a consulta y **predecir el
   resultado antes de verlo**. Donde no coincida, ahí está el hueco.
2. Reescribir `top_restaurantes` sin `HAVING` (con una subconsulta) y comprobar
   que da exactamente lo mismo.
3. En `03_cte_windows.sql`, cambiar `RANK()` por `DENSE_RANK()` y por
   `ROW_NUMBER()`, y explicar en una frase por qué cambian los empates.
4. Cargar `data/raw/` en Power BI y reproducir `01_data/clean_data.py` con Power
   Query, siguiendo `05_powerbi/02_power_query_steps.md`. Comparar el resultado
   fila a fila con `data/clean/`.
5. Escribir tres consultas nuevas que no estén en el repositorio. Por ejemplo:
   ticket medio por día de la semana y mercado; primer y último mes de cada
   restaurante; porcentaje de GMV que aporta el 20 % de clientes más grandes.

Rutas oficiales gratuitas: [Query and modify data with Transact-SQL](https://learn.microsoft.com/en-us/training/paths/get-started-querying-with-transact-sql/)
y [Prepare data for analysis with Power BI](https://learn.microsoft.com/en-us/training/paths/prepare-data-power-bi/).

---

## Semana 2 · Modelo en estrella, Power BI y DAX

**Objetivo:** montar un modelo semántico correcto y escribir medidas que
sobrevivan a los segmentadores.

1. Construir el modelo de `05_powerbi/01_modelo_estrella.md` en Power BI Desktop
   con los CSV de `data/clean/`.
2. Marcar `dim_date` como tabla de fechas y ocultar las claves.
3. Escribir las medidas de `03_dax_medidas.md` **de memoria**, sin copiar, y
   contrastar el resultado con `outputs/sql_results/04_saas_metrics__*.csv`. Si
   el MRR de Power BI no coincide con el de SQL, el modelo tiene un problema.
4. Montar las tres páginas de `04_guia_dashboard.md`.
5. Prueba de fuego: filtrar por el mercado «DK» y comprobar que el MRR baja. Si
   no cambia, falta el `VALUES(dim_restaurant[restaurant_id])` de la medida.

Conceptos que hay que entender de verdad, no memorizar: `CALCULATE`, contexto de
filtro frente a contexto de fila, `USERELATIONSHIP` e inteligencia de tiempo.

Rutas oficiales: [Model data with Power BI](https://learn.microsoft.com/en-us/training/paths/model-data-power-bi/)
y [Use DAX in Power BI semantic models](https://learn.microsoft.com/en-us/training/paths/dax-power-bi/).

---

## Semana 3 · Python aplicado

**Objetivo:** abrir un notebook y resolver, sin programación avanzada, limpieza,
agregación y tres modelos.

1. Recorrer `03_python/01_panel_y_metricas.py` y entender **por qué** el panel
   restaurante-mes es la tabla correcta para modelar: una fila por unidad y
   periodo, con la etiqueta del periodo siguiente.
2. Cambiar la fecha de corte `CORTE` en `02_modelos.py` y ver cómo se mueven las
   métricas. Es la mejor forma de interiorizar que un R² depende de la partición.
3. Añadir una variable nueva al modelo de baja (por ejemplo, días desde el último
   pedido) y comprobar si el AUC mejora.
4. Sustituir `LogisticRegression` por `RandomForestClassifier` y comparar: casi
   siempre gana un poco en AUC y pierde toda la interpretabilidad. Saber cuándo
   compensa es parte del criterio.
5. Explicar en voz alta, en un minuto, qué significan una matriz de confusión, la
   precisión, el recall y la validación cruzada.

Referencias oficiales: [scikit-learn: getting started](https://scikit-learn.org/stable/getting_started.html)
y [modelos lineales](https://scikit-learn.org/stable/modules/linear_model.html).

---

## Semana 4 · Experimento comercial y primer contacto con Fabric

**Objetivo:** saber plantear y leer un test A/B, y ver Fabric por encima sin
meterse todavía en la certificación.

Del experimento hay que poder recitar la ficha completa: hipótesis, métrica
principal, unidad de aleatorización, grupos, diferencia observada, incertidumbre,
limitaciones y recomendación. Está entera en `outputs/experimento_onboarding.md`,
generada por el propio script.

1. Leer `04_experiment/ab_test_onboarding.py` de arriba abajo.
2. Cambiar `TRUE_UPLIFT` en el generador a `0.05`, regenerar y volver a analizar:
   el efecto real existe, pero el test **no lo detecta**. Es la lección más útil
   de toda la semana.
3. Calcular a mano el intervalo de confianza de la diferencia y comprobar que
   coincide con el que da el script.
4. Explicar por qué el OLS con covariables no corrige un sesgo en un experimento
   aleatorizado, sino que reduce la varianza.

Referencia oficial: [statsmodels](https://www.statsmodels.org/stable/index.html).

**Fabric, solo la introducción:** cargar `data/clean/` en un lakehouse, consultar
un warehouse con SQL y conectar el modelo a Power BI. Nada más. La certificación
DP-600 llega después, cuando lo anterior esté sólido.
Ruta: [Get started with Microsoft Fabric](https://learn.microsoft.com/en-us/training/paths/get-started-fabric/).

---

## Cómo se cuenta esto en una entrevista

No «hice un proyecto de datos», sino el resultado y la decisión que permitió:

> «Monté la analítica completa de una plataforma SaaS de pedidos para
> restaurantes: 600 clientes y 250.000 pedidos. Encontré que el crecimiento
> depende casi por entero del cliente nuevo, con un NRR del 98 %, y que la
> retención se rompe entre el mes 2 y el 6. Construí un modelo de baja que
> concentra el 32 % de las bajas en el 10 % de la cartera con más riesgo, para
> que el equipo de retención sepa a quién llamar. Y leí un experimento de
> onboarding que dio un +49 % de pedidos en los primeros 30 días, con su
> intervalo de confianza y su cálculo de potencia, porque con 284 restaurantes
> solo se pueden detectar efectos grandes.»

Eso es lo que se recuerda al salir de la sala.
