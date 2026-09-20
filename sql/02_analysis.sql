-- Step 4: analysis queries. Run them all with:  python src/run_sql.py
-- Each query starts with "-- name:" so the runner can label the output.

-- name: 1. National ZEV share, every quarter
SELECT quarter, total, zev, zev_share
FROM quarterly
WHERE prov_code = 'CA'
ORDER BY quarter;

-- name: 2. National ZEV share by year (sums the 4 quarters first)
SELECT year,
       SUM(total) AS total,
       SUM(zev)   AS zev,
       ROUND(100.0 * SUM(zev) / SUM(total), 2) AS zev_share
FROM quarterly
WHERE prov_code = 'CA'
GROUP BY year
ORDER BY year;

-- name: 3. Province ranking, latest quarter
SELECT province, total, zev, zev_share,
       RANK() OVER (ORDER BY zev_share DESC) AS rank
FROM quarterly
WHERE quarter = (SELECT MAX(quarter) FROM quarterly)
  AND prov_code NOT IN ('CA')
  AND total > 0
ORDER BY zev_share DESC;

-- name: 4. Year-over-year change in ZEV registrations, latest quarter vs same quarter last year
WITH cur AS (
    SELECT * FROM quarterly WHERE quarter = (SELECT MAX(quarter) FROM quarterly)
),
prev AS (
    SELECT p.* FROM quarterly p JOIN cur c
      ON p.province = c.province AND p.year = c.year - 1 AND p.q = c.q
)
SELECT c.province,
       prev.zev AS zev_last_year,
       c.zev    AS zev_now,
       ROUND(100.0 * (c.zev - prev.zev) / prev.zev, 1) AS zev_growth_pct,
       ROUND(c.zev_share - prev.zev_share, 2)          AS share_change_pts
FROM cur c JOIN prev ON prev.province = c.province
WHERE prev.zev > 0
ORDER BY zev_growth_pct DESC;

-- name: 5. Peak ZEV share per province, and how far below the peak it is now
WITH ranked AS (
    SELECT province, quarter, zev_share,
           MAX(zev_share) OVER (PARTITION BY province) AS peak_share,
           ROW_NUMBER() OVER (PARTITION BY province ORDER BY quarter DESC) AS rn
    FROM quarterly
    WHERE total > 0
)
SELECT r.province,
       r.peak_share,
       (SELECT MIN(quarter) FROM quarterly q2
         WHERE q2.province = r.province AND q2.zev_share = r.peak_share) AS peak_quarter,
       r.zev_share AS latest_share,
       ROUND(r.zev_share - r.peak_share, 2) AS gap_from_peak_pts
FROM ranked r
WHERE r.rn = 1
ORDER BY r.peak_share DESC;

-- name: 6. Fuel-type mix in Canada by year (% of all new vehicles)
SELECT year,
       ROUND(100.0 * SUM(bev)      / SUM(total), 1) AS bev_pct,
       ROUND(100.0 * SUM(phev)     / SUM(total), 1) AS phev_pct,
       ROUND(100.0 * SUM(hybrid)   / SUM(total), 1) AS hybrid_pct,
       ROUND(100.0 * SUM(gasoline) / SUM(total), 1) AS gasoline_pct,
       ROUND(100.0 * (SUM(COALESCE(diesel,0)) + SUM(COALESCE(other,0))) / SUM(total), 1) AS diesel_other_pct
FROM quarterly
WHERE prov_code = 'CA'
GROUP BY year
ORDER BY year;

-- name: 7. Share of Canada's ZEVs registered in each province, latest full year
WITH full_year AS (
    SELECT MAX(year) AS y FROM (
        SELECT year, COUNT(DISTINCT q) AS nq FROM quarterly WHERE prov_code = 'CA'
        GROUP BY year HAVING nq = 4)
)
SELECT province,
       SUM(zev) AS zev,
       ROUND(100.0 * SUM(zev) / (SELECT SUM(zev) FROM quarterly
                                  WHERE prov_code = 'CA' AND year = (SELECT y FROM full_year)), 1)
           AS pct_of_canada_zev
FROM quarterly
WHERE prov_code <> 'CA' AND year = (SELECT y FROM full_year)
GROUP BY province
ORDER BY zev DESC;
