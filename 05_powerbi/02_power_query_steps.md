# Power Query Cleaning Steps

These examples reproduce the main transformations in
`01_data/clean_data.py` using Power Query M. Replace the placeholder paths with
a parameter such as `DataPath` before using the code in Power BI Desktop.

Where the source supports query folding, filter early and preserve folding for
as long as possible. CSV files do not fold, but early row and column reduction
still lowers memory use and refresh time.

## 1. Combine monthly order files

Connect to `data/raw/orders/` as a folder rather than creating a query for each
month. A new monthly file will then be included automatically at refresh.

```m
let
    Source = Folder.Files(DataPath & "/raw/orders"),
    CsvFiles = Table.SelectRows(Source, each [Extension] = ".csv"),
    Imported = Table.AddColumn(
        CsvFiles,
        "Rows",
        each Table.PromoteHeaders(
            Csv.Document(
                [Content],
                [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
            ),
            [PromoteAllScalars = true]
        )
    ),
    Combined = Table.Combine(Imported[Rows]),
    DecimalNormalised = Table.TransformColumns(
        Combined,
        {{"order_value_eur", each Text.Replace(Text.From(_), ",", "."), type text}}
    ),
    Typed = Table.TransformColumnTypes(
        DecimalNormalised,
        {
            {"order_id", type text},
            {"restaurant_id", type text},
            {"order_date", type date},
            {"order_value_eur", Currency.Type},
            {"order_channel", type text},
            {"fulfilment_type", type text},
            {"order_status", type text}
        },
        "en-US"
    ),
    Deduplicated = Table.Distinct(Typed, {"order_id"}),
    StatusNormalised = Table.TransformColumns(
        Deduplicated,
        {{"order_status", each Text.Lower(Text.Trim(_)), type text}}
    ),
    CompletedFlag = Table.AddColumn(
        StatusNormalised,
        "is_completed",
        each if [order_status] = "completed" then 1 else 0,
        Int64.Type
    )
in
    CompletedFlag
```

Normalise decimal separators before changing the data type. Under an English
locale, a text value such as `"27,50"` can otherwise be interpreted incorrectly
without producing an obvious refresh error.

## 2. Clean restaurant attributes

The restaurant extract contains duplicate keys, multiple date formats,
inconsistent market codes, whitespace, and placeholder categories.

```m
let
    Source = Csv.Document(
        File.Contents(DataPath & "/raw/restaurants_raw.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Deduplicated = Table.Distinct(Headers, {"restaurant_id"}),
    MarketISO = Table.AddColumn(
        Deduplicated,
        "market_iso",
        each
            let market = Text.Lower(Text.Trim([market]))
            in
                if List.Contains({"dk", "denmark"}, market) then "DK"
                else if List.Contains({"uk", "united kingdom"}, market) then "UK"
                else if List.Contains({"de", "germany"}, market) then "DE"
                else if List.Contains({"no", "norway"}, market) then "NO"
                else if List.Contains({"se", "sweden"}, market) then "SE"
                else "UNMAPPED",
        type text
    ),
    CityClean = Table.TransformColumns(
        MarketISO,
        {{"city", each Text.Proper(Text.Trim(_)), type text}}
    ),
    SignupDate = Table.AddColumn(
        CityClean,
        "signup",
        each
            if Text.Contains([signup_date], "/")
            then Date.FromText([signup_date], [Format = "dd/MM/yyyy"])
            else Date.FromText([signup_date], [Format = "yyyy-MM-dd"]),
        type date
    ),
    CuisineClean = Table.TransformColumns(
        SignupDate,
        {{"cuisine_type", each
            let value = Text.Trim(_ ?? "")
            in if List.Contains({"", "N/A", "unknown"}, value)
               then "Unknown" else value,
          type text}}
    ),
    SignupCohort = Table.AddColumn(
        CuisineClean,
        "signup_cohort",
        each Date.ToText([signup], [Format = "yyyy-MM"]),
        type text
    ),
    Final = Table.RemoveColumns(SignupCohort, {"market", "signup_date"})
in
    Final
```

After creating `market_iso`, filter for `UNMAPPED` and confirm that the result is
empty. An unused fallback category can conceal a silent data-quality failure.

## 3. Clean subscription intervals

```m
let
    Source = Csv.Document(
        File.Contents(DataPath & "/raw/subscriptions_raw.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    RealNulls = Table.TransformColumns(
        Headers,
        {{"end_date", each
            if _ = null or Text.Trim(Text.From(_)) = "" or Text.Upper(Text.Trim(Text.From(_))) = "NULL"
            then null else _,
          type nullable text}}
    ),
    DatesTyped = Table.TransformColumnTypes(
        RealNulls,
        {{"start_date", type date}, {"end_date", type nullable date}}
    ),
    MrrText = Table.TransformColumns(
        DatesTyped,
        {{"mrr_eur", each
            Text.Replace(Text.Replace(Text.Trim(Text.From(_)), " EUR", ""), ",", "."),
          type text}}
    ),
    MrrTyped = Table.TransformColumnTypes(MrrText, {{"mrr_eur", Currency.Type}}, "en-US"),
    KeysClean = Table.TransformColumns(
        MrrTyped,
        {{"plan_id", Text.Trim, type text}, {"restaurant_id", Text.Trim, type text}}
    ),
    CurrentFlag = Table.AddColumn(
        KeysClean,
        "is_current",
        each if [end_date] = null then 1 else 0,
        Int64.Type
    )
in
    CurrentFlag
```

The string `"NULL"` must become a true null. Leaving it as text causes open
subscriptions to be treated as closed while the model still refreshes normally.

## 4. Create a date table in M

The repository includes `dim_date.csv`, but generating the table in M is useful
when the reporting horizon should extend automatically.

```m
let
    StartDate = #date(2025, 1, 1),
    EndDate = #date(2026, 12, 31),
    Dates = List.Dates(
        StartDate,
        Duration.Days(EndDate - StartDate) + 1,
        #duration(1, 0, 0, 0)
    ),
    DateTable = Table.FromList(Dates, Splitter.SplitByNothing(), {"date"}),
    Typed = Table.TransformColumnTypes(DateTable, {{"date", type date}}),
    Year = Table.AddColumn(Typed, "year", each Date.Year([date]), Int64.Type),
    MonthNumber = Table.AddColumn(Year, "month_number", each Date.Month([date]), Int64.Type),
    MonthName = Table.AddColumn(MonthNumber, "month_name", each Date.MonthName([date]), type text),
    YearMonth = Table.AddColumn(MonthName, "year_month", each Date.ToText([date], "yyyy-MM"), type text),
    MonthStart = Table.AddColumn(YearMonth, "month_start", each Date.StartOfMonth([date]), type date)
in
    MonthStart
```

## Quality checklist

- Create one `DataPath` parameter rather than repeating absolute file paths.
- Give steps descriptive names; avoid defaults such as `Changed Type1`.
- Disable load for staging queries that should not appear in the semantic model.
- Remove unused columns early.
- Define types explicitly, including locale, when files mix regional formats.
- Check uniqueness on dimension keys and order IDs.
- Confirm that no market is `UNMAPPED` and no subscription period is invalid.
- Reconcile row counts and financial totals with the Python clean layer.
