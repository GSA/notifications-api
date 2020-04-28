-- Create new notification_history table and primary key.
CREATE TABLE notification_history_pivot AS SELECT * FROM notification_history WHERE 1=2;
ALTER TABLE notification_history_pivot ADD PRIMARY KEY (id);

create trigger to update notification_history_pivot when update to notification_history

create foreign key constraints in notification_history_pivot

insert data into notification_history_pivot in batches

create remaining indices on notification_history_pivot

-- Run basic sanity checks on data in notification_history_pivot, ensuring same number of entries present in notification_history and notification_history_pivot

rename table notification_history to notification_history_old
rename table notification_history_pivot to notification_history;

-- Run sanity checks on data in notification_history_pivot
-- 1. Ensure same number of entries in notification_history and notification_history_pivot
-- If not then reconcile entries and add remaining entries to notification_history

-- When sure data in new notification_history table are ok:
drop table notification_history;
