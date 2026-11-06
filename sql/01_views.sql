-- One row per place per quarter, with ZEV share already computed.
-- ZEV = battery electric + plug-in hybrid, which is StatCan's own definition.
DROP VIEW IF EXISTS quarterly;
CREATE VIEW quarterly AS
SELECT
    quarter, year, q, province, prov_code,
    SUM(CASE WHEN fuel_type = 'total'        THEN vehicles END) AS total,
    SUM(CASE WHEN fuel_type = 'bev'          THEN vehicles END) AS bev,
    SUM(CASE WHEN fuel_type = 'phev'         THEN vehicles END) AS phev,
    SUM(CASE WHEN fuel_type = 'hybrid'       THEN vehicles END) AS hybrid,
    SUM(CASE WHEN fuel_type = 'gasoline'     THEN vehicles END) AS gasoline,
    SUM(CASE WHEN fuel_type = 'diesel'       THEN vehicles END) AS diesel,
    SUM(CASE WHEN fuel_type = 'other'        THEN vehicles END) AS other,
    SUM(CASE WHEN fuel_type = 'zev_reported' THEN vehicles END) AS zev,
    ROUND(100.0 * SUM(CASE WHEN fuel_type = 'zev_reported' THEN vehicles END)
          / SUM(CASE WHEN fuel_type = 'total' THEN vehicles END), 3) AS zev_share,
    ROUND(100.0 * SUM(CASE WHEN fuel_type = 'hybrid' THEN vehicles END)
          / SUM(CASE WHEN fuel_type = 'total' THEN vehicles END), 3) AS hybrid_share
FROM registrations
GROUP BY quarter, year, q, province, prov_code;
