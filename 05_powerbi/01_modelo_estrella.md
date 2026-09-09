# Modelo semántico en Power BI

Todo lo que sigue se construye sobre `data/clean/*.csv`. La capa limpia existe
precisamente para que Power BI no tenga que arreglar nada en tiempo de consulta.

## Esquema

```
                      dim_date
                    (tabla de fechas
                     marcada como tal)
                          |
        +-----------------+------------------+
        |                 |                  |
   fact_order      fact_support_ticket   fact_subscription
        |                 |                  |
        +--------+--------+---------+--------+
                 |                  |
          dim_restaurant         dim_plan
                 |
      fact_campaign_assignment --- dim_campaign
```

## Relaciones

| Desde | Hacia | Cardinalidad | Dirección | Activa |
|---|---|---|---|---|
| `fact_order[restaurant_id]` | `dim_restaurant[restaurant_id]` | muchos a uno | simple | sí |
| `fact_order[order_date]` | `dim_date[date]` | muchos a uno | simple | sí |
| `fact_subscription[restaurant_id]` | `dim_restaurant[restaurant_id]` | muchos a uno | simple | sí |
| `fact_subscription[plan_id]` | `dim_plan[plan_id]` | muchos a uno | simple | sí |
| `fact_subscription[end_date]` | `dim_date[date]` | muchos a uno | simple | **NO (inactiva)** |
| `fact_support_ticket[restaurant_id]` | `dim_restaurant[restaurant_id]` | muchos a uno | simple | sí |
| `fact_support_ticket[ticket_date]` | `dim_date[date]` | muchos a uno | simple | sí |
| `fact_campaign_assignment[restaurant_id]` | `dim_restaurant[restaurant_id]` | muchos a uno | simple | sí |
| `fact_campaign_assignment[campaign_id]` | `dim_campaign[campaign_id]` | muchos a uno | simple | sí |

### Por qué `fact_subscription` NO se relaciona por `start_date`

Una suscripción tiene dos fechas —alta y baja— y además **ocupa un intervalo**,
no un día. Si se relaciona `start_date` con la tabla de fechas, al filtrar por
«agosto de 2026» solo aparecen las suscripciones que empezaron en agosto, no las
que estaban vigentes. Es el error clásico de este tipo de modelo.

La solución que se usa aquí:

1. **Ninguna relación activa** entre `fact_subscription` y `dim_date`. Las
   medidas de MRR y de clientes activos filtran el intervalo a mano (ver
   `03_dax_medidas.md`, patrón *foto a fin de mes*).
2. Una **relación inactiva** por `end_date`, que se activa con
   `USERELATIONSHIP` solo en las medidas de bajas.

Es más trabajo de medida, pero es lo único que da el número correcto cuando el
usuario cambia el mes en el segmentador.

## Ajustes obligatorios del modelo

- `dim_date`: **marcarla como tabla de fechas** por la columna `date`. Sin esto,
  las funciones de inteligencia de tiempo (`DATEADD`, `TOTALYTD`) no son fiables.
- Ordenar `dim_date[month_name]` por `dim_date[month_number]`; si no, los meses
  salen en orden alfabético.
- Ocultar del panel de campos todas las claves (`restaurant_id`, `plan_id`,
  `campaign_id`) y las columnas de fecha de las tablas de hechos: el usuario debe
  filtrar siempre por `dim_date`, nunca por la fecha del hecho.
- Ocultar `fact_order[order_value_eur]` y dejar visible solo la medida `GMV`. Una
  columna numérica suelta invita a arrastrarla al lienzo y obtener una suma que
  incluye pedidos cancelados.
- Crear una tabla de medidas vacía (`_Medidas`) para agruparlas todas.
- Tipos: importes en decimal fijo, fechas en fecha (no fecha y hora) y claves en
  texto.

## Modo de almacenamiento

Con este volumen —250.000 pedidos— **Import** es lo adecuado: cabe de sobra en
memoria y todo es instantáneo. DirectQuery solo tendría sentido si los pedidos
fueran decenas de millones o si hiciera falta ver los datos al minuto; a cambio
se pierden muchas funciones DAX y el informe va más lento.
