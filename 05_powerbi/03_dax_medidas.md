# Biblioteca de medidas DAX

Copiar cada bloque como una medida nueva en la tabla `_Medidas`. Están ordenadas
de más simple a más difícil; las tres últimas son las que de verdad distinguen a
alguien que sabe DAX de alguien que solo arrastra campos.

Todas devuelven el mismo número que las consultas de
`02_sql/04_saas_metrics.sql`. Ese contraste es la forma de saber que están bien.

---

## 1. Medidas base

```dax
Pedidos = CALCULATE ( COUNTROWS ( fact_order ), fact_order[order_status] = "completed" )

GMV = CALCULATE ( SUM ( fact_order[order_value_eur] ), fact_order[order_status] = "completed" )

Ticket medio = DIVIDE ( [GMV], [Pedidos] )

Pedidos cancelados =
CALCULATE ( COUNTROWS ( fact_order ), fact_order[order_status] <> "completed" )

Tasa de cancelacion % =
DIVIDE ( [Pedidos cancelados], COUNTROWS ( fact_order ) )
```

`DIVIDE` en lugar de `/`: devuelve vacío en vez de error cuando el denominador es
cero, cosa que en un informe con segmentadores pasa constantemente.

---

## 2. Clientes activos y MRR: el patrón «foto a fin de mes»

`fact_subscription` no tiene relación activa con la tabla de fechas (ver
`01_modelo_estrella.md`), así que el intervalo se filtra dentro de la medida.

```dax
Clientes activos =
VAR FinPeriodo = MAX ( dim_date[date] )
RETURN
    CALCULATE (
        DISTINCTCOUNT ( fact_subscription[restaurant_id] ),
        FILTER (
            ALL ( fact_subscription ),
            fact_subscription[start_date] <= FinPeriodo
                && ( ISBLANK ( fact_subscription[end_date] )
                     || fact_subscription[end_date] >= FinPeriodo )
        ),
        // se conservan los filtros de restaurante (mercado, plan, cocina...)
        VALUES ( dim_restaurant[restaurant_id] )
    )

MRR =
VAR FinPeriodo = MAX ( dim_date[date] )
RETURN
    CALCULATE (
        SUM ( fact_subscription[mrr_eur] ),
        FILTER (
            ALL ( fact_subscription ),
            fact_subscription[start_date] <= FinPeriodo
                && ( ISBLANK ( fact_subscription[end_date] )
                     || fact_subscription[end_date] >= FinPeriodo )
        ),
        VALUES ( dim_restaurant[restaurant_id] )
    )

ARR = [MRR] * 12

ARPU = DIVIDE ( [MRR], [Clientes activos] )
```

Detalle importante: `ALL ( fact_subscription )` quita el filtro de fecha, pero
`VALUES ( dim_restaurant[restaurant_id] )` vuelve a aplicar el filtro que venga
de la dimensión. Sin esa segunda parte, al filtrar por el mercado «DK» saldría el
MRR de toda la cartera.

---

## 3. Inteligencia de tiempo

```dax
MRR mes anterior = CALCULATE ( [MRR], DATEADD ( dim_date[date], -1, MONTH ) )

Crecimiento MRR % =
VAR Anterior = [MRR mes anterior]
RETURN DIVIDE ( [MRR] - Anterior, Anterior )

GMV YTD = TOTALYTD ( [GMV], dim_date[date] )

GMV mismo mes ano anterior = CALCULATE ( [GMV], SAMEPERIODLASTYEAR ( dim_date[date] ) )

GMV media movil 3M =
AVERAGEX (
    DATESINPERIOD ( dim_date[date], MAX ( dim_date[date] ), -3, MONTH ),
    [GMV]
)
```

Nada de esto funciona bien si la tabla de fechas no está **marcada como tabla de
fechas** y no cubre años completos.

---

## 4. Bajas y churn (aquí entra la relación inactiva)

```dax
Bajas =
CALCULATE (
    COUNTROWS ( fact_subscription ),
    fact_subscription[end_type] = "churn",
    USERELATIONSHIP ( fact_subscription[end_date], dim_date[date] )
)

MRR perdido =
CALCULATE (
    SUM ( fact_subscription[mrr_eur] ),
    fact_subscription[end_type] = "churn",
    USERELATIONSHIP ( fact_subscription[end_date], dim_date[date] )
)

Clientes activos mes anterior =
CALCULATE ( [Clientes activos], DATEADD ( dim_date[date], -1, MONTH ) )

Churn de clientes % =
DIVIDE ( [Bajas], [Clientes activos mes anterior] )

Churn de ingresos % =
DIVIDE ( [MRR perdido], CALCULATE ( [MRR], DATEADD ( dim_date[date], -1, MONTH ) ) )

Churn anualizado % = 1 - POWER ( 1 - [Churn de clientes %], 12 )
```

El denominador es la base **al cierre del mes anterior**. Es una elección, no una
verdad: con la base media del mes el número sale distinto. Lo importante es
escribirlo en el informe, porque si no, dos personas calculan dos churns.

---

## 5. Movimiento de MRR: nuevo, expansión, contracción y baja

Explica *por qué* se mueve el MRR. Es la vista que más se pide en las revisiones
de negocio y la que menos gente sabe montar.

```dax
MRR nuevo =
VAR FinPeriodo = MAX ( dim_date[date] )
VAR InicioPeriodo = MIN ( dim_date[date] )
RETURN
    CALCULATE (
        SUM ( fact_subscription[mrr_eur] ),
        FILTER (
            ALL ( fact_subscription ),
            fact_subscription[start_date] >= InicioPeriodo
                && fact_subscription[start_date] <= FinPeriodo
                && fact_subscription[end_type] <> "downgrade"
                && fact_subscription[end_type] <> "upgrade"
        )
    )

MRR neto = [MRR] - [MRR mes anterior]

MRR expansion =
VAR Neto = [MRR neto]
RETURN IF ( Neto > 0, Neto - [MRR nuevo] + [MRR perdido], BLANK () )
```

Cuando el modelo tiene cambios de plan, la descomposición exacta se calcula mejor
en la capa de datos —la consulta `movimiento_de_mrr` de
`02_sql/04_saas_metrics.sql`— y se carga ya resuelta. **Saber cuándo NO hacer
algo en DAX también es parte del oficio**: una medida de 40 líneas que se
recalcula en cada celda es peor que una tabla materializada.

---

## 6. Cohortes de retención

Columna calculada sobre una tabla puente `panel` (o directamente el CSV
`panel_restaurante_mes.csv`, que ya trae `antiguedad_meses`):

```dax
Retencion % =
VAR TamanoCohorte =
    CALCULATE (
        DISTINCTCOUNT ( panel[restaurant_id] ),
        ALLEXCEPT ( panel, panel[signup_cohort] ),
        panel[antiguedad_meses] = 0
    )
VAR Vivos = CALCULATE ( DISTINCTCOUNT ( panel[restaurant_id] ), panel[activo] = 1 )
RETURN DIVIDE ( Vivos, TamanoCohorte )
```

Se visualiza como matriz: filas `signup_cohort`, columnas `antiguedad_meses`,
valores `Retencion %`, con formato condicional de un solo color.

---

## 7. Experimento A/B

```dax
Restaurantes del experimento =
CALCULATE (
    DISTINCTCOUNT ( fact_campaign_assignment[restaurant_id] ),
    fact_campaign_assignment[campaign_id] = "CMP-003"
)

Pedidos 30 dias =
SUMX (
    VALUES ( dim_restaurant[restaurant_id] ),
    VAR Alta = CALCULATE ( MAX ( dim_restaurant[signup_date] ) )
    RETURN
        CALCULATE (
            [Pedidos],
            DATESBETWEEN ( dim_date[date], Alta, Alta + 29 )
        )
)

Pedidos 30 dias por restaurante =
DIVIDE ( [Pedidos 30 dias], DISTINCTCOUNT ( fact_campaign_assignment[restaurant_id] ) )
```

En el informe se pone `assignment_group` en el eje. El **intervalo de confianza
no se calcula en DAX**: se toma de `outputs/experimento_resumen.json` y se
escribe en una tarjeta de texto. Un gráfico de barras sin intervalo invita a leer
como diferencia real lo que puede ser ruido.

---

## Formato

- Importes: `#,##0 "€"`, sin decimales en tarjetas y con uno en tablas.
- Porcentajes: `0,0 %`.
- Toda medida con nombre en castellano y con la descripción rellena en el panel
  de propiedades: es lo que ve quien use el informe dentro de seis meses.
