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

create index concurrently created_id_nh on notification_history (created_at, id);