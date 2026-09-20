-- Step 3: a view that turns the long table (one row per fuel type)
-- into one row per province per quarter, with ZEV share already calculated.
-- ZEV = battery electric (bev) + plug-in hybrid (phev), same as StatCan.

DROP VIEW IF EXISTS quarterly;
CREATE VIEW quarterly AS
SELECT
    quarter,
    year,
    q,
    province,
    prov_code,
    SUM(CASE WHEN fuel_type = 'total'    THEN vehicles END) AS total,
    SUM(CASE WHEN fuel_type = 'bev'      THEN vehicles END) AS bev,
    SUM(CASE WHEN fuel_type = 'phev'     THEN vehicles END) AS phev,
    SUM(CASE WHEN fuel_type = 'hybrid'   THEN vehicles END) AS hybrid,
    SUM(CASE WHEN fuel_type = 'gasoline' THEN vehicles END) AS gasoline,
    SUM(CASE WHEN fuel_type = 'diesel'   THEN vehicles END) AS diesel,
    SUM(CASE WHEN fuel_type = 'other'    THEN vehicles END) AS other,
    COALESCE(SUM(CASE WHEN fuel_type IN ('bev', 'phev') THEN vehicles END), 0) AS zev,
    ROUND(100.0 * COALESCE(SUM(CASE WHEN fuel_type IN ('bev', 'phev') THEN vehicles END), 0)
          / SUM(CASE WHEN fuel_type = 'total' THEN vehicles END), 2) AS zev_share
FROM registrations
GROUP BY quarter, year, q, province, prov_code;
