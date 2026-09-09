# Four-Week Learning Path

This repository can be used as a structured learning programme rather than a
finished artefact to read once. Each week builds on the same commercial case,
so the focus remains on transferable analytical judgement rather than isolated
software exercises.

| Capability | Where it is practised | Priority |
|---|---|---|
| SQL | `02_sql/` | Very high |
| Power Query and DAX | `05_powerbi/` | Very high |
| pandas | `03_python/01_panel_and_metrics.py` | High |
| Regression, classification, clustering | `03_python/02_models.py` | Medium-high |
| SaaS metrics | `02_sql/04_saas_metrics.sql` and `05_cohorts.sql` | Medium-high |
| Experimentation | `04_experiment/ab_test_onboarding.py` | Medium |

## Week 1 · SQL and data preparation

**Goal:** become comfortable with filtering, grouping, CASE expressions, joins,
CTEs, window functions, and cleaning imperfect source files.

1. Run each query in `02_sql/01_exploration.sql`. Predict the result before
   looking at the output, then explain any mismatch.
2. Rewrite `top_restaurants` without `HAVING`, using a subquery, and verify that
   both versions return the same rows.
3. Replace `RANK()` with `DENSE_RANK()` and `ROW_NUMBER()` in
   `03_cte_windows.sql`; document how each function handles ties.
4. Load `data/raw/` into Power BI and reproduce the transformations from
   `01_data/clean_data.py` using the M examples in
   `05_powerbi/02_power_query_steps.md`.
5. Write three additional queries, such as average order value by weekday and
   market, first and last order by restaurant, or GMV share from the top 20% of
   customers.

Suggested Microsoft Learn paths:
[Query and modify data with Transact-SQL](https://learn.microsoft.com/en-us/training/paths/get-started-querying-with-transact-sql/)
and [Prepare data for analysis with Power BI](https://learn.microsoft.com/en-us/training/paths/prepare-data-power-bi/).

## Week 2 · Semantic modelling, Power BI, and DAX

**Goal:** build a reliable semantic model and measures that respond correctly to
date, market, and plan filters.

1. Recreate the relationships in `05_powerbi/01_star_schema.md` using the clean
   CSV files.
2. Mark `dim_date` as the date table and hide technical keys from report users.
3. Recreate the measures in `05_powerbi/03_dax_measures.md` without copying
   them, then reconcile the results with
   `outputs/sql_results/04_saas_metrics__*.csv`.
4. Build the three report pages specified in
   `05_powerbi/04_dashboard_guide.md`.
5. Filter the report to Denmark and confirm that MRR changes. If it does not,
   examine how the restaurant filter is propagated inside the interval-based
   subscription measures.

Focus on `CALCULATE`, filter context, row context, `USERELATIONSHIP`, and time
intelligence. These ideas matter more than memorising individual expressions.

Suggested Microsoft Learn paths:
[Model data with Power BI](https://learn.microsoft.com/en-us/training/paths/model-data-power-bi/)
and [Use DAX in Power BI semantic models](https://learn.microsoft.com/en-us/training/paths/dax-power-bi/).

## Week 3 · Applied Python

**Goal:** understand how data preparation, validation, modelling, and business
interpretation connect in one reproducible workflow.

1. Work through `03_python/01_panel_and_metrics.py` and explain why a
   restaurant-month panel is appropriate for predicting next-month outcomes.
2. Change the temporal cutoff in `03_python/02_models.py` and observe how test
   metrics change. Record why model performance depends on the validation period.
3. Add a feature such as days since last completed order and measure whether it
   improves churn ranking on the holdout period.
4. Compare logistic regression with a tree-based classifier. Evaluate the gain
   in discrimination against the loss of interpretability.
5. Give a one-minute explanation of the confusion matrix, precision, recall,
   AUC, cross-validation, and top-decile lift in business language.

References:
[scikit-learn: Getting Started](https://scikit-learn.org/stable/getting_started.html)
and [Linear Models](https://scikit-learn.org/stable/modules/linear_model.html).

## Week 4 · Commercial experimentation

**Goal:** design and interpret an A/B test without reducing the conclusion to a
single p-value.

1. Read `04_experiment/ab_test_onboarding.py` from the sampling checks through
   the final recommendation.
2. Change the true uplift in the data generator to 5%, regenerate the data, and
   rerun the pipeline. Explain why a real effect may not be detected with the
   available sample.
3. Calculate the confidence interval for the treatment-control difference by
   hand and reconcile it with the script.
4. Explain why covariate-adjusted OLS reduces variance in a randomised test but
   does not rescue failed randomisation.
5. Rewrite the recommendation for three audiences: a product manager, a finance
   director, and a data scientist.

Reference: [statsmodels documentation](https://www.statsmodels.org/stable/index.html).

As an optional next step, load the clean layer into a Microsoft Fabric lakehouse,
query it through a warehouse, and connect the semantic model to Power BI. Keep
this as an introduction until the underlying SQL and DAX are comfortable.

## Interview version

> I built an end-to-end analytics case for a restaurant SaaS platform covering
> 600 customers and more than 250,000 orders. The work showed that growth was
> driven primarily by acquisition, while retention deteriorated between months
> 2 and 6. I then developed a churn-prioritisation model: the highest-risk 10% of
> accounts contained 32% of next-month churn. Finally, I analysed a randomised
> onboarding test that increased first-30-day orders by 49%, including balance
> checks, confidence intervals, power, guardrails, and a staged rollout
> recommendation.

Practise this explanation until it sounds conversational. Then be ready to open
the relevant SQL, Python, or output file and explain how each number was derived.
