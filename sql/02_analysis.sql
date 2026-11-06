-- Analysis queries. Run them all with: python src/run_sql.py
-- Each starts with "-- name:" so the runner can label and save the output.

-- name: 1. National ZEV share by quarter
SELECT quarter, total, zev, zev_share, hybrid_share
FROM quarterly WHERE prov_code = 'CA' ORDER BY quarter;

-- name: 2. National ZEV share by year (ratio of sums, not the average of quarters)
SELECT year, SUM(total) AS total, SUM(zev) AS zev,
       ROUND(100.0 * SUM(zev) / SUM(total), 2) AS zev_share,
       ROUND(100.0 * SUM(hybrid) / SUM(total), 2) AS hybrid_share
FROM quarterly WHERE prov_code = 'CA' GROUP BY year ORDER BY year;

-- name: 3. Province ranking, latest quarter
SELECT province, total, zev, zev_share,
       RANK() OVER (ORDER BY zev_share DESC) AS rank
FROM quarterly
WHERE quarter = (SELECT MAX(quarter) FROM quarterly)
  AND prov_code <> 'CA' AND total IS NOT NULL
ORDER BY zev_share DESC;

-- name: 4. Year-over-year change, latest quarter vs the same quarter last year
WITH cur AS (SELECT * FROM quarterly WHERE quarter = (SELECT MAX(quarter) FROM quarterly)),
     prev AS (SELECT p.* FROM quarterly p JOIN cur c
              ON p.province = c.province AND p.year = c.year - 1 AND p.q = c.q)
SELECT c.province, prev.zev AS zev_last_year, c.zev AS zev_now,
       ROUND(100.0 * (c.zev - prev.zev) / prev.zev, 1) AS zev_growth_pct,
       ROUND(c.zev_share - prev.zev_share, 2) AS share_change_pts
FROM cur c JOIN prev ON prev.province = c.province
WHERE prev.zev > 0 ORDER BY zev_growth_pct DESC;

-- name: 5. Peak ZEV share per province and the gap to the latest quarter
WITH ranked AS (
  SELECT province, quarter, zev_share,
         MAX(zev_share) OVER (PARTITION BY province) AS peak_share,
         ROW_NUMBER() OVER (PARTITION BY province ORDER BY quarter DESC) AS rn
  FROM quarterly WHERE total IS NOT NULL)
SELECT r.province, r.peak_share,
       (SELECT MIN(quarter) FROM quarterly q2
         WHERE q2.province = r.province AND q2.zev_share = r.peak_share) AS peak_quarter,
       r.zev_share AS latest_share,
       ROUND(r.zev_share - r.peak_share, 2) AS gap_from_peak_pts
FROM ranked r WHERE r.rn = 1 ORDER BY r.peak_share DESC;

-- name: 6. National fuel mix by year (% of all new vehicles)
SELECT year,
       ROUND(100.0 * SUM(bev) / SUM(total), 2) AS bev_pct,
       ROUND(100.0 * SUM(phev) / SUM(total), 2) AS phev_pct,
       ROUND(100.0 * SUM(hybrid) / SUM(total), 2) AS hybrid_pct,
       ROUND(100.0 * SUM(gasoline) / SUM(total), 2) AS gasoline_pct,
       ROUND(100.0 * (SUM(COALESCE(diesel,0)) + SUM(COALESCE(other,0))) / SUM(total), 2) AS diesel_other_pct
FROM quarterly WHERE prov_code = 'CA' GROUP BY year ORDER BY year;

-- name: 7. Where Canada's ZEVs are registered, latest four quarters
WITH last4 AS (SELECT DISTINCT quarter FROM quarterly ORDER BY quarter DESC LIMIT 4)
SELECT province, SUM(zev) AS zev, SUM(total) AS total,
       ROUND(100.0 * SUM(zev) / SUM(total), 2) AS zev_share,
       ROUND(100.0 * SUM(zev) / (SELECT SUM(zev) FROM quarterly
             WHERE prov_code <> 'CA' AND quarter IN (SELECT quarter FROM last4)), 1) AS pct_of_national_zev
FROM quarterly
WHERE prov_code <> 'CA' AND quarter IN (SELECT quarter FROM last4)
GROUP BY province HAVING SUM(zev) > 0 ORDER BY zev DESC;

-- name: 8. The 2025 policy shock: four quarters before vs four quarters after
WITH tagged AS (
  SELECT province, prov_code, quarter, total, zev,
         CASE WHEN quarter IN ('2024Q1','2024Q2','2024Q3','2024Q4') THEN 'before_2024'
              WHEN quarter IN ('2025Q1','2025Q2','2025Q3','2025Q4') THEN 'after_2025' END AS era
  FROM quarterly WHERE total IS NOT NULL)
SELECT province,
       ROUND(100.0 * SUM(CASE WHEN era='before_2024' THEN zev END)
             / SUM(CASE WHEN era='before_2024' THEN total END), 2) AS share_2024,
       ROUND(100.0 * SUM(CASE WHEN era='after_2025' THEN zev END)
             / SUM(CASE WHEN era='after_2025' THEN total END), 2) AS share_2025,
       ROUND(100.0 * SUM(CASE WHEN era='after_2025' THEN zev END)
             / SUM(CASE WHEN era='after_2025' THEN total END)
           - 100.0 * SUM(CASE WHEN era='before_2024' THEN zev END)
             / SUM(CASE WHEN era='before_2024' THEN total END), 2) AS change_pts
FROM tagged WHERE era IS NOT NULL
GROUP BY province ORDER BY change_pts;
