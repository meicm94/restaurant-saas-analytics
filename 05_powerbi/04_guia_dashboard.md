# Guía del informe: tres páginas, tres preguntas

Un informe no es una colección de gráficos: es la respuesta a una pregunta que
alguien se hace de verdad. Tres páginas, una pregunta cada una.

## Página 1 · Negocio: «¿cómo vamos?»

| Zona | Contenido |
|---|---|
| Fila de tarjetas | MRR, ARR, clientes activos, ARPU, GMV del mes y churn % |
| Gráfico principal | MRR por mes (línea) con media móvil de 3 meses |
| Apoyo izquierda | Movimiento de MRR por mes (barras apiladas: nuevo, expansión, contracción, baja) |
| Apoyo derecha | GMV y pedidos por mercado (barras horizontales ordenadas) |
| Segmentadores | Rango de fechas, mercado y plan |

Regla: si las tarjetas y el gráfico principal no responden la pregunta en cinco
segundos, sobra algo.

## Página 2 · Retención: «¿quién se nos va y por qué?»

| Zona | Contenido |
|---|---|
| Tarjetas | Bajas del mes, churn de clientes %, churn de ingresos %, NRR % |
| Gráfico principal | Matriz de cohortes con formato condicional de un solo tono |
| Apoyo | Bajas por motivo (barras) y por plan |
| Tabla | Clientes activos sin pedidos en 60 días, con MRR y último pedido, ordenada por MRR |

Esa última tabla es lo único accionable de la página: es la lista de llamadas del
equipo de retención. Sale de `02_sql/02_joins.sql > clientes_sin_actividad` y se
puede enriquecer con la probabilidad de baja del modelo.

## Página 3 · Experimento: «¿funcionó el nuevo onboarding?»

| Zona | Contenido |
|---|---|
| Texto | Hipótesis, métrica principal y periodo, en dos frases |
| Tarjetas | Pedidos a 30 días por grupo, diferencia %, intervalo de confianza y valor p |
| Gráfico | Media por grupo con barras de error |
| Gráfico | Distribución acumulada de pedidos por grupo |
| Tabla | Métricas secundarias y guardarraíl |

## Cosas que no se hacen

- **Dos ejes verticales.** Nunca. Si hay dos magnitudes de escala distinta, van
  en dos gráficos o se indexan a base 100.
- **Gráficos de tarta con más de tres categorías.** Barras ordenadas.
- **Colores asignados por posición en un ranking.** El color identifica a la
  entidad; si cambia el orden y cambia el color, el usuario se pierde.
- **Un número sin contexto.** Un 4,1 % de churn no dice nada; «4,1 %, frente al
  3,4 % del trimestre anterior» sí.
- **Decimales de más.** En una tarjeta, `62 K€` se lee; `61.803,45 €` no.
