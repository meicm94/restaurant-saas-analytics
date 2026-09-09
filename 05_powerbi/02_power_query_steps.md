# Power Query: los pasos de limpieza, uno a uno

Cada apartado hace lo mismo que `01_data/clean_data.py`, pero en M. Se incluye el
código para pegarlo en el editor avanzado.

Un principio: **plegar** la consulta (query folding) siempre que se pueda y hacer
los filtros lo antes posible; cuanto más arriba se descarta una fila, menos
trabajo hay aguas abajo.

---

## 1. Pedidos: combinar una carpeta de ficheros mensuales

`data/raw/orders/` tiene un CSV por mes. En lugar de 20 consultas, se conecta a
**la carpeta** y se combinan. Así, cuando llegue el mes siguiente, basta con
dejar el fichero en la carpeta y actualizar.

```m
let
    Origen = Folder.Files("C:\...\data\raw\orders"),
    SoloCsv = Table.SelectRows(Origen, each [Extension] = ".csv"),
    Combinados = Table.Combine(
        List.Transform(SoloCsv[Content],
            each Csv.Document(_, [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]))),
    Encabezados = Table.PromoteHeaders(Combinados, [PromoteAllScalars = true]),
    // los ficheros de algunos meses vienen con coma decimal: se normaliza ANTES de convertir
    ComaAPunto = Table.TransformColumns(Encabezados,
        {{"order_value_eur", each Text.Replace(_, ",", "."), type text}}),
    Tipos = Table.TransformColumnTypes(ComaAPunto, {
        {"order_id", type text}, {"restaurant_id", type text},
        {"order_date", type date}, {"order_value_eur", type number},
        {"order_channel", type text}, {"fulfilment_type", type text},
        {"order_status", type text}}),
    // dos ficheros traen filas repetidas por un reproceso del ETL de origen
    SinDuplicados = Table.Distinct(Tipos, {"order_id"}),
    // el estado viene en mayusculas, minusculas y capitalizado
    EstadoNormalizado = Table.TransformColumns(SinDuplicados,
        {{"order_status", Text.Lower, type text}}),
    Completados = Table.AddColumn(EstadoNormalizado, "is_completed",
        each if [order_status] = "completed" then 1 else 0, Int64.Type)
in
    Completados
```

**Trampa que evitar:** convertir a número antes de cambiar la coma por el punto.
Con configuración regional inglesa, `"27,50"` se convierte en `2750` sin dar
ningún error. Son datos silenciosamente multiplicados por cien.

---

## 2. Restaurantes: fechas en dos formatos, texto sucio y duplicados

```m
let
    Origen = Csv.Document(File.Contents("...\restaurants_raw.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),
    SinDuplicados = Table.Distinct(Encabezados, {"restaurant_id"}),
    // mercado: conviven "DK", "dk" y "Denmark"
    MercadoNormalizado = Table.AddColumn(SinDuplicados, "market_iso", each
        let m = Text.Lower(Text.Trim([market])) in
        if List.Contains({"dk", "denmark"}, m) then "DK"
        else if List.Contains({"uk", "united kingdom"}, m) then "UK"
        else if List.Contains({"de", "germany"}, m) then "DE"
        else if List.Contains({"no", "norway"}, m) then "NO"
        else if List.Contains({"se", "sweden"}, m) then "SE"
        else "SIN MAPEAR", type text),
    // ciudad: espacios sobrantes y capitalizacion inconsistente
    CiudadLimpia = Table.TransformColumns(MercadoNormalizado,
        {{"city", each Text.Proper(Text.Trim(_)), type text}}),
    // fecha: unas filas vienen dd/MM/yyyy y otras yyyy-MM-dd
    FechaAlta = Table.AddColumn(CiudadLimpia, "signup", each
        if Text.Contains([signup_date], "/")
        then Date.FromText([signup_date], [Format = "dd/MM/yyyy"])
        else Date.FromText([signup_date], [Format = "yyyy-MM-dd"]), type date),
    // categoria: "", "N/A" y "unknown" son lo mismo
    CocinaLimpia = Table.TransformColumns(FechaAlta, {{"cuisine_type", each
        let v = Text.Trim(_ ?? "") in
        if List.Contains({"", "N/A", "unknown"}, v) then "Unknown" else v, type text}}),
    Cohorte = Table.AddColumn(CocinaLimpia, "signup_cohort",
        each Date.ToText([signup], [Format = "yyyy-MM"]), type text),
    Final = Table.RemoveColumns(Cohorte, {"market", "signup_date"})
in
    Final
```

**Comprobación imprescindible:** después del paso de mercado, filtrar por
`"SIN MAPEAR"` y confirmar que salen cero filas. Un `else "SIN MAPEAR"` que nadie
mira es una fuga silenciosa de datos.

---

## 3. Suscripciones: nulos falsos y números con divisa

```m
let
    Origen = ..., Encabezados = Table.PromoteHeaders(Origen),
    // "" y el texto "NULL" tienen que ser nulo de verdad para que las medidas
    // de suscripcion vigente funcionen
    NulosReales = Table.TransformColumns(Encabezados, {{"end_date", each
        if _ = null or _ = "" or _ = "NULL" then null else _, type nullable text}}),
    FechaBaja = Table.TransformColumnTypes(NulosReales,
        {{"end_date", type nullable date}, {"start_date", type date}}),
    // el MRR viene como "99,00 EUR" en parte de las filas
    MrrTexto = Table.TransformColumns(FechaBaja, {{"mrr_eur", each
        Text.Replace(Text.Replace(Text.Trim(_), " EUR", ""), ",", "."), type text}}),
    MrrNumero = Table.TransformColumnTypes(MrrTexto, {{"mrr_eur", type number}}),
    // plan_id trae espacios: si no se recortan, la relacion con dim_plan falla
    ClaveLimpia = Table.TransformColumns(MrrNumero, {{"plan_id", Text.Trim, type text}}),
    Vigente = Table.AddColumn(ClaveLimpia, "is_active",
        each if [end_date] = null then 1 else 0, Int64.Type)
in
    Vigente
```

**Trampa que evitar:** dejar `"NULL"` como texto. La relación sigue funcionando y
el informe no da error: simplemente cuenta como bajas a clientes que siguen
activos, y nadie lo nota hasta que alguien lo compara con facturación.

---

## 4. Tabla de fechas

Se puede cargar `dim_date.csv`, pero es más robusto generarla en M para que
cubra siempre todo el rango de los hechos:

```m
let
    Inicio = #date(2025, 1, 1),
    Fin = #date(2026, 12, 31),
    Dias = List.Dates(Inicio, Duration.Days(Fin - Inicio) + 1, #duration(1, 0, 0, 0)),
    Tabla = Table.FromList(Dias, Splitter.SplitByNothing(), {"date"}),
    Tipos = Table.TransformColumnTypes(Tabla, {{"date", type date}}),
    Columnas = Table.AddColumn(Table.AddColumn(Table.AddColumn(Table.AddColumn(
        Tipos, "year", each Date.Year([date]), Int64.Type),
        "month_number", each Date.Month([date]), Int64.Type),
        "year_month", each Date.ToText([date], [Format = "yyyy-MM"]), type text),
        "month_start", each Date.StartOfMonth([date]), type date)
in
    Columnas
```

---

## Buenas prácticas que se aplican en todas las consultas

1. **Renombrar los pasos** en castellano y con sentido. `#"Tipo cambiado1"` no
   dice nada dentro de tres meses.
2. **Nada de rutas absolutas repetidas**: crear un parámetro `RutaDatos` y
   referenciarlo. Cambiar de carpeta pasa a ser un único cambio.
3. **Deshabilitar la carga** de las consultas intermedias (clic derecho y quitar
   «Habilitar carga») para que no aparezcan como tablas en el modelo.
4. **Quitar columnas pronto**, no al final: reduce memoria y acelera la
   actualización.
5. **No usar la detección automática de tipos** sobre ficheros con
   configuraciones regionales mezcladas; se hace a mano, columna a columna.
