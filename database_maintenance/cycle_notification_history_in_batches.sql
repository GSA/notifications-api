-- Call once at the start of the process

CREATE TABLE notification_history_pivot AS SELECT * from notification_history WHERE 1=2;

CREATE TEMPORARY TABLE nh_temp AS SELECT id FROM notification_history;

SELECT COUNT(*) AS "Total number of rows in nh" FROM nh_temp;

DELETE FROM nh_temp t
USING notification_history_pivot p
WHERE t.id = p.id;

SELECT COUNT(*) AS "Number of rows remaining that need moving across from nh to nh_pivot" FROM nh_temp;

CREATE INDEX nh_temp_idx ON nh_temp (id);

-- In each function call, using same database connection as used for the above SQL (needs to be in a transaction; this can be inside a stored function or in a transaction from the code)

INSERT INTO notification_history_pivot
SELECT n.*
FROM notification_history n,
     nh_temp t
WHERE n.id = t.id;

DELETE FROM nh_temp t
USING notification_history_pivot p
WHERE t.id = p.id;

SELECT COUNT(*) from nh_temp;

-- Loop until this result is zero.
