-- Stage 1 - manual process

-- Create new notification_history table and primary key.
CREATE TABLE notification_history_pivot AS SELECT * FROM notification_history WHERE 1=2;
ALTER TABLE notification_history_pivot ADD PRIMARY KEY (id);

-- Update values of notification_status, billable_units, updated_at, sent_by, sent_at based on new updates coming into the notification_history table.
CREATE OR REPLACE FUNCTION update_pivot_table()
RETURNS TRIGGER
LANGUAGE plpgsql AS 
$$
BEGIN
    UPDATE notification_history_pivot SET   notification_status = NEW.notification_status,
                                            billable_units = NEW.billable_units,
                                            updated_at = NEW.updated_at,
                                            sent_by = NEW.sent_by,
                                            sent_at = NEW.sent_at
    WHERE notification_history_pivot.id = NEW.id;

    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS update_pivot on notification_history;
CREATE TRIGGER update_pivot AFTER UPDATE OF notification_status, billable_units, updated_at, sent_by, sent_at ON notification_history
FOR EACH ROW
  EXECUTE PROCEDURE update_pivot_table();

-- Create foreign key constraints in notification_history_pivot using same names as used in notification_history
ALTER TABLE notification_history_pivot ADD CONSTRAINT fk_notification_history_notification_status FOREIGN KEY (notification_status) REFERENCES notification_status_types(name)
ALTER TABLE notification_history_pivot ADD CONSTRAINT notification_history_api_key_id_fkey FOREIGN KEY (api_key_id) REFERENCES api_keys(id)
ALTER TABLE notification_history_pivot ADD CONSTRAINT notification_history_job_id_fkey FOREIGN KEY (job_id) REFERENCES jobs(id)
ALTER TABLE notification_history_pivot ADD CONSTRAINT notification_history_key_type_fkey FOREIGN KEY (key_type) REFERENCES key_types(name)
ALTER TABLE notification_history_pivot ADD CONSTRAINT notification_history_service_id_fkey FOREIGN KEY (service_id) REFERENCES services(id)
ALTER TABLE notification_history_pivot ADD CONSTRAINT notification_history_templates_history_fkey FOREIGN KEY (template_id, template_version) REFERENCES templates_history(id, version)

-- Stage 2 - automated process

-- insert data into notification_history_pivot in batches
-- This is handled by a python process

-- Once the Python process has completed, then,

-- Stage 3 - manual process

-- Run basic sanity checks on data in notification_history_pivot, ensuring same number of entries present in notification_history and notification_history_pivot
SELECT COUNT(*) FROM notification_history_pivot;
SELECT COUNT(*) FROM notification_history;
-- Ensure these counts match.

ALTER TABLE notification_history RENAME TO notification_history_old;
ALTER TABLE notification_history_pivot RENAME TO notification_history;

-- Run sanity checks on data in notification_history_pivot
-- 1. Ensure same number of entries in notification_history and notification_history_pivot
-- If not then reconcile entries and add remaining entries to notification_history

-- When sure data in new notification_history table are ok:
-- ALTER TABLE notification_history_old DROP CONSTRAINT notification_history_pkey; -- May not need this step.
DROP TABLE notification_history_old;

-- Could rename primary key on new notification_history table.
ALTER TABLE notification_history DROP CONSTRAINT notification_history_pivot_pkey;
ALTER TABLE notification_history ADD PRIMARY KEY (id); -- Will create a new primary key named "notification_history_pkey".

-- Create remaining indices on notification_history_pivot
--- Create indexes after drop table since the names need to be unique
--- Or rename these indexes (index names have to be unique in db)
CREATE INDEX CONCURRENTLY ix_notification_history_job_id ON notification_history_pivot (job_id);
CREATE INDEX CONCURRENTLY ix_notification_history_reference ON notification_history_pivot (reference);
CREATE INDEX CONCURRENTLY ix_notification_history_template_id ON notification_history_pivot (template_id);
CREATE INDEX CONCURRENTLY ix_notifications_service_id_composite ON notification_history_pivot (service_id, key_type, notification_type, created_at);

-- Note that the only impact of these changes
